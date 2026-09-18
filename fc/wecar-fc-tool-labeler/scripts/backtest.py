#!/usr/bin/env python3
"""回测 label.py 的判定准确率（留一法，用训练集自身做 ground truth）。

用法:
  python3 backtest.py                    # 默认抽样 1200 条
  python3 backtest.py -n 3000            # 更大样本
  python3 backtest.py --domain 音乐       # 只测单域
  python3 backtest.py --show-errors 20   # 打印错误明细

改了 label.py 的 RULES 或 LIST_PAT 之后必跑一次，确认没有回退。
基线：1200 条抽样，工具名准确率 98.75%（EXACT 层 99.1%）。
"""
import argparse
import importlib.util
import json
import os
import random
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TRAIN = os.environ.get(
    "WECAR_FC_TRAIN",
    "/Users/rwardzhang/PycharmProjects/wecar_agent/api_agent/train_dataset/"
    "log_annotation_pipeline/runs/webtest/final/train_fc_data_2026.08.24_v3.jsonl",
)

DOM_ALIAS = {
    "出行": "出行工具选择", "地点": "地点工具选择", "音乐": "音乐工具选择",
    "新闻": "新闻工具选择", "speech": "speech工具选择",
    "信息查询": "信息查询工具选择", "影院电影": "影院电影工具选择",
}


def load_labeler():
    spec = importlib.util.spec_from_file_location("lb", os.path.join(HERE, "label.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=1200, help="抽样条数")
    ap.add_argument("--domain", "-d")
    ap.add_argument("--show-errors", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--train", default=DEFAULT_TRAIN)
    args = ap.parse_args()

    if not os.path.exists(args.train):
        sys.exit(f"[FATAL] 训练集不存在: {args.train}")
    lb = load_labeler()

    rows = [json.loads(l) for l in open(args.train, encoding="utf-8") if l.strip()]
    fc = [r for r in rows if "工具与参数" in r["messages"][0]["content"]]
    dom = DOM_ALIAS.get(args.domain, args.domain) if args.domain else None
    if dom:
        fc = [r for r in fc if lb.dom_of(r["messages"][0]["content"]) == dom]
    random.seed(args.seed)
    sample = random.sample(fc, min(args.n, len(fc)))

    idx = lb.load_index(args.train)
    ok = 0
    cs = Counter()
    err = defaultdict(Counter)
    err_ex = []
    for r in sample:
        dn = lb.dom_of(r["messages"][0]["content"])
        q = lb.last_user(r["messages"][1]["content"])
        ctx = r["messages"][1]["content"]
        conf, pred, why, _ = lb.suggest(idx, q, dn, lb.has_domain_list(ctx))
        gold = r["messages"][2]["content"].split("|")[0]
        good = pred == gold
        cs[(conf, good)] += 1
        if good:
            ok += 1
        else:
            err[dn][(gold, pred)] += 1
            if len(err_ex) < args.show_errors:
                err_ex.append((dn, q, gold, pred, conf, why))

    n = len(sample)
    print(f"=== 回测 {n} 条{'（域=' + dom + '）' if dom else ''} ===")
    print(f"工具名准确率: {ok}/{n} = {ok/n*100:.2f}%")
    print("\n按置信度分层:")
    for c in ("EXACT", "RULE", "NEAR", "MANUAL"):
        t, f = cs[(c, True)], cs[(c, False)]
        if t + f:
            print(f"  {c:<7} n={t+f:<5} 覆盖 {(t+f)/n*100:5.1f}%   准确 {t/(t+f)*100:5.1f}%")
    print("\n错误分布:")
    for dn, c in sorted(err.items(), key=lambda x: -sum(x[1].values())):
        print(f"  【{dn}】{sum(c.values())} 条")
        for (g, p), k in c.most_common(5):
            print(f"      {k:>3}  gold={g} -> pred={p}")
    if err_ex:
        print("\n错误明细:")
        for dn, q, g, p, conf, why in err_ex:
            print(f"  [{dn}] {q[:40]}")
            print(f"      gold={g}  pred={p}  ({conf}) {why[:70]}")


if __name__ == "__main__":
    main()
