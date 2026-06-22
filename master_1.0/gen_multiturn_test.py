# -*- coding: utf-8 -*-
"""
基于训练集生成多轮意图分类测试语料（**同域真实模板替换法**）

核心思路（V2，对齐训练集风格）：
1. 训练集中的多轮样本结构都是：整段对话围绕同一个意图领域展开，
   末尾标签 = 整段主线意图，中间 assistant 全部用 "..." 占位。
2. 因此本脚本不再做跨域拼接，而是直接以训练集多轮样本为「模板」：
   - 同标签下随机抽一条训练集多轮样本作为模板
   - 把模板的"末轮 user query"替换成测试集中的同标签单轮 query
   - system 与 中间 assistant 占位 完全保留训练集原样
3. 这样产出的样本：
   - 结构 / 长度分布 / 上下文风格 完全对齐训练集
   - 末轮 query 来自测试集，未在训练集出现过，评测意义保留
   - 标签语义自洽（前缀和末轮都是同一意图领域）

输出：
- openai_test_multiturn.jsonl
- MA_1.0_test_multiturn.xlsx

可重复性：固定随机种子。

用法：
    python3 gen_multiturn_test.py
    python3 gen_multiturn_test.py --per-label 100 --seed 42
"""

import os
import json
import random
import argparse
from collections import defaultdict, Counter

import pandas as pd


# ============== 默认路径与配置 ==============
DEFAULT_TRAIN_JSONL = "/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/openai_train_split_from_ma1_train.jsonl"
DEFAULT_TEST_JSONL  = "/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/openai_train_split_from_ma1_test.jsonl"
DEFAULT_OUT_JSONL   = "/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/openai_test_multiturn.jsonl"
DEFAULT_OUT_XLSX    = "/Users/rwardzhang/PycharmProjects/master_agent_qc/master_1.0/MA_1.0_test_multiturn.xlsx"

VALID_LABELS = [
    "food", "puscene", "meituan", "luckin", "maoyan", "tc_travel",
    "music", "podcast", "news", "travel_plan", "chat", "starbucks",
    "sights", "video", "car_control",
]

# xlsx 输出表头（与 MA_1.0_train.xlsx 一致）
XLSX_COLUMNS = ["from", "query", "intent", "entity", "is_car_control", "m_intent"]


# ============== 数据加载 ==============
def load_jsonl(path: str) -> list:
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def split_messages(messages: list):
    """
    把 jsonl 样本的 messages 拆成: system_msg / convo / label
    convo 即中间的 user/assistant 对，末尾 label = 最后一条 assistant 内容
    """
    system_msg = messages[0]
    label = messages[-1]["content"]
    convo = messages[1:-1]
    return system_msg, convo, label


# ============== 训练集多轮模板抽取（同域） ==============
def extract_multiturn_templates(train_items: list):
    """
    从训练集中抽取所有多轮样本作为模板。
    模板形如：
        {
            "system": <system message>,
            "convo":  [user1, assistant1, ..., user_{N-1}, assistant_{N-1}, userN],
            "label":  <意图>,
            "n_user": N,
        }
    返回:
        templates_by_label: {label: [template, ...]}
        n_user_dist:       Counter，user 轮数分布（含末轮）
    """
    templates_by_label = defaultdict(list)
    n_user_dist = Counter()

    for item in train_items:
        sys_msg, convo, label = split_messages(item["messages"])
        n_user = sum(1 for m in convo if m["role"] == "user")
        if n_user < 2:
            continue
        # 校验末尾必须是 user（训练集多轮的末轮一定是 user）
        if not convo or convo[-1]["role"] != "user":
            continue
        templates_by_label[label].append({
            "system": sys_msg,
            "convo": convo,
            "label": label,
            "n_user": n_user,
        })
        n_user_dist[n_user] += 1

    return templates_by_label, n_user_dist


# ============== 测试集 query 抽取（同域） ==============
def extract_test_queries(test_items: list):
    """
    从单轮测试集抽取每个标签的 query 列表
    返回: {label: [query_str, ...]}
    """
    queries_by_label = defaultdict(list)
    for item in test_items:
        _, convo, label = split_messages(item["messages"])
        # 仅取单轮
        users = [m["content"] for m in convo if m["role"] == "user"]
        n_user = len(users)
        if n_user != 1:
            continue
        queries_by_label[label].append(users[0])
    return queries_by_label


# ============== 拼接生成 ==============
def build_sample_from_template(template: dict, new_last_query: str) -> dict:
    """
    用 new_last_query 替换 template 末轮 user，构造完整样本。
    历史 assistant 占位保持原样（训练集统一为 "..."）。
    """
    sys_msg = template["system"]
    label = template["label"]
    convo = list(template["convo"])  # 浅拷贝
    # 替换最后一条（必为 user）的内容
    convo[-1] = {"role": "user", "content": new_last_query}

    messages = [sys_msg] + convo + [{"role": "assistant", "content": label}]
    return {"messages": messages}


def messages_to_query_str(convo: list) -> str:
    """
    把 convo（含末轮 user）还原为 xlsx query 列字符串：
        user:xxx\\nassistant:...\\nuser:yyy
    """
    return "\n".join(f"{m['role']}:{m['content']}" for m in convo)


