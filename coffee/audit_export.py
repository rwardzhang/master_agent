#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把审计结果写到 xlsx，避免终端乱码看不清。"""
import json
from collections import Counter, defaultdict
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

PATH = "/Users/rwardzhang/PycharmProjects/master_agent_qc/coffee/coffee_train.jsonl"
OUT = "/Users/rwardzhang/PycharmProjects/master_agent_qc/coffee/coffee_train_audit.xlsx"
VALID = {"luckin", "starbucks", "meituan", "clarify", "whatever", "terminate", "other"}

label_cnt = Counter()
sus_lucky = []
luckin_query_dup = defaultdict(list)
target_hits = []
all_lucky_q = []

with open(PATH, "r", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        d = json.loads(line)
        msgs = d["messages"]
        label = msgs[-1]["content"].strip()
        user_q = ""
        for m in reversed(msgs):
            if m["role"] == "user":
                c = m["content"]
                user_q = c if isinstance(c, str) else c[0].get("text", "")
                break
        label_cnt[label] += 1
        if "lucky" in (label + user_q).lower():
            sus_lucky.append((i, user_q, label))
        luckin_query_dup[user_q].append((i, label))
        if "瑞幸咖啡" in user_q or "点一杯瑞幸" in user_q:
            target_hits.append((i, user_q, label))
        if "luckin" in label and ("瑞幸" in user_q or "luckin" in user_q.lower()):
            all_lucky_q.append((i, user_q, label))

wb = Workbook()

# Sheet1: 标签分布
ws1 = wb.active
ws1.title = "标签分布"
ws1.append(["标签", "条数", "是否合法"])
for k, v in label_cnt.most_common():
    ws1.append([k, v, "✅" if k in VALID else "⚠️ 非法"])
ws1.append(["合计", sum(label_cnt.values()), ""])

# Sheet2: lucky 字样样本
ws2 = wb.create_sheet("lucky字样")
ws2.append(["行号", "user query", "label"])
for r in sus_lucky:
    ws2.append(list(r))
if not sus_lucky:
    ws2.append(["-", "训练集中完全没有 lucky 字样", "-"])

# Sheet3: 同 query 不同 label 冲突
ws3 = wb.create_sheet("query冲突")
ws3.append(["user query", "label1", "label2", "出现次数"])
conflicts = {q: labs for q, labs in luckin_query_dup.items() if len({lab for _, lab in labs}) > 1}
for q, labs in sorted(conflicts.items(), key=lambda x: -len(x[1])):
    cnt = Counter(lab for _, lab in labs)
    keys = list(cnt.keys())
    ws3.append([q, f"{keys[0]}({cnt[keys[0]]})",
                f"{keys[1]}({cnt[keys[1]]})" if len(keys) > 1 else "",
                len(labs)])

# Sheet4: 「点一杯瑞幸咖啡」相关
ws4 = wb.create_sheet("瑞幸咖啡相关")
ws4.append(["行号", "user query", "label"])
for r in target_hits:
    ws4.append(list(r))

# Sheet5: 所有 luckin 标签的 query (前200)
ws5 = wb.create_sheet("luckin样本前200")
ws5.append(["行号", "user query", "label"])
for r in all_lucky_q[:200]:
    ws5.append(list(r))

# 统一样式
for ws in wb.worksheets:
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2E75B6")
    for c in ws[1]:
        c.font = header_font
        c.fill = header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
    for col_idx, col in enumerate(ws.columns, start=1):
        ws.column_dimensions[get_column_letter(col_idx)].width = max(12, min(60, max((len(str(c.value or "")) for c in col), default=12) + 2))
    ws.freeze_panes = "A2"

wb.save(OUT)
print(f"OUT: {OUT}")
print(f"label distribution: {dict(label_cnt)}")
print(f"lucky entries: {len(sus_lucky)}")
print(f"query conflicts: {len(conflicts)}")
print(f"瑞幸咖啡 hits: {len(target_hits)}")
