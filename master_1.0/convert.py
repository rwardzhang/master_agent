# -*- coding: utf-8 -*-
"""
将 MA_1.0_train.xlsx 转换为 OpenAI 训练样本格式（jsonl）

源文件结构（新格式 MA_1.0_train）：
- 每个 Sheet 对应一个意图标签（如 meituan、chat、tc_travel 等）
- 第 0 行为表头：from | query | intent | entity | is_car_control | m_intent
- 从第 1 行开始为真实语料数据
- query 列内容形如：
    单轮：  "user:帮我下单送一杯山楂汁"
    多轮：  "user:使用美团\nassistant:...\nuser:中山路\nassistant:...\nuser:要第一个"
  其中 \n 为真实换行符，"assistant:..." 为历史助手回复占位
- intent 列即意图标签，与 sheet 名一致

目标格式：
- 每行一个 JSON 对象，包含 messages 字段
- messages 第 1 条为 system（统一意图分类系统提示词）
- 中间为 query 解析出的若干 user / assistant 多轮对话
- 最后一条为 assistant，内容为 intent 标签
"""

import json
import os
import re
import argparse
import pandas as pd


# 与 openai_train_split.jsonl 一致的 system prompt
SYSTEM_PROMPT = (
    "你是一个车载智能助手的意图分类系统。"
    "你的任务是根据用户的当前输入（以及可能的对话上下文），"
    "判断用户意图属于以下哪个分类标签，并仅输出标签名称。\n\n"
    "可选的分类标签：\n"
    "- food：餐厅/美食的搜索推荐与到店导航,不含具体下单动作。\n"
    "- puscene：到店用餐前的排队取号、订座、订包间预约\n"
    "- meituan：明确的自取/下单/想吃/购买/配送意图,且非星巴克、非瑞幸品牌，例如：外卖点餐、饮品下单、买药、超市购物等购买场景，支持一切可在美团小程序执行的操作\n"
    "- luckin：仅限瑞幸品牌的咖啡点单：商品选择、规格确认、下单自提\n"
    "- maoyan：明确的购买电影/演唱会/音乐会/话剧票务意图：电影/演唱会/音乐会/话剧搜索、影院/场馆选择、场次选择、选座、购票支付\n"
    "- tc_travel：明确的预订/购买意图：酒店预订、机票/火车票/景点门票购买等出行票务场景\n"
    "- music：音乐播放/搜索/问答/播控/伴奏\n"
    "- podcast：AI 播客生成/交互问答/实时播控/断点续播\n"
    "- news：早晚报/热点/分类/地区/关键词新闻的搜索、打开与播放\n"
    "- travel_plan：旅游规划/出游推荐/周边/沿途搜/ETA/AI向导/导航/常用POI管理/出行闲聊\n"
    "- chat：不属于以上分类标签的兜底场景，包含闲聊问答、天气查询、股票查询、百科问答等通用需求\n"
    "- starbucks：仅限星巴克品牌的咖啡点单：商品选择、规格确认、下单自提\n"
    "- sights：单个景区的搜索、推荐、信息问答，提供景区推荐服务\n"
    "- video：影视类视频搜索推荐、问答与播放控制\n"
    "- car_control：车辆硬件控制 + 车机APP开关 + 电话/蓝牙系统控制\n"
    "- miniprogram：支持在小程序中：查询航站楼|登机口|出发时间等信息、查询股票、小红书搜索、大众点评搜索、短剧、有声书、游戏、日程会议等各种内容\n\n"
    "- 仅输出一个标签名称（如 meituan / maoyan / starbucks），不要输出任何解释、推理过程或其他内容\n"
    "- 标签必须是上述列表中的一个，不能输出其他内容\n"
)

# 合法的意图标签集合，便于校验
VALID_LABELS = {
    "food", "puscene", "meituan", "luckin", "maoyan", "tc_travel",
    "music", "podcast", "news", "travel_plan", "chat", "starbucks",
    "sights", "video", "car_control","miniprogram"
}

# 用于切分多轮对话的正则：匹配行首 user: / assistant:
# 每段开头的 "user:" 或 "assistant:" 作为分隔标记
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

    返回：[{"role": "user"|"assistant", "content": "..."}]
    """
    if not query:
        return []

    # 找到所有 role 标记的位置
    matches = list(ROLE_PATTERN.finditer(query))
    if not matches:
        # 没找到任何标记，整段当成一句 user
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
      多条 user / assistant messages（不再整段塞进一条 user content）
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
        # 即至少 3 条；若 query 解析失败导致只有 system + label，则跳过
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
    parser = argparse.ArgumentParser(description="将 MA_1.0_train.xlsx 转换为 OpenAI 训练样本 jsonl 格式")
    parser.add_argument(
        "--input", "-i",
        default="/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/MA_1.0_train_1125.xlsx",
        help="输入的 xlsx 文件路径"
    )
    parser.add_argument(
        "--output", "-o",
        default="/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/zc_model_1.0_v40.jsonl",
        help="输出的 jsonl 文件路径"
    )
    args = parser.parse_args()

    convert(args.input, args.output)


if __name__ == "__main__":
    main()
