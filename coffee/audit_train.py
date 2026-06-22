#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审计 coffee_train.jsonl：定位 lucky 输出根因。"""
import json
import re
from collections import Counter, defaultdict

PATH = "/Users/rwardzhang/PycharmProjects/master_agent_qc/coffee/coffee_train.jsonl"
VALID = {"luckin", "starbucks", "meituan", "clarify", "whatever", "terminate", "other"}

label_cnt = Counter()
bad_label = []           # label 不在 VALID
sus_lucky = []           # query 或 label 含 lucky
luckin_examples = []     # 抽样看 luckin 训练样本是否一致
luckin_query_dup = defaultdict(list)  # 同 query 不同 label 检测

with open(PATH, "r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        d = json.loads(line)
        msgs = d["messages"]
        label = msgs[-1]["content"].strip()
        # 取最后一个 user query
        user_q = ""
        for m in reversed(msgs):
            if m["role"] == "user":
                c = m["content"]
                user_q = c if isinstance(c, str) else c[0].get("text", "")
                break

        label_cnt[label] += 1
        if label not in VALID:
            bad_label.append((i, user_q, label))
        if "lucky" in label.lower() or "lucky" in user_q.lower():
            sus_lucky.append((i, user_q, label))
        if label == "luckin" and len(luckin_examples) < 5:
            luckin_examples.append((i, user_q, label))
        # 同 query 不同 label
        luckin_query_dup[user_q].append(label)

print("=" * 70)
print("【1】标签分布")
print("=" * 70)
for k, v in label_cnt.most_common():
    flag = "" if k in VALID else "  ⚠️ 非法标签"
    print(f"  {v:>5}  {k!r}{flag}")
print(f"  合计: {sum(label_cnt.values())}")

print()
print("=" * 70)
print("【2】非法标签样本")
print("=" * 70)
if not bad_label:
    print("  ✅ 无非法标签")
else:
    for i, q, lab in bad_label[:20]:
        print(f"  line {i}: label={lab!r}  query={q!r}")
    print(f"  ...共 {len(bad_label)} 条非法")

print()
print("=" * 70)
print("【3】出现 lucky 字样的样本（query 或 label）")
print("=" * 70)
if not sus_lucky:
    print("  ✅ 训练集中完全没有 lucky 字样")
else:
    for i, q, lab in sus_lucky[:30]:
        print(f"  line {i}: label={lab!r}  query={q!r}")
    print(f"  ...共 {len(sus_lucky)} 条")

print()
print("=" * 70)
print("【4】抽样 5 条 luckin 样本（看 user query 是否合理）")
print("=" * 70)
for i, q, lab in luckin_examples:
    print(f"  line {i}: {q!r} -> {lab}")

print()
print("=" * 70)
print("【5】同 query 不同 label 的冲突样本")
print("=" * 70)
conflicts = {q: labs for q, labs in luckin_query_dup.items() if len(set(labs)) > 1}
if not conflicts:
    print("  ✅ 无 query 标签冲突")
else:
    for q, labs in list(conflicts.items())[:20]:
        print(f"  {q!r} -> {Counter(labs).most_common()}")
    print(f"  ...共 {len(conflicts)} 个冲突 query")

print()
print("=" * 70)
print("【6】「点一杯瑞幸咖啡」相关样本")
print("=" * 70)
target_keywords = ["瑞幸咖啡", "点一杯瑞幸"]
hit = []
with open(PATH, "r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        d = json.loads(line)
        msgs = d["messages"]
        for m in msgs:
            if m["role"] == "user":
                c = m["content"]
                user_q = c if isinstance(c, str) else c[0].get("text", "")
                if any(k in user_q for k in target_keywords):
                    hit.append((i, user_q, msgs[-1]["content"].strip()))
                    break
print(f"  命中 {len(hit)} 条")
for i, q, lab in hit[:30]:
    print(f"  line {i}: {q!r} -> {lab}")
