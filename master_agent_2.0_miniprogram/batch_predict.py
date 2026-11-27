# -*- coding: utf-8 -*-
"""批量请求小程序归属二分类模型接口

读取 xlsx 中的 query 列，逐条（可并发）调用 OpenAI 兼容 chat/completions 接口，
把预测结果写成 jsonl（可断点续跑）+ xlsx 汇总。

鉴权：Token 仅从环境变量读取，不写入代码/命令行历史
  export MINI_API_TOKEN='xxxxxxxx'
  # 可选：覆盖默认地址与模型
  export MINI_API_URL='https://devgw.tai.qq.com/tacs_llm_scenariox_agent_model_api_svc/openai/chat/completions'
  export MINI_API_MODEL='master-scenariox-mini-category-model'

用法：
  python3 batch_predict.py                        # 全量跑 test.xlsx
  python3 batch_predict.py --limit 20             # 先试跑 20 条
  python3 batch_predict.py --workers 8            # 并发 8
  python3 batch_predict.py --resume               # 跳过 jsonl 中已成功的 query
  python3 batch_predict.py --label-col label      # xlsx 带真值列时顺便算准确率
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from openpyxl import Workbook, load_workbook

HERE = Path(__file__).resolve().parent
DEFAULT_XLSX = HERE / "test.xlsx"
DEFAULT_JSONL = HERE / "test_pred.jsonl"
DEFAULT_REPORT = HERE / "test_pred.xlsx"

DEFAULT_URL = ("https://devgw.tai.qq.com/tacs_llm_scenariox_agent_model_api_svc"
               "/openai/chat/completions")
DEFAULT_MODEL = "master-scenariox-mini-category-model"
SYSTEM_PROMPT = (
    "你是车机小程序意图判别器。判断用户指令是否明确指向车机已上架的小程序"
    "（明确点名小程序或其常见简称即为是）。是则输出1，否则输出0。只输出数字。"
)

_print_lock = threading.Lock()


def log(msg):
    with _print_lock:
        print(msg, flush=True)


class RateLimiter:
    """全局 QPS 限速器，避免触发服务端 429。qps<=0 表示不限速。"""

    def __init__(self, qps: float):
        self.interval = 1.0 / qps if qps and qps > 0 else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def acquire(self):
        if not self.interval:
            return
        with self._lock:
            now = time.monotonic()
            wait = self._next - now
            if wait < 0:
                wait = 0.0
                self._next = now
            self._next += self.interval
        if wait > 0:
            time.sleep(wait)


def read_queries(xlsx_path: Path, query_col: str | None, label_col: str | None):
    """返回 [(query, label_or_None)]。无表头时取第一列全部单元格。"""
    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = [r for r in ws.iter_rows(values_only=True)]
    wb.close()
    if not rows:
        return []

    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    has_header = (query_col or "query") in header
    if has_header:
        qi = header.index(query_col or "query")
        li = header.index(label_col) if label_col and label_col in header else None
        body = rows[1:]
    else:
        qi, li, body = 0, None, rows
        if query_col:
            log(f"[warn] 未找到表头列 {query_col!r}，按第一列读取")

    out, seen = [], set()
    for r in body:
        q = r[qi] if qi < len(r) else None
        q = str(q).strip() if q is not None else ""
        if not q or q in seen:
            continue
        seen.add(q)
        lab = None
        if li is not None and li < len(r) and r[li] is not None:
            lab = str(r[li]).strip()
        out.append((q, lab))
    return out


def parse_pred(content: str):
    """从模型输出里抽取 0/1；无法判定返回 None。"""
    text = (content or "").strip()
    for ch in text:
        if ch in "01":
            return ch
    return None


def request_one(session, url, token, model, query, timeout, retries, limiter=None):
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        "temperature": 0.1,
        "chat_template_kwargs": {"enable_thinking": False},
        "openai_infer": True,
    }
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {token}"}
    last_err = ""
    for attempt in range(retries + 1):
        if limiter:
            limiter.acquire()
        t0 = time.time()
        throttled = False
        try:
            resp = session.post(url, json=payload, headers=headers, timeout=timeout)
            cost = round((time.time() - t0) * 1000)
            if resp.status_code != 200:
                last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                throttled = resp.status_code in (429, 503)
            else:
                data = resp.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                pred = parse_pred(content)
                if pred is None:
                    last_err = f"无法解析输出: {content[:120]!r}"
                else:
                    return {"pred": pred, "raw": content.strip(),
                            "latency_ms": cost, "error": ""}
        except Exception as e:  # 网络/超时/JSON 异常统一重试
            last_err = f"{type(e).__name__}: {e}"
        if attempt < retries:
            # 限流类错误退避更久
            base = 3.0 if throttled else 1.0
            time.sleep(min(base * (2 ** attempt), 30))
    return {"pred": None, "raw": "", "latency_ms": None, "error": last_err}


def load_done(jsonl_path: Path):
    """已成功预测过的 query -> 记录，用于 --resume。"""
    done = {}
    if not jsonl_path.is_file():
        return done
    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("pred") in ("0", "1"):
                done[rec.get("query")] = rec
    return done


def write_report(path: Path, records, with_label):
    wb = Workbook()
    ws = wb.active
    ws.title = "预测结果"
    head = ["query", "pred", "raw", "latency_ms", "error"]
    if with_label:
        head.insert(2, "label")
        head.insert(3, "correct")
    ws.append(head)
    for r in records:
        row = [r["query"], r.get("pred") or "", r.get("raw", ""),
               r.get("latency_ms"), r.get("error", "")]
        if with_label:
            lab = r.get("label") or ""
            correct = "" if (not lab or not r.get("pred")) else int(lab == r["pred"])
            row.insert(2, lab)
            row.insert(3, correct)
        ws.append(row)
    wb.save(path)


def main():
    ap = argparse.ArgumentParser(description="批量请求二分类模型接口")
    ap.add_argument("-i", "--input", default=str(DEFAULT_XLSX), help="输入 xlsx")
    ap.add_argument("-o", "--output", default=str(DEFAULT_JSONL), help="输出 jsonl")
    ap.add_argument("-r", "--report", default=str(DEFAULT_REPORT), help="输出汇总 xlsx")
    ap.add_argument("--query-col", default=None, help="query 所在列名（无表头可不填）")
    ap.add_argument("--label-col", default=None, help="真值列名，提供则计算准确率")
    ap.add_argument("--workers", type=int, default=4, help="并发数")
    ap.add_argument("--qps", type=float, default=8.0, help="全局限速，每秒请求数（0=不限速）")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全量）")
    ap.add_argument("--timeout", type=float, default=30.0, help="单次请求超时秒")
    ap.add_argument("--retries", type=int, default=4, help="失败重试次数")
    ap.add_argument("--resume", action="store_true", help="跳过已成功的 query")
    args = ap.parse_args()

    token = os.environ.get("MINI_API_TOKEN")
    if not token:
        sys.exit("[error] 请先设置环境变量 MINI_API_TOKEN")
    url = os.environ.get("MINI_API_URL", DEFAULT_URL)
    model = os.environ.get("MINI_API_MODEL", DEFAULT_MODEL)

    xlsx_path = Path(args.input).expanduser().resolve()
    if not xlsx_path.is_file():
        sys.exit(f"[error] 输入文件不存在: {xlsx_path}")
    jsonl_path = Path(args.output).expanduser().resolve()
    report_path = Path(args.report).expanduser().resolve()

    items = read_queries(xlsx_path, args.query_col, args.label_col)
    if args.limit:
        items = items[:args.limit]
    if not items:
        sys.exit("[error] 未读到任何 query")

    done = load_done(jsonl_path) if args.resume else {}
    todo = [(q, l) for q, l in items if q not in done]
    log(f"[info] 共 {len(items)} 条，待请求 {len(todo)} 条"
        f"{f'（复用已完成 {len(items) - len(todo)} 条）' if done else ''}"
        f"，并发 {args.workers}，限速 {args.qps or '不限'} qps")

    limiter = RateLimiter(args.qps)
    results, counter = {}, {"n": 0}
    session_local = threading.local()

    def get_session():
        if not hasattr(session_local, "s"):
            session_local.s = requests.Session()
        return session_local.s

    write_mode = "a" if (args.resume and jsonl_path.is_file()) else "w"
    out_lock = threading.Lock()
    with jsonl_path.open(write_mode, encoding="utf-8") as writer:
        def work(item):
            query, label = item
            res = request_one(get_session(), url, token, model, query,
                              args.timeout, args.retries, limiter)
            rec = {"query": query, "label": label, **res}
            with out_lock:
                writer.write(json.dumps(rec, ensure_ascii=False) + "\n")
                writer.flush()
                results[query] = rec
                counter["n"] += 1
                if counter["n"] % 50 == 0 or counter["n"] == len(todo):
                    log(f"[info] 进度 {counter['n']}/{len(todo)}")
            if res["error"]:
                log(f"[fail] {query} -> {res['error']}")
            return rec

        if todo:
            with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
                list(pool.map(work, todo))

    ordered, with_label = [], any(l for _, l in items)
    for q, l in items:
        rec = results.get(q) or done.get(q) or {"query": q, "label": l,
                                                "pred": None, "raw": "",
                                                "latency_ms": None, "error": "未请求"}
        rec.setdefault("label", l)
        ordered.append(rec)
    write_report(report_path, ordered, with_label)

    ok = [r for r in ordered if r.get("pred") in ("0", "1")]
    fail = len(ordered) - len(ok)
    pos = sum(1 for r in ok if r["pred"] == "1")
    lat = [r["latency_ms"] for r in ok if r.get("latency_ms")]
    log(f"\n[done] 成功 {len(ok)} / 失败 {fail}；pred=1 {pos} 条，pred=0 {len(ok) - pos} 条")
    if lat:
        lat.sort()
        log(f"       延迟 avg={sum(lat) // len(lat)}ms p90={lat[int(len(lat) * 0.9) - 1]}ms")
    if with_label:
        judged = [r for r in ok if r.get("label") in ("0", "1")]
        if judged:
            acc = sum(1 for r in judged if r["label"] == r["pred"]) / len(judged)
            log(f"       准确率 {acc:.4f}（{len(judged)} 条有真值）")
    log(f"       明细 {jsonl_path}\n       汇总 {report_path}")


if __name__ == "__main__":
    main()
