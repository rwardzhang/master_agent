# -*- coding: utf-8 -*-
"""
扩充 coffee.xlsx 中 meituan sheet 的语料，使三类标签数据更均衡。

策略：
- 现状：meituan(359) / luckin(952) / starbucks(1277)
- 目标：meituan 扩到 ~1000 条，与 luckin 量级接近
- 扩充原则：
  1) 严格保持"明确外送/外卖/配送意图"这一标签语义
  2) 只覆盖与现有训练语料同类的表达模式（不引入星巴克、瑞幸品牌歧义）
  3) 模板组合 + 去重；保留与原有数据一致的 "user:..." 前缀和 "\n" 多轮分隔风格
  4) 写回原 xlsx 的 meituan sheet，luckin / starbucks sheet 完全不动
"""

import os
import random
import pandas as pd
from openpyxl import load_workbook

INPUT_XLSX = "/Users/rwardzhang/PycharmProjects/master_agent_qc/coffee/coffee.xlsx"
TARGET_TOTAL = 1000  # 目标 meituan 样本数
SEED = 20260616

random.seed(SEED)


# =============== 词表 ===============

# 起手词（"我要 / 帮我 / 点 / 来 / 给我 / 麻烦 ..."）
LEAD_VERBS = [
    "点", "来", "我要", "帮我点", "帮我买", "帮我下单", "帮我叫",
    "给我", "给我点", "麻烦帮我点", "麻烦来", "搞", "搞杯", "弄", "弄杯",
    "整", "整一杯", "下单", "下个单", "买", "我想点", "我想喝", "我想来",
]

# 量词
QUANTIFIERS = ["一杯", "杯", "两杯", "三杯", "份", "一份", "个", "一个"]

# 商品（保持中性，不偏向某一品牌）
PRODUCTS = [
    "咖啡", "拿铁", "冰美式", "热美式", "美式", "热拿铁", "冰拿铁",
    "卡布奇诺", "摩卡", "燕麦拿铁", "澳白", "厚乳拿铁", "椰云拿铁",
    "生椰拿铁", "焦糖玛奇朵", "馥芮白",
]

# 品牌（基本覆盖训练集里所有出现过的品牌；不含瑞幸/星巴克避免歧义，
# 但保留少量"瑞幸/星巴克 + 外送词" 的组合，因为这本就是 meituan 类目核心 case）
BRANDS_NEUTRAL = [
    "库迪", "Manner", "Tims", "Tim Hortons", "幸运咖", "挪瓦咖啡", "NOWWA",
    "Costa", "皮爷咖啡", "Peet's", "Seesaw", "M Stand", "太平洋咖啡",
    "麦咖啡", "Grid Coffee", "代数学家咖啡", "鹰集咖啡", "%Arabica",
    "Lavazza", "连咖啡",
]
BRANDS_LUCKIN_STAR = ["瑞幸", "星巴克"]  # 与外送词结合时仍属 meituan

# 配送动词
DELIVERY_VERBS = [
    "外卖", "外送", "送到", "送", "配送到", "配送", "送过来", "送来",
    "快送到", "急送", "送到家", "送到公司",
]

# 配送地点
PLACES = [
    "家", "家里", "我家", "公司", "公司楼下", "公司前台", "公司门口",
    "办公室", "办公室前台", "办公楼前台", "工位", "会议室", "会议室门口",
    "楼下", "前台", "宿舍", "宿舍楼下", "学校门口", "教学楼", "图书馆",
    "酒店", "酒店大堂", "公寓", "公寓楼下", "小区门口", "小区", "院子里",
    "医院门口", "医院", "诊所", "客户那边", "客户公司", "甲方公司",
    "车站", "高铁站", "机场", "机场出发口", "地铁口", "地铁站",
    "商场门口", "商场", "餐厅", "工厂门口", "工地",
    "公园门口", "健身房", "书店", "咖啡馆门口", "影院门口",
    "现在的位置", "这个定位", "这个地址", "我的定位", "导航定位处",
    "幼儿园门口", "学校门口", "客户的会议室", "项目部",
]

# 助手占位
ASSIST = "assistant:..."


# =============== 单轮模板 ===============

