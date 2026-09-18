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
import re
import argparse
import pandas as pd


# 咖啡场景七分类（meituan / luckin / starbucks / clarify / whatever / terminate / other）专用 system prompt
SYSTEM_PROMPT = """你是「点单与订单查询」场景的意图分类器。你的任务是根据用户的当前输入（以及可能的对话上下文），判断用户当前的核心意图，输出唯一一个标签。

【可服务范围】
每个服务域后的括号内为该域可落地的品牌/平台，点单与查订单同样适用：
    - 咖啡（瑞幸、星巴克）：咖啡、奶咖、饮品。
        · 瑞幸独有商品：生椰、橙C、苹果C、柚C、小黄油、厚乳、陨石。
        · 星巴克独有商品：星冰、星冰乐、焦糖玛奇朵、馥芮白、冰震浓缩。
    - 外卖配送（美团）：点外卖、外送、配送、送到某地、以及奶茶、茶饮、果茶等
    - 出行（同程）：火车票、高铁、机票、酒店、汽车票、旅游出行。
    - 娱乐票务（猫眼）：电影票、演出票、演唱会、话剧、音乐剧。
    - 排队（美味不用等）：餐厅排队、取号、等位、排号。

【标签含义】
    precise：能唯一确定一个品牌/平台。
    clarify：诉求落在可服务范围内，但定位不到唯一品牌/平台，需要追问。
    whatever：明确表达无偏好（都行、随便、听你的、你定、无所谓）。
    terminate：明确表达终止当前事项（不弄了、取消、算了不用了），且没有其它待办诉求。
    other：当前核心意图在可服务范围之外。

【判定步骤】（自上而下，命中即停）
    1. 当前句表达的是服务范围之外的功能诉求（如放音乐、导航、问天气、闲聊）→ other；即使上文在点单，只要当前句已转向范围外诉求，也按此判断。
    2. 当前句明确表示终止且没有其它诉求 → terminate；若在终止的同时又提出范围内的新诉求，则忽略终止、按新诉求继续判断。
    3. 当前句明确表达无偏好 → whatever（这类回应通常出现在系统已追问品牌/平台之后）。
    4. 能唯一锁定一个品牌/平台 → precise，满足任一即可：
        · 直接说出品牌/平台名；
        · 命中某品牌独有商品（需整句读音对应地完整命中，仅个别字相同或口味相近不算命中）；
        · 诉求落在仅含唯一品牌/平台的服务域（外卖配送 / 出行 / 娱乐票务 / 排队）。
    5. 落在可服务范围内但锁不到唯一品牌/平台 → clarify：
        · 咖啡仅说“咖啡 / 拿铁 / 美式 / 咖啡订单”等通用词、未指明瑞幸或星巴克（点单或查订单都一样）；
        · 通用动作词跨域，如“买票”可能是出行或娱乐票务，未指定平台的“查订单”可能是任一域。

【补充规则】
    - 当前这句话优先于上下文；仅当当前句缺少关键线索时，才用上下文补全。
    - 语音转写可能有同音/近音错别字，整句读音明显指向某品牌、平台或服务词时，按正确含义理解。
【输出要求】
    仅输出 precise、clarify、whatever、terminate、other 其中之一，不带任何解释、标点或换行。"""

# 合法的意图标签集合（咖啡场景 7 类）
VALID_LABELS = {"precise","clarify", "whatever", "terminate", "other"}

# 用于切分多轮对话的正则：匹配行首 user: / assistant:
ROLE_PATTERN = re.compile(r"(?:^|\n)(user|assistant)\s*[:：]\s*", re.IGNORECASE)

# 用于检查 query 是否以 user: / assistant: 开头（允许前置空白）
ROLE_PREFIX_PATTERN = re.compile(r"^\s*(user|assistant)\s*[:：]", re.IGNORECASE)


def ensure_user_prefix(query: str) -> tuple:
    """确保 query 带有 role 前缀。

    规则：
    - 若 query 已经以 "user:" / "assistant:" 开头（中英文冒号均可），原样返回
    - 否则在最前面补一个 "user:" 前缀

    返回 (new_query, fixed)，fixed 为 True 表示进行了补全
    """
    if not query:
        return query, False
    if ROLE_PREFIX_PATTERN.match(query):
        return query, False
    return "user:" + query, True


def parse_query_to_turns(query: str) -> list:
    """
    将 query 字段解析为多轮对话 messages（不含 system / 末尾 label）

    规则：
    - 以 "user:" / "assistant:" 作为 role 分隔标记
    - 每段 role 对应的内容作为该消息的 content
    - 保留 "assistant:..." 这种历史助手回复占位（content 为 "..."）
    """
    if not query:
        return []

    matches = list(ROLE_PATTERN.finditer(query))
    if not matches:
        return [{"role": "user", "content": query.strip()}]

    turns = []
    for i, m in enumerate(matches):
        role = m.group(1).lower()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(query)
        content = query[start:end].strip()
        if not content:
            continue
        turns.append({"role": role, "content": content})

    return turns


def build_sample(query: str, label: str) -> tuple:
    """构造单条 OpenAI 训练样本（多轮 messages 格式）

    样本结构：
        [
          {"role": "system",    "content": SYSTEM_PROMPT},
          {"role": "user",      "content": "..."},
          {"role": "assistant", "content": "..."},   # 历史助手回复占位（如 "..."）
          {"role": "user",      "content": "..."},
          ...
          {"role": "assistant", "content": label},   # 末尾 assistant 输出意图标签
        ]

    说明：
    - query 中 "user:xxx\\nassistant:...\\nuser:yyy" 这样的多轮上下文会被拆分为
      多条 user / assistant messages
    - 写入 jsonl 前会检查 query 是否带有 user:/assistant: 前缀，没有则自动补 user:
    - 末尾固定追加一条 {"role": "assistant", "content": label}

    返回 (sample, fixed)，fixed=True 表示本条进行了 user: 前缀补全。
    """
    content = query.strip()
    content, fixed = ensure_user_prefix(content)

    turns = parse_query_to_turns(content)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(turns)
    messages.append({"role": "assistant", "content": label})

    return {"messages": messages}, fixed


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
    fixed_prefix_count = 0  # 统计 jsonl 写入时被补 'user:' 前缀的条数
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

        # 生成训练样本；在 build_sample 内部会检查并补上 'user:' 前缀
        sample, fixed = build_sample(query, label)
        if fixed:
            fixed_prefix_count += 1

        # 校验：messages 至少包含 system + 1 条 user + 末尾 assistant label
        if len(sample["messages"]) < 3:
            skipped += 1
            continue

        samples.append(sample)

    if fixed_prefix_count > 0:
        print(f"  🛠️  Sheet [{sheet_name}] 写入 jsonl 时为 {fixed_prefix_count} 条 query 补上了 'user:' 前缀")

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
                # 中间消息（去掉首条 system 与末尾 assistant 标签）大于 1 条则为多轮
                if len(s["messages"]) - 2 > 1:
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
        default="/Users/rwardzhang/PycharmProjects/master_agent_qc/coffee/coffee_order_0728.xlsx",
        help="输入的 xlsx 文件路径"
    )
    parser.add_argument(
        "--output", "-o",
        default="/Users/rwardzhang/PycharmProjects/master_agent_qc/coffee/coffee_order_0728.jsonl",
        help="输出的 jsonl 文件路径"
    )
    args = parser.parse_args()

    convert(args.input, args.output)


if __name__ == "__main__":
    main()
