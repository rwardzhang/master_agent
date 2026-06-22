# -*- coding: utf-8 -*-
"""
将 openai_train_split_from_ma1*.jsonl 反向转换为 xlsx 文件

输出格式（参考用户给定截图）：
- 按 intent（意图标签）拆分为多个 Sheet
- 每个 Sheet 表头：from / query / intent / entity / is_car_control / m_intent
- 不带序号列
- query 列即原 jsonl 中 user 消息的 content
- intent 列即原 jsonl 中 assistant 消息的 content
- 其它列（from / entity / is_car_control / m_intent）默认留空，可在后续人工标注或脚本补全

用法：
    python3 jsonl_to_xlsx.py
    python3 jsonl_to_xlsx.py -i 输入.jsonl -o 输出.xlsx
"""

import os
import json
import argparse
from collections import defaultdict

import pandas as pd


# 输出表头（与图片一致）
COLUMNS = ["from", "query", "intent", "entity", "is_car_control", "m_intent"]

# 合法标签集合
VALID_LABELS = {
    "food", "puscene", "meituan", "luckin", "maoyan", "tc_travel",
    "music", "podcast", "news", "travel_plan", "chat", "starbucks",
    "sights", "video", "car_control",
}


def parse_jsonl(input_path: str) -> dict:
    """
    读取 jsonl 文件，按 intent 分组。
    返回：{intent: [ {from, query, intent, entity, is_car_control, m_intent}, ... ] }
    """
    grouped = defaultdict(list)
    bad_lines = 0

    with open(input_path, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad_lines += 1
                continue

            messages = obj.get("messages", [])
            user_msg, assistant_msg = None, None
            for m in messages:
                role = m.get("role")
                if role == "user":
                    user_msg = m.get("content", "")
                elif role == "assistant":
                    assistant_msg = m.get("content", "")

            if user_msg is None or assistant_msg is None:
                bad_lines += 1
                continue

            query = str(user_msg).strip()
            intent = str(assistant_msg).strip()

            if not query or not intent:
                bad_lines += 1
                continue

            row = {
                "from": "",
                "query": query,
                "intent": intent,
                "entity": "",
                "is_car_control": "",
                "m_intent": "",
            }
            grouped[intent].append(row)

    if bad_lines:
        print(f"⚠️  跳过 {bad_lines} 条无效/不完整行")

    return grouped


def write_xlsx(grouped: dict, output_path: str) -> None:
    """
    按 intent 分 Sheet 写入 xlsx；
    Sheet 顺序按样本量从多到少排列；Sheet 名形如 "meituan(4576)"。
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # 按样本量倒序
    ordered = sorted(grouped.items(), key=lambda x: -len(x[1]))

    total = 0
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for intent, rows in ordered:
            df = pd.DataFrame(rows, columns=COLUMNS)
            sheet_name = str(intent)
            # Excel sheet 名最长 31 字符
            if len(sheet_name) > 31:
                sheet_name = sheet_name[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            total += len(rows)
            print(f"  ✅ {sheet_name}: {len(rows)} 条")

    print("\n=== 转换完成 ===")
    print(f"📤 输出文件：{output_path}")
    print(f"📊 总样本数：{total}（共 {len(ordered)} 个 Sheet）")


def convert(input_jsonl: str, output_xlsx: str) -> None:
    if not os.path.exists(input_jsonl):
        raise FileNotFoundError(f"找不到输入文件：{input_jsonl}")

    print(f"📂 读取文件：{input_jsonl}")
    grouped = parse_jsonl(input_jsonl)

    # 给出未知标签提示（不阻断）
    unknown = [k for k in grouped.keys() if k not in VALID_LABELS]
    if unknown:
        print(f"⚠️  发现未知标签（仍会写入）：{unknown}")

    write_xlsx(grouped, output_xlsx)


def main():
    parser = argparse.ArgumentParser(description="将 jsonl 转换为按 intent 分 Sheet 的 xlsx")
    parser.add_argument(
        "--input", "-i",
        default="/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/openai_train_split_from_ma1_test.jsonl",
        help="输入的 jsonl 文件路径",
    )
    parser.add_argument(
        "--output", "-o",
        default="/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/MA_1.0_test.xlsx",
        help="输出的 xlsx 文件路径",
    )
    args = parser.parse_args()

    convert(args.input, args.output)


if __name__ == "__main__":
    main()
