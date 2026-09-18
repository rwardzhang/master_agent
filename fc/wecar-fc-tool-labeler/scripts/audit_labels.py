#!/usr/bin/env python3
"""FC 标注质量门禁：对标注结果做 6 层校验，全部规则从训练集自动生成，不硬编码白名单。

用法:
  python3 audit_labels.py <待检jsonl>
  python3 audit_labels.py <待检jsonl> --train <训练集> --csv errors.csv

检查层：
  A 格式层  role序列 / assistant非空 / 无前后空白 / 无换行 / 无think / 分隔符无空格
  B 合法层  工具名必须在该条 system 现场声明的工具清单内（正则从 system 提取，不用独立白名单）
  C arity   参数个数须等于训练集该工具的标准 arity
  D 枚举层  枚举位取值须在训练集已有集合内
  E 一致层  同一 (system, last_user) 在本批内不得给出两种标注
  F 查重    与训练集做 system+user 签名比对
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict

DEFAULT_TRAIN = os.environ.get(
    "WECAR_FC_TRAIN",
    "/Users/rwardzhang/PycharmProjects/wecar_agent/api_agent/train_dataset/"
    "log_annotation_pipeline/runs/webtest/final/train_fc_data_2026.08.24_v3.jsonl",
)


def last_user(text):
    lines = [x for x in text.strip().split("\n") if x.strip()]
    for x in reversed(lines):
        m = re.match(r"^user:?\s*(.*)$", x.strip())
        if m and m.group(1).strip():
            return m.group(1).strip()
    return lines[-1] if lines else ""


def tools_in_system(sysc):
    """从 system prompt 现场解析声明的工具名 —— 绝不用独立硬编码白名单。"""
    return set(re.findall(r"^([a-z_]+)（", sysc, re.M))


def build_ref(train_path):
    """从训练集生成 arity 标准与枚举域。"""
    arity = defaultdict(Counter)
    vals = defaultdict(lambda: defaultdict(Counter))
    sig = set()
    for line in open(train_path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        ms = d["messages"]
        if "工具与参数" not in ms[0]["content"]:
            continue
        sig.add((ms[0]["content"], ms[1]["content"]))
        parts = ms[2]["content"].split("|")
        t = parts[0]
        arity[t][len(parts) - 1] += 1
        for i, v in enumerate(parts[1:]):
            vals[t][i][v] += 1
    std_arity = {t: c.most_common(1)[0][0] for t, c in arity.items()}
    enum = {}
    for t, pos in vals.items():
        for i, c in pos.items():
            if len(c) <= 8:                 # 取值种类 <=8 视为枚举位
                enum[(t, i)] = set(c)
    return std_arity, enum, sig, arity


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--train", default=DEFAULT_TRAIN)
    ap.add_argument("--csv", help="把问题导出为 CSV")
    args = ap.parse_args()

    if not os.path.exists(args.train):
        sys.exit(f"[FATAL] 训练集不存在: {args.train}")

    std_arity, enum, train_sig, arity_raw = build_ref(args.train)
    rows = [json.loads(l) for l in open(args.src, encoding="utf-8") if l.strip()]
    print(f"待检 {len(rows)} 条  |  参考训练集 {len(train_sig)} 个唯一签名")

    issues = []                             # (level, code, line, detail)
    seen = defaultdict(list)                # (sysc, lu) -> [gt]

    for i, d in enumerate(rows, 1):
        ms = d.get("messages")
        if not ms:
            issues.append(("A", "A0-缺messages", i, ""))
            continue
        roles = tuple(m.get("role") for m in ms)
        if roles != ("system", "user", "assistant"):
            issues.append(("A", "A1-role序列", i, str(roles)))
            continue
        sysc, userc, gt = ms[0]["content"], ms[1]["content"], ms[2]["content"]

        # --- A 格式层 ---
        if not gt.strip():
            issues.append(("A", "A2-assistant为空", i, ""))
            continue
        if gt != gt.strip():
            issues.append(("A", "A3-前后空白", i, repr(gt[:40])))
        if "\n" in gt:
            issues.append(("A", "A4-含换行", i, repr(gt[:40])))
        if "<think>" in gt or "</think>" in gt:
            issues.append(("A", "A5-think标签", i, repr(gt[:60])))
        if " |" in gt or "| " in gt:
            issues.append(("A", "A6-分隔符空格", i, repr(gt[:50])))
        if not userc.strip():
            issues.append(("A", "A7-user为空", i, ""))

        parts = [x.strip() for x in gt.split("|")]
        tool = parts[0]

        # --- B 合法层：从 system 现场解析 ---
        declared = tools_in_system(sysc)
        if declared and tool not in declared:
            issues.append(("B", "B1-工具未在system声明", i,
                           f"{tool} 不在 {sorted(declared)}"))

        # --- C arity ---
        exp = std_arity.get(tool)
        if exp is not None and len(parts) - 1 != exp:
            issues.append(("C", "C1-参数个数不符", i,
                           f"{tool} 期望{exp}个 实际{len(parts)-1}个: {gt[:50]}"))

        # --- D 枚举 ---
        for j, v in enumerate(parts[1:]):
            dom = enum.get((tool, j))
            if dom and v not in dom:
                issues.append(("D", "D1-枚举值越界", i,
                               f"{tool}[{j}]={v!r} 不在 {sorted(dom)}"))

        # --- E 一致性 ---
        seen[(sysc, last_user(userc))].append((i, gt))

        # --- F 查重 ---
        if (sysc, userc) in train_sig:
            issues.append(("F", "F1-与训练集重复", i, last_user(userc)[:50]))

    for (sysc, lu), items in seen.items():
        gts = {g for _, g in items}
        if len(gts) > 1:
            issues.append(("E", "E1-同query多标注", items[0][0],
                           f"{lu[:36]!r} -> {sorted(gts)}"))

    print("\n=== 问题汇总 ===")
    if not issues:
        print("  无问题 ✅")
    else:
        for code, n in Counter(x[1] for x in issues).most_common():
            print(f"  {n:>4}  {code}")
        print("\n=== 明细（前 40 条）===")
        for lv, code, ln, det in issues[:40]:
            print(f"  [{code}] 第{ln}行  {det}")

    if args.csv and issues:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["level", "code", "line", "detail"])
            w.writerows(issues)
        print(f"\n已导出 -> {args.csv}")

    # 长度提示（cutoff_len）
    good = [r for r in rows if r.get("messages") and len(r["messages"]) == 3]
    if good:
        L = sorted(sum(len(m["content"]) for m in r["messages"]) for r in good)
        tok = int(L[-1] / 1.6)
        print(f"\n总字符 min/P50/P90/max: {L[0]}/{L[len(L)//2]}/{L[int(len(L)*.9)]}/{L[-1]}"
              f"  -> max ≈ {tok} token，cutoff_len 建议 ≥ {max(2048, 1 << (tok-1).bit_length())}")

    sys.exit(1 if any(x[0] in "ABC" for x in issues) else 0)


if __name__ == "__main__":
    main()