def gen_singles(n):
    """生成 n 条独特的单轮 query（去重）"""
    out = set()

    # —— 模式 A：[起手] [量词] [商品] [配送词][地点]
    while len(out) < n // 2:
        v = random.choice(LEAD_VERBS)
        q = random.choice(QUANTIFIERS)
        p = random.choice(PRODUCTS)
        dv = random.choice(["送到", "配送到", "送", "送往", "送至"])
        place = random.choice(PLACES)
        text = f"user:{v}{q}{p}{dv}{place}"
        out.add(text)

    # —— 模式 B：[起手] [品牌] [配送词][地点]
    while len(out) < n * 3 // 4:
        v = random.choice(LEAD_VERBS)
        b = random.choice(BRANDS_NEUTRAL + BRANDS_LUCKIN_STAR)
        q = random.choice(["", "一杯", "杯", "两杯"])
        p = random.choice([""] + PRODUCTS)
        dv = random.choice(["外卖", "外送", "送到", "配送到", "送过来", "送", "送至"])
        place = random.choice([""] + PLACES)
        # 组合：品牌 + （量+商品）? + 配送 + 地点?
        if dv in ("外卖", "外送", "送过来"):
            text = f"user:{v}{q}{b}{p}{dv}".rstrip()
        else:
            place = random.choice(PLACES)
            text = f"user:{v}{q}{b}{p}{dv}{place}"
        # 简单整理：清理偶发的双量词
        out.add(text)

    # —— 模式 C：纯配送场景（不指定品牌）
    extras = [
        "user:点个咖啡外卖", "user:咖啡外卖来一份", "user:来份咖啡外卖",
        "user:整杯咖啡外送过来", "user:急送一杯咖啡到公司",
        "user:咖啡帮我送一下", "user:点杯咖啡赶紧送过来",
        "user:有没有咖啡能送到家的", "user:外卖一杯热美式",
        "user:外卖来杯冰美式", "user:点份咖啡外卖到家",
        "user:咖啡外卖现在能送吗", "user:来份咖啡配送",
        "user:来杯咖啡，外卖送", "user:帮我点份咖啡外卖到工位",
        "user:点一份咖啡套餐外送到公司", "user:点杯咖啡现送",
        "user:整杯咖啡送家", "user:配送一杯拿铁到楼下",
        "user:加急送一杯咖啡到办公室", "user:点份咖啡套餐外卖到家",
        "user:点份咖啡外卖到客户公司", "user:咖啡外卖送家门口",
        "user:咖啡帮我外送到家", "user:外卖买一杯咖啡到楼下",
    ]
    for e in extras:
        out.add(e)

    # —— 模式 D：含规格/数量的更口语化表达
    specs = ["少冰", "正常冰", "去冰", "热的", "冰的", "少糖", "不加糖", "正常糖",
             "大杯", "中杯", "加奶", "加双倍浓缩", "加燕麦奶"]
    while len(out) < n:
        v = random.choice(LEAD_VERBS)
        q = random.choice(["一杯", "两杯", "杯"])
        p = random.choice(PRODUCTS)
        s = random.choice(specs)
        place = random.choice(PLACES)
        dv = random.choice(["外卖送到", "外送到", "送到", "配送到"])
        text = f"user:{v}{q}{s}{p}{dv}{place}"
        out.add(text)

    out = list(out)
    random.shuffle(out)
    return out[:n]


# =============== 多轮模板 ===============

OPENERS = [
    "我想喝咖啡", "想喝咖啡", "来杯咖啡", "我要喝咖啡", "想点杯咖啡",
    "帮我点杯咖啡", "我要点咖啡", "帮我买杯咖啡", "想来杯咖啡",
    "我想喝点东西", "想喝点提神的", "好困啊想喝咖啡", "提提神",
    "口渴了来杯咖啡", "下午茶来杯咖啡", "想点杯下午茶",
    "我要下午茶", "想点点喝的", "需要一杯咖啡",
]

BRAND_PICK_LINES = [
    "选{b}", "点{b}", "{b}吧", "我要{b}", "来杯{b}", "用美团点{b}",
    "美团上点{b}", "找{b}", "帮我看下{b}", "美团点{b}",
    "不要瑞幸不要星巴克，{b}", "不是瑞幸，来杯{b}", "不要星巴克，点{b}",
]

PRODUCT_LINES = [
    "一杯{p}", "{p}", "来一杯{p}", "我要一杯{p}", "{p}，{s}",
    "一杯{p}，{s}", "两杯{p}", "{p}加{p2}",
]

SPEC_LINES = [
    "少冰", "正常冰", "去冰", "热的", "少糖", "不加糖", "正常糖",
    "大杯", "中杯", "加燕麦奶", "加双倍浓缩",
]

DELIVERY_LINES = [
    "送到家", "送到公司", "送到办公室", "送到工位", "送到会议室",
    "送到楼下", "送到公司楼下", "送到酒店", "送到酒店大堂",
    "送到学校门口", "送到地铁站", "送到机场", "送到高铁站",
    "送到客户那边", "送到这个地址", "送到当前定位", "外卖送过来",
    "外卖送到家", "外卖送到公司", "美团外卖送到家", "美团外卖送到办公室",
    "用美团下单送到家", "美团送到公司前台", "配送到家", "配送到办公室",
    "送到宿舍楼下", "送到医院门口", "送到小区门口", "送到项目部",
    "急送到公司", "尽快送到楼下",
]

CONFIRM_LINES = [
    "现在下单", "确认下单", "就这样下单", "麻烦快点", "尽快送到",
    "支付吧", "下单吧",
]


