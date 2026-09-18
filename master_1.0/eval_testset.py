#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
意图分类模型测试集评测脚本

- 读取 test.jsonl（每行 messages = system + user + assistant(真值)）
- 对每条用其自带 system + user 调用推理服务
- 并发请求，统计总体准确率、各标签 P/R/F1、混淆矩阵
- 输出 Markdown 报告 + 错误明细 CSV + 原始预测 JSONL
"""

import argparse
import csv
import json
import os
import re
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import urllib.request
import urllib.error

# ----------------------- 配置 -----------------------
API_URL = "https://ms-sppb89td-100043908827-sw.gw.ap-guangzhou.ti.tencentcs.com/ms-sppb89td/v1/chat/completions"
AUTH = "da30c185db3bf9f"
MODEL = "zc-intent"

# 全部合法标签（用于归一化/校验，超出该集合的输出记为 __invalid__）
VALID_LABELS = {
    "food", "puscene", "meituan", "luckin", "maoyan", "tc_travel",
    "music", "podcast", "news", "travel_plan", "chat", "starbucks",
    "sights", "video", "car_control", "miniprogram", "retail",
}


def extract_user_text(content):
    """user content 可能是 str 或 [{'type':'text','text':...}]，统一取文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for seg in content:
            if isinstance(seg, dict) and seg.get("type") == "text":
                parts.append(seg.get("text", ""))
            elif isinstance(seg, str):
                parts.append(seg)
        return "".join(parts)
    return str(content)


def normalize_label(raw):
    """把模型输出归一化成合法标签；无法匹配返回 __invalid__。"""
    if raw is None:
        return "__invalid__"
    s = raw.strip()
    # 去掉可能的引号/标点/空白
    s = re.sub(r'["\'` \t\r\n。，,.!！]+', "", s)
    if s in VALID_LABELS:
        return s
    # 容错：输出里包含某个标签词
    for lab in VALID_LABELS:
        if lab in s:
            return lab
    return "__invalid__"


def build_payload(system_content, user_text):
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": [{"type": "text", "text": user_text}]},
        ],
        "chat_template_kwargs": {"enable_thinking": False},
    }


