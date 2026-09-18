#!/usr/bin/env python3
"""在训练集里检索与给定 query 最相似的已标注样本，用于「照抄同句先例」。

用法:
  python3 find_similar.py "今天星期几"
  python3 find_similar.py "播放轻松的音乐" --domain 音乐
  python3 find_similar.py --file queries.txt --topk 8
  python3 find_similar.py --jsonl confirmed.jsonl        # 批量：对文件里每条的 last_user 检索

相似度：last_user 的字符 3-gram Jaccard。
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

DEFAULT_TRAIN = os.environ.get(
    "WECAR_FC_TRAIN",
    "/Users/rwardzhang/PycharmProjects/wecar_agent/api_agent/train_dataset/"
    "log_annotation_pipeline/runs/webtest/final/train_fc_data_2026.08.24_v3.jsonl",
)

DOM_ALIAS = {
    "出行": "出行工具选择", "travel": "出行工具选择",
    "地点": "地点工具选择", "poi": "地点工具选择",
    "音乐": "音乐工具选择", "music": "音乐工具选择",
    "新闻": "新闻工具选择", "news": "新闻工具选择",
    "speech": "speech工具选择", "语音": "speech工具选择",
    "信息查询": "信息查询工具选择", "info_query": "信息查询工具选择",
    "影院电影": "影院电影工具选择", "video": "影院电影工具选择", "电影": "影院电影工具选择",
}


def grams(s, n=3):
    s = re.sub(r"\s+", "", s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def last_user(text):
    lines = [x for x in text.strip().split("\n") if x.strip()]
    for x in reversed(lines):
        m = re.match(r"^user:?\s*(.*)$", x.strip())
        if m and m.group(1).strip():
            return m.group(1).strip()
    return lines[-1] if lines else ""


def dom_of(sysc):
    m = re.match(r"你是一个(.+?)(助手|专家)", sysc)
    return m.group(1) if m else None


def load_index(train_path):
    idx = defaultdict(list)  # domain -> [(last_user, gt, grams)]
    for line in open(train_path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        sysc = d["messages"][0]["content"]
        if "工具与参数" not in sysc:      # 跳过非 FC 域（如 Query 改写）
            continue
        dn = dom_of(sysc)
        if not dn:
            continue
        lu = last_user(d["messages"][1]["content"])
        idx[dn].append((lu, d["messages"][2]["content"], grams(lu)))
    return idx


def search(idx, query, domain=None, topk=6):
    g = grams(query)
    pools = [(domain, idx[domain])] if domain else list(idx.items())
    out = []
    for dn, pool in pools:
        for lu, gt, tg in pool:
            inter = len(g & tg)
            if not inter:
                continue
            out.append((inter / len(g | tg), dn, lu, gt))
    out.sort(reverse=True)
    # 同 (last_user, gt) 去重
    seen, res = set(), []
    for s, dn, lu, gt in out:
        k = (lu, gt)
        if k in seen:
            continue
        seen.add(k)
        res.append((s, dn, lu, gt))
        if len(res) >= topk:
            break
    return res


def report(idx, query, domain, topk):
    res = search(idx, query, domain, topk)
    print(f"\n【query】{query}" + (f"   [域={domain}]" if domain else "   [全域]"))
    if not res:
        print("    (无相似样本 —— 属于训练集未覆盖形态，需人工按域规则判定)")
        return
    exact = [r for r in res if r[0] >= 0.95]
    if exact:
        print("    >>> 命中同句先例，直接照抄：")
        for s, dn, lu, gt in exact:
            print(f"        [{s:.2f}] ({dn}) {lu}  ->  {gt}")
    for s, dn, lu, gt in res:
        if s >= 0.95:
            continue
        print(f"    [{s:.2f}] ({dn}) {lu[:48]:<50} -> {gt[:52]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", help="要检索的 query 文本")
    ap.add_argument("--domain", "-d", help="限定域（出行/地点/音乐/新闻/speech/信息查询/影院电影）")
    ap.add_argument("--topk", "-k", type=int, default=6)
    ap.add_argument("--file", "-f", help="批量：每行一个 query 的纯文本文件")
    ap.add_argument("--jsonl", "-j", help="批量：jsonl 文件，对每条 messages[1] 的 last_user 检索")
    ap.add_argument("--train", default=DEFAULT_TRAIN, help="训练集路径")
    args = ap.parse_args()

    if not os.path.exists(args.train):
        sys.exit(f"[FATAL] 训练集不存在: {args.train}\n        用 --train 指定，或设 WECAR_FC_TRAIN 环境变量")

    dom = DOM_ALIAS.get(args.domain, args.domain) if args.domain else None
    idx = load_index(args.train)
    if dom and dom not in idx:
        sys.exit(f"[FATAL] 未知域 {dom}，可选: {sorted(idx)}")
    print(f"索引: {sum(len(v) for v in idx.values())} 条 / {len(idx)} 域")

    if args.jsonl:
        for line in open(args.jsonl, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            q = d.get("last_user") or last_user(
                d.get("user") or d["messages"][1]["content"])
            dn = DOM_ALIAS.get(d.get("domain", ""), dom)
            report(idx, q, dn if dn in idx else None, args.topk)
    elif args.file:
        for q in open(args.file, encoding="utf-8"):
            q = q.strip()
            if q:
                report(idx, q, dom, args.topk)
    elif args.query:
        report(idx, args.query, dom, args.topk)
    else:
        ap.error("需要提供 query，或 --file / --jsonl")


if __name__ == "__main__":
    main()