def make_multi_turn():
    """随机生成一条多轮 query（结尾必为配送/下单）"""
    n_turns = random.choice([2, 3, 3, 4, 4, 5])  # 多数 3~4 轮

    user_turns = []
    user_turns.append(random.choice(OPENERS))

    # 中间轮：可选 "选品牌"、"选商品"、"指定规格"
    if n_turns >= 3:
        b = random.choice(BRANDS_NEUTRAL)
        user_turns.append(random.choice(BRAND_PICK_LINES).format(b=b))

    if n_turns >= 4:
        p = random.choice(PRODUCTS)
        p2 = random.choice(PRODUCTS)
        s = random.choice(SPEC_LINES)
        line = random.choice(PRODUCT_LINES).format(p=p, p2=p2, s=s)
        user_turns.append(line)

    if n_turns >= 5:
        user_turns.append(random.choice(SPEC_LINES))

    # 最后一轮固定为配送指令（少数情况是"现在下单"，但前一轮一定是配送）
    if random.random() < 0.15 and len(user_turns) >= 2:
        # 倒数第二轮配送，最后一轮确认
        user_turns.append(random.choice(DELIVERY_LINES))
        user_turns.append(random.choice(CONFIRM_LINES))
    else:
        user_turns.append(random.choice(DELIVERY_LINES))

    # 拼接成 "user:.. \n assistant:... \n user:.. ..." 的格式
    parts = []
    for i, u in enumerate(user_turns):
        parts.append(f"user:{u}")
        if i < len(user_turns) - 1:
            parts.append(ASSIST)
    return "\n".join(parts)


def gen_multi(n):
    out = set()
    tries = 0
    while len(out) < n and tries < n * 50:
        out.add(make_multi_turn())
        tries += 1
    out = list(out)
    random.shuffle(out)
    return out[:n]


# =============== 主流程 ===============

def main():
    # 1. 读取现有 meituan
    df = pd.read_excel(INPUT_XLSX, sheet_name="meituan", header=0)
    df.columns = [str(c).strip() for c in df.columns]
    existing = set(df["query"].dropna().astype(str).tolist())
    print(f"📥 现有 meituan 语料：{len(existing)} 条")

    need = TARGET_TOTAL - len(existing)
    if need <= 0:
        print(f"✅ 已达目标 {TARGET_TOTAL}，无需扩充")
        return

    # 2. 生成新语料：单轮 / 多轮 ≈ 2:1（与原始比例 231:128 接近）
    n_single = int(need * 0.62)
    n_multi  = need - n_single

    candidate_singles = gen_singles(n_single * 2)   # 多生成一些以便去重
    candidate_multi   = gen_multi(n_multi * 2)

    # 3. 去重：与原 query 列做去重
    new_singles = [q for q in candidate_singles if q not in existing][:n_single]
    seen = set(new_singles) | existing
    new_multi = [q for q in candidate_multi if q not in seen][:n_multi]

    new_rows = new_singles + new_multi
    print(f"🆕 新生成单轮 {len(new_singles)} 条，多轮 {len(new_multi)} 条，合计 {len(new_rows)} 条")

    # 4. 构造新 DataFrame（沿用原表头：from / query / intent / entity / is_car_control / m_intent）
    cols = list(df.columns)
    new_df = pd.DataFrame(
        [{c: "" for c in cols} for _ in new_rows]
    )
    new_df["query"] = new_rows
    new_df["intent"] = "meituan"

    # 与原数据合并
    merged = pd.concat([df, new_df], ignore_index=True)
    # 再做一次全局去重（query 列）
    before = len(merged)
    merged = merged.drop_duplicates(subset=["query"]).reset_index(drop=True)
    print(f"🧹 去重后 meituan 总数：{len(merged)}（去重前 {before}）")

    # 5. 写回 xlsx：保留 luckin / starbucks sheet 不变，仅替换 meituan sheet
    #    使用 openpyxl 直接覆盖 meituan sheet 内容
    wb = load_workbook(INPUT_XLSX)
    if "meituan" in wb.sheetnames:
        del wb["meituan"]
    # 把 meituan 放到首位（与原顺序一致）
    ws = wb.create_sheet("meituan", index=0)

    # 写表头
    for c_idx, col in enumerate(cols, start=1):
        ws.cell(row=1, column=c_idx, value=col)
    # 写数据
    for r_idx, row in enumerate(merged.itertuples(index=False), start=2):
        for c_idx, val in enumerate(row, start=1):
            if pd.isna(val):
                val = None
            ws.cell(row=r_idx, column=c_idx, value=val)

    wb.save(INPUT_XLSX)
    print(f"💾 已写回：{INPUT_XLSX}（meituan sheet 共 {len(merged)} 条）")


if __name__ == "__main__":
    main()