def call_api(payload, timeout=60, retries=3, backoff=1.5):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                API_URL, data=data, method="POST",
                headers={"Authorization": AUTH, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
            obj = json.loads(body)
            content = obj["choices"][0]["message"]["content"]
            return content, None
        except Exception as e:  # noqa
            last_err = e
            time.sleep(backoff * (attempt + 1))
    return None, str(last_err)


def load_dataset(path):
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msgs = obj.get("messages", [])
            system_content = ""
            user_text = ""
            gold = ""
            for m in msgs:
                role = m.get("role")
                if role == "system":
                    system_content = m.get("content", "")
                elif role == "user":
                    user_text = extract_user_text(m.get("content", ""))
                elif role == "assistant":
                    gold = extract_user_text(m.get("content", "")).strip()
            items.append({
                "idx": line_no,
                "system": system_content,
                "user": user_text,
                "gold": gold,
            })
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="test.jsonl")
    ap.add_argument("--outdir", default="eval_output")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--limit", type=int, default=0, help="只跑前N条，0=全部")
    args = ap.parse_args()

    src = Path(args.input)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    items = load_dataset(src)
    if args.limit > 0:
        items = items[: args.limit]
    total = len(items)
    print(f"[load] {total} samples from {src}")

    results = [None] * total
    done = {"n": 0, "err": 0}
    lock = threading.Lock()
    t0 = time.time()

    def worker(i, item):
        payload = build_payload(item["system"], item["user"])
        content, err = call_api(payload)
        pred = normalize_label(content)
        rec = {
            "idx": item["idx"],
            "user": item["user"],
            "gold": item["gold"],
            "raw": content if content is not None else "",
            "pred": pred,
            "error": err or "",
            "correct": int(pred == item["gold"]),
        }
        with lock:
            done["n"] += 1
            if err:
                done["err"] += 1
            if done["n"] % 200 == 0 or done["n"] == total:
                el = time.time() - t0
                rate = done["n"] / el if el > 0 else 0
                print(f"[progress] {done['n']}/{total}  err={done['err']}  {rate:.1f}/s")
        return i, rec

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(worker, i, it) for i, it in enumerate(items)]
        for fut in as_completed(futs):
            i, rec = fut.result()
            results[i] = rec

    elapsed = time.time() - t0
    print(f"[done] {total} samples in {elapsed:.1f}s")

    # 保存原始预测
    pred_path = outdir / "predictions.jsonl"
    with open(pred_path, "w", encoding="utf-8") as f:
        for rec in results:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # ---------------- 指标计算 ----------------
    labels = sorted(VALID_LABELS)
    n_correct = sum(r["correct"] for r in results)
    n_error = sum(1 for r in results if r["error"])
    n_invalid = sum(1 for r in results if r["pred"] == "__invalid__")
    accuracy = n_correct / total if total else 0.0

    tp = Counter()
    fp = Counter()
    fn = Counter()
    support = Counter()
    confusion = defaultdict(Counter)  # gold -> pred -> count

    for r in results:
        g, p = r["gold"], r["pred"]
        support[g] += 1
        confusion[g][p] += 1
        if p == g:
            tp[g] += 1
        else:
            fp[p] += 1
            fn[g] += 1

    per_label = {}
    macro_p = macro_r = macro_f1 = 0.0
    valid_label_count = 0
    for lab in labels:
        s = support[lab]
        prec = tp[lab] / (tp[lab] + fp[lab]) if (tp[lab] + fp[lab]) else 0.0
        rec_ = tp[lab] / (tp[lab] + fn[lab]) if (tp[lab] + fn[lab]) else 0.0
        f1 = 2 * prec * rec_ / (prec + rec_) if (prec + rec_) else 0.0
        per_label[lab] = {"precision": prec, "recall": rec_, "f1": f1, "support": s, "correct": tp[lab]}
        if s > 0:
            macro_p += prec
            macro_r += rec_
            macro_f1 += f1
            valid_label_count += 1
    if valid_label_count:
        macro_p /= valid_label_count
        macro_r /= valid_label_count
        macro_f1 /= valid_label_count

    # 错误明细
    err_path = outdir / "errors.csv"
    with open(err_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["idx", "gold", "pred", "raw", "user", "api_error"])
        for r in results:
            if r["correct"] == 0:
                w.writerow([r["idx"], r["gold"], r["pred"], r["raw"],
                            r["user"].replace("\n", " / "), r["error"]])

    # ---------------- Markdown 报告 ----------------
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append(f"# 意图分类模型测试集评测报告\n")
    lines.append(f"- 模型：`{MODEL}`")
    lines.append(f"- 测试集：`{src.name}`")
    lines.append(f"- 评测时间：{ts}")
    lines.append(f"- 耗时：{elapsed:.1f}s（{args.workers} 并发）\n")

    lines.append("## 总体指标\n")
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append(f"| 样本总数 | {total} |")
    lines.append(f"| 预测正确 | {n_correct} |")
    lines.append(f"| **准确率 Accuracy** | **{accuracy:.4f}（{accuracy*100:.2f}%）** |")
    lines.append(f"| Macro-Precision | {macro_p:.4f} |")
    lines.append(f"| Macro-Recall | {macro_r:.4f} |")
    lines.append(f"| Macro-F1 | {macro_f1:.4f} |")
    lines.append(f"| API 请求失败 | {n_error} |")
    lines.append(f"| 非法/越界输出 | {n_invalid} |")
    lines.append("")

    lines.append("## 各标签指标（按 support 降序）\n")
    lines.append("| 标签 | Precision | Recall | F1 | 正确/总数 |")
    lines.append("| --- | --- | --- | --- | --- |")
    for lab in sorted(labels, key=lambda x: -per_label[x]["support"]):
        m = per_label[lab]
        if m["support"] == 0:
            continue
        lines.append(f"| {lab} | {m['precision']:.4f} | {m['recall']:.4f} | {m['f1']:.4f} | {m['correct']}/{m['support']} |")
    lines.append("")

    # 最易混淆 TopN
    lines.append("## 主要混淆对（gold → pred，Top 20）\n")
    conf_pairs = []
    for g in confusion:
        for p, c in confusion[g].items():
            if g != p and c > 0:
                conf_pairs.append((g, p, c))
    conf_pairs.sort(key=lambda x: -x[2])
    lines.append("| 真值 gold | 误判为 pred | 次数 |")
    lines.append("| --- | --- | --- |")
    for g, p, c in conf_pairs[:20]:
        lines.append(f"| {g} | {p} | {c} |")
    lines.append("")

    # 完整混淆矩阵
    lines.append("## 混淆矩阵（行=真值，列=预测）\n")
    used_preds = set()
    for g in confusion:
        used_preds.update(confusion[g].keys())
    col_labels = [l for l in labels if l in used_preds]
    if any(confusion[g].get("__invalid__", 0) for g in confusion):
        col_labels.append("__invalid__")
    header = "| gold\\pred | " + " | ".join(col_labels) + " |"
    sep = "| --- |" + " --- |" * len(col_labels)
    lines.append(header)
    lines.append(sep)
    for g in sorted(labels, key=lambda x: -per_label[x]["support"]):
        if per_label[g]["support"] == 0:
            continue
        row = [f"| **{g}** "]
        for p in col_labels:
            c = confusion[g].get(p, 0)
            cell = f"| {c} " if c == 0 else (f"| **{c}** " if p == g else f"| {c} ")
            row.append(cell)
        row.append("|")
        lines.append("".join(row))
    lines.append("")

    lines.append("## 产物文件\n")
    lines.append(f"- `predictions.jsonl`：全部 {total} 条原始预测")
    lines.append(f"- `errors.csv`：{total - n_correct} 条错误明细（gold/pred/user/原始输出）")
    lines.append("")

    report_path = outdir / "eval_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"[report] {report_path}")
    print(f"[report] accuracy={accuracy:.4f} macro-f1={macro_f1:.4f}")


if __name__ == "__main__":
    main()
