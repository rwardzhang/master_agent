# -*- coding: utf-8 -*-
"""
将 coffee.xlsx 转换为 OpenAI 训练样本格式（jsonl）

源文件结构（coffee.xlsx）：
- 共 3 个 Sheet，分别对应一个意图标签：meituan / luckin / starbucks
- 第 0 行为表头：from | query | intent | entity | is_car_control | m_intent
- 从第 1 行开始为真实语料数据
- query 列内容形如：
    单轮：  "user:点个咖啡外卖"
    多轮：  "user:我想点杯咖啡\nassistant:...\nuser:我要瑞幸"
  其中 \n 为真实换行符，"assistant:..." 为历史助手回复占位
- intent 列即意图标签，与 sheet 名一致

目标格式（保持与原训练格式一致）：
- 每行一个 JSON 对象，包含 messages 字段
- messages 第 1 条为 system（咖啡场景三分类系统提示词）
- 中间为 query 解析出的若干 user / assistant 多轮对话
- 最后一条为 assistant，内容为 intent 标签
"""

import json
import os
import argparse
import pandas as pd


# 咖啡场景七分类（meituan / luckin / starbucks / clarify / whatever / terminate / other）专用 system prompt
SYSTEM_PROMPT = (
    "你是点单品类下的品牌与服务平台意图分类助手。请结合用户输入和最近上下文，"
    "判断用户当前关于点咖啡诉求的核心意图，并从下列结果中选择一个最匹配结果：\n\n"
    "分类定义：\n"
    "    luckin：用户明确说使用瑞幸小程序，或者没有明确说使用哪种小程序但要买瑞幸独有商品；"
    "瑞幸小程序只支持到店自取，如果表达要外卖、外送、配送或送到某地，不能输出 luckin。"
    "瑞幸独有品名关键字包括：生椰、橙C、苹果C、柚C、小黄油、厚乳、陨石。\n"
    "    starbucks：用户明确说使用星巴克小程序，或者没有明确说使用哪种小程序但要买星巴克独有商品；"
    "星巴克小程序只支持到店自取，如果表达要外卖、外送、配送或送到某地，不能输出 starbucks。"
    "星巴克独有品名关键字包括：星冰、星冰乐、焦糖玛奇朵、馥芮白、冰震浓缩。\n"
    "    meituan：用户意图包含外卖、外送、配送、送到某地等需要配送的服务意图，表示使用美团小程序；"
    "如果用户明确说了咖啡品牌，但该品牌不是瑞幸或星巴克，也输出 meituan。\n"
    "    clarify：用户的点咖啡诉求可以在瑞幸和星巴克完成，且用户没有表达品牌、小程序或平台偏好，"
    "需要继续询问使用星巴克还是瑞幸。\n"
    "    whatever：用户明确表达\"都可以、随便、听你的、你决定、无所谓\"等无偏好含义。\n"
    "    terminate：用户明确表达不想点了、取消点单、算了等停止点单含义，且没有其他需要继续处理的核心意图。\n"
    "    other：不属于上述场景，或者当前核心意图不是点咖啡。\n\n"
)

# 合法的意图标签集合（咖啡场景 7 类）
VALID_LABELS = {"meituan", "luckin", "starbucks", "clarify", "whatever", "terminate", "other"}


def build_sample(query: str, label: str) -> dict:
    """
    构造单条 OpenAI 训练样本：
        [
            {"role": "system",    "content": SYSTEM_PROMPT},
            {"role": "user",     "content": <query 原文，保留 user:/assistant: 及 \n>},
            {"role": "assistant","content": <label>}
        ]

    注意：不再将多轮对话拆分成多条 message，整段 query 作为一条 user 的 content。
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
        {"role": "assistant", "content": label},
    ]
    return {"messages": messages}


def parse_sheet(xls: pd.ExcelFile, sheet_name: str) -> tuple:
    """
    解析单个 Sheet：
    - 第 0 行为表头（from / query / intent / entity / is_car_control / m_intent）
    - 从第 1 行开始为数据
    - 取 query 列与 intent 列

    返回 (samples, skipped)
    """
    df = pd.read_excel(xls, sheet_name=sheet_name, header=0)

    # 兼容大小写 / 去除空白
    df.columns = [str(c).strip() for c in df.columns]

    if "query" not in df.columns or "intent" not in df.columns:
        print(f"  ⚠️  Sheet [{sheet_name}] 缺少 query 或 intent 列（实际列：{list(df.columns)}），已跳过")
        return [], 0

    samples = []
    skipped = 0
    for _, row in df.iterrows():
        query = row["query"]
        label = row["intent"]

        # 过滤空行 / NaN
        if pd.isna(query) or pd.isna(label):
            skipped += 1
            continue

        query = str(query).strip()
        label = str(label).strip()

        if not query or not label:
            skipped += 1
            continue

        # 校验标签合法性
        if label not in VALID_LABELS:
            print(f"  ⚠️  Sheet [{sheet_name}] 出现未知标签：{label}，已跳过")
            skipped += 1
            continue

        sample = build_sample(query, label)
        samples.append(sample)

    return samples, skipped


def convert(input_xlsx: str, output_jsonl: str) -> None:
    if not os.path.exists(input_xlsx):
        raise FileNotFoundError(f"找不到输入文件：{input_xlsx}")

    xls = pd.ExcelFile(input_xlsx)
    print(f"📂 读取文件：{input_xlsx}")
    print(f"📑 共 {len(xls.sheet_names)} 个 Sheet：{xls.sheet_names}\n")

    total = 0
    label_counter = {}
    multi_turn_counter = 0

    os.makedirs(os.path.dirname(output_jsonl) or ".", exist_ok=True)

    with open(output_jsonl, "w", encoding="utf-8") as fout:
        for sheet_name in xls.sheet_names:
            samples, skipped = parse_sheet(xls, sheet_name)
            for s in samples:
                fout.write(json.dumps(s, ensure_ascii=False) + "\n")
                lbl = s["messages"][-1]["content"]
                label_counter[lbl] = label_counter.get(lbl, 0) + 1
                # query 中出现 "assistant:" 即视为多轮
                user_content = s["messages"][1]["content"]
                if "assistant:" in user_content or "assistant：" in user_content:
                    multi_turn_counter += 1
            total += len(samples)
            print(f"  ✅ {sheet_name}: 写入 {len(samples)} 条，跳过 {skipped} 条")

    print("\n=== 转换完成 ===")
    print(f"📤 输出文件：{output_jsonl}")
    print(f"📊 总样本数：{total}")
    print(f"🔁 其中多轮样本数：{multi_turn_counter}")
    print("\n各标签样本数：")
    for lbl, cnt in sorted(label_counter.items(), key=lambda x: -x[1]):
        print(f"  {lbl}: {cnt}")


def main():
    parser = argparse.ArgumentParser(description="将 coffee.xlsx 转换为 OpenAI 训练样本 jsonl 格式（meituan / luckin / starbucks / clarify / whatever / terminate / other 七分类）")
    parser.add_argument(
        "--input", "-i",
        default="/Users/rwardzhang/PycharmProjects/master_agent_qc/coffee/coffee.xlsx",
        help="输入的 xlsx 文件路径"
    )
    parser.add_argument(
        "--output", "-o",
        default="/Users/rwardzhang/PycharmProjects/master_agent_qc/coffee/coffee_train.jsonl",
        help="输出的 jsonl 文件路径"
    )
    args = parser.parse_args()

    convert(args.input, args.output)


if __name__ == "__main__":
    main()
