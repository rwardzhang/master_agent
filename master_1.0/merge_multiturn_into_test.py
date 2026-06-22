# -*- coding: utf-8 -*-
"""
将多轮测试语料 (openai_test_multiturn.jsonl) 合并进现有单轮测试集 (openai_train_split_from_ma1_test.jsonl)，
并重新生成同名 xlsx（MA_1.0_test.xlsx），使其同时包含单轮与多轮样本。

行为：
1. 读取原测试 jsonl 与多轮 jsonl，校验各自合法性
2. 拼接为新的合并 jsonl，覆盖写回 openai_train_split_from_ma1_test.jsonl
   （原文件已由调用方备份为 .bak.jsonl）
3. 基于合并后数据重新生成 MA_1.0_test.xlsx；
   - 单轮：query 列 = 该条 user 内容
   - 多轮：query 列 = "user:...\\nassistant:...\\nuser:..." 还原串
4. 打印合并前后统计

用法：
    python3 merge_multiturn_into_test.py
"""

import os
import json
from collections import defaultdict, Counter

import pandas as pd


SINGLE_TURN_TEST = "/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/openai_train_split_from_ma1_test.jsonl"
MULTITURN_JSONL  = "/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/openai_test_multiturn.jsonl"
OUT_XLSX         = "/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/MA_1.0_test.xlsx"

VALID_LABELS = {
    "food", "puscene", "meituan", "luckin", "maoyan", "tc_travel",
    "music", "podcast", "news", "travel_plan", "chat", "starbucks",
    "sights", "video", "car_control",
}

XLSX_COLUMNS = ["from", "query", "intent", "entity", "is_car_control", "m_intent"]


def load_jsonl(path: str):
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def messages_to_query_str(messages):
    """
    把 messages（去掉首部 system 与末尾 assistant 标签）还原成 xlsx 的 query 字符串。
    单轮：直接返回最后一句 user 的内容
    多轮：拼接成 "user:...\\nassistant:...\\nuser:..."
    """
    convo = messages[1:-1]
    n_user = sum(1 for m in convo if m["role"] == "user")
    if n_user <= 1:
        for m in convo:
            if m["role"] == "user":
                return m["content"]
        return ""
    return "\n".join(f"{m['role']}:{m['content']}" for m in convo)


def main():
    print(f"📂 读取单轮测试集: {SINGLE_TURN_TEST}")
    single_items = load_jsonl(SINGLE_TURN_TEST)
    print(f"   {len(single_items)} 条")

    # 防御性检查：如果原文件已经包含多轮（说明此前已合并过），先去掉旧的多轮再重新合并
    n_multi_in_single = 0
    pure_single = []
    for it in single_items:
        convo = it["messages"][1:-1]
        n_user = sum(1 for m in convo if m["role"] == "user")
        if n_user > 1:
            n_multi_in_single += 1
        else:
            pure_single.append(it)
    if n_multi_in_single > 0:
        print(f"   ⚠️  原文件已含 {n_multi_in_single} 条多轮，将剔除后重新合并以保持幂等")
        single_items = pure_single

    print(f"📂 读取多轮测试集: {MULTITURN_JSONL}")
    multi_items = load_jsonl(MULTITURN_JSONL)
    print(f"   {len(multi_items)} 条")

    # ===== 合并 =====
    merged = single_items + multi_items
    print(f"\n🔗 合并后: {len(merged)} 条 (单轮 {len(single_items)} + 多轮 {len(multi_items)})")

    # ===== 写回 jsonl =====
    with open(SINGLE_TURN_TEST, "w", encoding="utf-8") as f:
        for it in merged:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    print(f"📤 已覆盖写入: {SINGLE_TURN_TEST}")

    # ===== 重新生成 xlsx（按 intent 分 Sheet，多轮兼容） =====
    grouped = defaultdict(list)
    label_total = Counter()
    label_multi = Counter()

    for it in merged:
        msgs = it["messages"]
        label = msgs[-1]["content"].strip()
        if not label:
            continue
        convo = msgs[1:-1]
        n_user = sum(1 for m in convo if m["role"] == "user")
        query_str = messages_to_query_str(msgs)
        grouped[label].append({
            "from": "",
            "query": query_str,
            "intent": label,
            "entity": "",
            "is_car_control": "",
            "m_intent": "" if n_user <= 1 else f"multi_turn|user_turns={n_user}",
        })
        label_total[label] += 1
        if n_user > 1:
            label_multi[label] += 1

    unknown = [k for k in grouped if k not in VALID_LABELS]
    if unknown:
        print(f"⚠️  发现未知标签（仍写入）: {unknown}")

    ordered = sorted(grouped.items(), key=lambda x: -len(x[1]))
    os.makedirs(os.path.dirname(OUT_XLSX) or ".", exist_ok=True)
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        for intent, rows in ordered:
            df = pd.DataFrame(rows, columns=XLSX_COLUMNS)
            sheet_name = str(intent)[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    print(f"📤 已重写 xlsx : {OUT_XLSX}")

    # ===== 统计 =====
    print("\n=== 合并后标签分布 (总/多轮) ===")
    for lbl, c in label_total.most_common():
        print(f"  {lbl:12s} {c:5d}  multi={label_multi.get(lbl, 0)}")
    print(f"\n合计: {sum(label_total.values())} 条，其中多轮 {sum(label_multi.values())} 条 "
          f"({sum(label_multi.values())/sum(label_total.values())*100:.1f}%)")


if __name__ == "__main__":
    main()