# ============== 主流程 ==============
def generate(args):
    rng = random.Random(args.seed)

    print(f"📂 加载训练集: {args.train}")
    train_items = load_jsonl(args.train)
    print(f"   {len(train_items)} 条")

    print(f"📂 加载单轮测试集: {args.test}")
    test_items = load_jsonl(args.test)
    print(f"   {len(test_items)} 条")

    print("\n🔍 抽取训练集多轮模板（同域）...")
    templates_by_label, n_user_dist = extract_multiturn_templates(train_items)
    total_tpl = sum(len(v) for v in templates_by_label.values())
    print(f"   共 {total_tpl} 条多轮模板，user 轮数分布: {dict(sorted(n_user_dist.items()))}")
    for lb in VALID_LABELS:
        print(f"     {lb:12s}: {len(templates_by_label.get(lb, []))} 条模板")

    print("\n🔍 抽取单轮测试集 query...")
    queries_by_label = extract_test_queries(test_items)
    for lb in VALID_LABELS:
        print(f"     {lb:12s}: {len(queries_by_label.get(lb, []))} 条 query")

    # ============ 拼接 ============
    print(f"\n🛠  开始生成：每标签 {args.per_label} 条（同域真实模板替换法）\n")
    out_samples = []
    out_meta = []

    for label in VALID_LABELS:
        tpl_pool = templates_by_label.get(label, [])
        q_pool = queries_by_label.get(label, [])
        if not tpl_pool:
            print(f"  ⚠️  {label}: 训练集无多轮模板，跳过")
            continue
        if not q_pool:
            print(f"  ⚠️  {label}: 测试集无候选 query，跳过")
            continue

        n_need = args.per_label

        # 末轮 query 采样：足量则不放回，不足则放回
        if len(q_pool) >= n_need:
            picked_queries = rng.sample(q_pool, n_need)
        else:
            picked_queries = [rng.choice(q_pool) for _ in range(n_need)]

        # 模板采样：每条 query 配一个模板（放回采样，因为模板池小于 query 数也允许复用）
        picked_templates = [rng.choice(tpl_pool) for _ in range(n_need)]

        for tpl, q in zip(picked_templates, picked_queries):
            sample = build_sample_from_template(tpl, q)
            out_samples.append(sample)
            convo = sample["messages"][1:-1]
            out_meta.append({
                "query": messages_to_query_str(convo),
                "intent": label,
                "n_user_turns": tpl["n_user"],
            })

        print(f"  ✅ {label:12s}: {n_need} 条")

    # 打乱顺序，避免按标签聚集
    combined = list(zip(out_samples, out_meta))
    rng.shuffle(combined)
    out_samples, out_meta = zip(*combined)
    out_samples, out_meta = list(out_samples), list(out_meta)

    # ============ 写 jsonl ============
    os.makedirs(os.path.dirname(args.out_jsonl) or ".", exist_ok=True)
    with open(args.out_jsonl, "w", encoding="utf-8") as f:
        for s in out_samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"\n📤 已写出 jsonl: {args.out_jsonl}  ({len(out_samples)} 条)")

    # ============ 写 xlsx（按 intent 分 Sheet） ============
    grouped = defaultdict(list)
    for meta in out_meta:
        grouped[meta["intent"]].append({
            "from": "",
            "query": meta["query"],
            "intent": meta["intent"],
            "entity": "",
            "is_car_control": "",
            "m_intent": f"multi_turn|user_turns={meta['n_user_turns']}",
        })

    os.makedirs(os.path.dirname(args.out_xlsx) or ".", exist_ok=True)
    ordered = sorted(grouped.items(), key=lambda x: -len(x[1]))
    with pd.ExcelWriter(args.out_xlsx, engine="openpyxl") as writer:
        for intent, rows in ordered:
            df = pd.DataFrame(rows, columns=XLSX_COLUMNS)
            sheet_name = str(intent)[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    print(f"📤 已写出 xlsx : {args.out_xlsx}  ({sum(len(v) for v in grouped.values())} 条，{len(grouped)} 个 Sheet)")

    # ============ 统计 ============
    print("\n=== 生成统计 ===")
    print(f"总样本数: {len(out_samples)}")
    turn_dist = Counter(m["n_user_turns"] for m in out_meta)
    print(f"user 轮数分布: {dict(sorted(turn_dist.items()))}")


def main():
    parser = argparse.ArgumentParser(description="生成多轮意图分类测试语料（同域真实模板替换法）")
    parser.add_argument("--train", default=DEFAULT_TRAIN_JSONL, help="训练集 jsonl 路径")
    parser.add_argument("--test", default=DEFAULT_TEST_JSONL, help="单轮测试集 jsonl 路径")
    parser.add_argument("--out-jsonl", default=DEFAULT_OUT_JSONL, help="输出 jsonl 路径")
    parser.add_argument("--out-xlsx", default=DEFAULT_OUT_XLSX, help="输出 xlsx 路径")
    parser.add_argument("--per-label", type=int, default=100, help="每个标签生成的样本数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    generate(args)


if __name__ == "__main__":
    main()
