# -*- coding: utf-8 -*-
"""
扩展 coffee.xlsx 训练集：从 3 类（meituan/luckin/starbucks）扩展到 7 类
新增标签：clarify / whatever / terminate / other

执行步骤：
  1. 读取现有 coffee.xlsx 中的 meituan / luckin / starbucks
  2. 将 luckin 中"末轮为随便/都可以等"的 86 条多轮样本迁移到新 whatever sheet
  3. 生成 clarify / whatever / terminate / other 四类的训练语料
  4. 整体写回 coffee.xlsx（7 个 sheet）
"""

import os
import random
import re

import pandas as pd

random.seed(42)

INPUT_XLSX = "/Users/rwardzhang/PycharmProjects/master_agent_qc/coffee/coffee.xlsx"
OUTPUT_XLSX = "/Users/rwardzhang/PycharmProjects/master_agent_qc/coffee/coffee.xlsx"

COLS = ["from", "query", "intent", "entity", "is_car_control", "m_intent"]

# 用于识别 luckin sheet 中"末轮为随便/都可以"的多轮样本
WHATEVER_KEYWORDS = [
    "随便", "都行", "都可以", "无所谓", "你看着办", "看你推荐", "随意",
    "任意", "whatever", "你决定", "听你的", "看你的", "都成", "都中",
    "都一样", "都好", "你来定", "你来选", "都喜欢", "都爱", "都不挑",
    "没意见", "没要求", "什么都行", "哪个都行", "哪个都可以", "你帮我选",
    "你帮我决定", "你说了算", "都没问题", "都ok", "都OK", "都Ok",
]
WHATEVER_RE = re.compile("|".join(map(re.escape, WHATEVER_KEYWORDS)))


def is_last_turn_whatever(query: str) -> bool:
    """判断多轮 query 的最后一条 user 消息是否为"随便/都可以"等模糊表态"""
    q = (query or "").strip()
    if "assistant:" not in q.lower():
        return False
    last_line = q.split("\n")[-1].strip()
    # 必须以 user: 开头
    if not last_line.lower().startswith("user:"):
        return False
    return bool(WHATEVER_RE.search(last_line))


def make_row(query: str, intent: str) -> dict:
    return {
        "from": "synthetic",
        "query": query,
        "intent": intent,
        "entity": "",
        "is_car_control": "",
        "m_intent": "",
    }


# ============================================================================
# 1. clarify 语料：用户想喝咖啡但没说品牌、没说配送、瑞幸/星巴克都能满足
# ============================================================================

# 单轮 clarify：表达想点咖啡，但没指定品牌/特有商品/配送
CLARIFY_SINGLE_TURN = [
    # 直接表达想喝咖啡
    "我想喝咖啡", "想喝杯咖啡", "来杯咖啡", "点杯咖啡", "我要喝咖啡", "给我来杯咖啡",
    "帮我点杯咖啡", "买杯咖啡", "我要点咖啡", "想点咖啡", "整杯咖啡", "搞杯咖啡",
    "弄杯咖啡", "来点咖啡", "我想点杯咖啡", "帮我买杯咖啡", "买点咖啡", "想要点咖啡",
    "我想买咖啡", "需要一杯咖啡", "来一杯咖啡", "给我整一杯咖啡", "我要一杯咖啡",
    "想来杯咖啡", "我得喝杯咖啡", "我要一杯咖啡谢谢", "想喝咖啡了", "我饿了想喝咖啡",
    "想点杯咖啡喝", "想买杯咖啡喝喝", "下午想喝咖啡", "上午想点杯咖啡",
    "晚上想点杯咖啡", "早上想喝杯咖啡", "我想喝点咖啡", "整一杯咖啡吧",
    # 想点 / 想喝某个通用品类（不具品牌）
    "我想点杯拿铁", "来杯拿铁", "点杯拿铁", "我要杯拿铁", "买杯拿铁", "整杯拿铁",
    "想喝拿铁", "想要杯拿铁", "我要拿铁", "帮我点杯拿铁", "需要一杯拿铁",
    "来杯美式", "我要杯美式", "想喝美式", "点杯美式", "买杯美式", "我要美式",
    "帮我点杯美式", "整杯美式", "需要一杯美式", "想点美式", "来一杯美式",
    "想要杯美式", "买一杯美式", "整一杯美式",
    "来杯卡布奇诺", "想喝卡布奇诺", "点杯卡布奇诺", "我要卡布奇诺", "整杯卡布奇诺",
    "来杯摩卡", "想喝摩卡", "点杯摩卡", "整杯摩卡", "买杯摩卡", "我要摩卡",
    "来杯澳白", "我要澳白", "点杯澳白", "想喝澳白",
    "想喝杯热咖啡", "来杯热咖啡", "想喝杯冰咖啡", "来杯冰咖啡", "我要杯冰咖啡",
    "想喝冰美式", "来杯冰美式", "我要冰美式", "点杯冰美式", "整杯冰美式",
    "想喝冰拿铁", "来杯冰拿铁", "我要冰拿铁", "点杯冰拿铁", "整杯冰拿铁",
    # 想提神 / 没精神 / 困
    "我有点困想喝咖啡", "想提神来杯咖啡", "犯困了点杯咖啡", "好困来杯咖啡",
    "犯困了想喝咖啡", "提个神点杯咖啡", "想提个神来杯咖啡",
    "好累想喝咖啡", "累了想喝杯咖啡", "我要提神咖啡", "来杯提神的咖啡",
    "想喝点提神的", "想点杯提神的咖啡",
    # 自取相关（未说品牌）
    "点杯咖啡自取", "我要点杯咖啡自取", "帮我点杯咖啡到店自取", "来杯咖啡到店取",
    "点一杯咖啡到店自提", "我去取咖啡帮我点一杯", "点杯咖啡我自己去取",
    "点杯拿铁自取", "点杯美式自取", "拿铁自取一杯", "美式自取一杯",
    "我去店里取，点杯咖啡", "帮我点杯咖啡我去拿",
    # 在附近点
    "附近点杯咖啡", "在附近点杯咖啡", "附近来杯咖啡", "附近买杯咖啡",
    "附近点一杯拿铁", "附近点杯美式", "附近找家咖啡店点一杯",
    "找个近的咖啡店点一杯", "点杯附近的咖啡", "就近点杯咖啡",
    # 模糊一点
    "想喝点饮料咖啡那种", "想喝点咖啡因", "需要咖啡因", "来点咖啡因",
    "想喝点带咖啡因的", "我要喝点带咖啡的", "整点咖啡喝喝", "弄点咖啡喝",
    "搞点咖啡来", "买点咖啡来喝",
    # 偏口味（仍需澄清）
    "想喝杯不太苦的咖啡", "想喝甜一点的咖啡", "想喝杯顺口的咖啡",
    "想喝口感清爽的咖啡", "想喝杯奶味重的咖啡", "想要杯顺滑的咖啡",
    "来杯口味淡的咖啡", "来杯偏甜的咖啡", "来杯偏苦的咖啡",
    # 杯型
    "来杯大杯咖啡", "我要中杯咖啡", "点杯小杯咖啡", "整杯大杯咖啡",
    "来杯超大杯咖啡", "大杯拿铁一杯", "中杯美式一杯",
]

# 多轮 clarify：第一轮用户表达想喝咖啡，第二轮仍然没指明品牌（继续描述需求/口味/杯型/温度等），
# 仍然瑞幸星巴克都能满足
CLARIFY_MULTI_FIRST = [
    "我想喝咖啡", "想喝杯咖啡", "来杯咖啡", "点杯咖啡", "我要喝咖啡",
    "想点咖啡", "推荐杯咖啡", "推荐个饮料", "想喝点东西", "想喝点饮料",
    "好困来点咖啡", "犯困了想喝咖啡", "想提神点咖啡", "我要喝点带咖啡因的",
]
CLARIFY_MULTI_SECOND = [
    "要冰的", "要热的", "要常温的",
    "要大杯的", "要中杯的", "要小杯的",
    "甜一点", "不要太甜", "无糖", "少糖", "半糖", "全糖", "三分糖",
    "去冰", "少冰", "正常冰",
    "加奶", "加点奶", "燕麦奶吧", "豆奶吧", "全脂牛奶", "脱脂牛奶",
    "奶味重一点", "口味清淡一点", "不要太苦", "不要太浓",
    "不要太酸", "顺口一点", "醇一点",
    "拿铁吧", "美式吧", "卡布奇诺吧", "摩卡吧", "澳白吧",
    "拿铁就行", "美式就行", "卡布奇诺就行",
    "热拿铁吧", "冰拿铁吧", "热美式吧", "冰美式吧",
    "再加一份浓缩", "加份浓缩", "双份浓缩",
    "尽快做好", "做好提醒我", "到店再说",
]

# 多轮 clarify：用户说想喝咖啡，第二轮接着补充口味/温度/杯型，但仍然没明确品牌
def gen_clarify_multi():
    rows = []
    seen = set()
    target = min(250, len(CLARIFY_MULTI_FIRST) * len(CLARIFY_MULTI_SECOND))
    max_try = target * 50
    tried = 0
    while len(rows) < target and tried < max_try:
        tried += 1
        first = random.choice(CLARIFY_MULTI_FIRST)
        second = random.choice(CLARIFY_MULTI_SECOND)
        q = f"user:{first}\nassistant:...\nuser:{second}"
        if q in seen:
            continue
        seen.add(q)
        rows.append(q)
    return rows


# ============================================================================
# 2. whatever 语料：明确表达"都可以/随便/听你的/无所谓"
# ============================================================================

# 单轮 whatever：纯粹表达无偏好（带咖啡上下文）
WHATEVER_SINGLE_TURN = [
    "随便点一杯咖啡", "随便来杯咖啡", "随便弄杯咖啡", "随便整杯咖啡",
    "随便给我来杯咖啡", "随便点杯咖啡都行", "随便点都可以",
    "都可以随便点杯咖啡", "随意点一杯咖啡", "随意来一杯咖啡", "随意整杯咖啡",
    "你看着点一杯咖啡", "你看着办点一杯咖啡", "你看着来一杯咖啡",
    "你帮我决定点啥咖啡", "你帮我选一杯咖啡", "你帮我推荐一杯随便",
    "听你的点杯咖啡", "你说了算点杯咖啡", "你来选一杯咖啡",
    "你给我来杯咖啡随便什么都行", "你帮我点一杯咖啡都可以",
    "无所谓点杯咖啡", "无所谓什么咖啡都行", "什么咖啡都可以",
    "哪个咖啡都行", "哪杯咖啡都可以",
]

# 多轮 whatever：从原 luckin sheet 中迁出 + 新增更多扩展
WHATEVER_MULTI_FIRST = [
    "我想喝咖啡", "想喝杯咖啡", "来杯咖啡", "点杯咖啡", "我要喝咖啡",
    "想点咖啡", "推荐杯咖啡", "推荐个饮料", "想喝点东西", "想喝点饮料",
    "好困来点咖啡", "犯困了想喝咖啡", "想提神点咖啡", "我有点想喝咖啡",
    "晚上想喝杯咖啡", "下午想喝杯咖啡", "上午想喝杯咖啡",
    "想点杯奶茶", "想喝点奶茶", "想喝点提神的", "想喝点带咖啡因的",
]
WHATEVER_MULTI_SECOND = [
    "随便", "都行", "都可以", "无所谓", "你看着办", "看你推荐", "随意",
    "任意", "whatever", "你决定", "听你的", "看你的", "都成",
    "都一样", "都好", "你来定", "你来选", "我都喜欢", "我都爱", "我不挑",
    "没意见", "没要求", "什么都行", "哪个都行", "哪个都可以", "你帮我选",
    "你帮我决定吧", "你说了算", "都没问题", "都ok", "都OK",
    "随便都行", "随便就行", "随便点", "随便弄", "都行你看着办",
    "你帮我决定", "你帮我搞定", "你做主", "我没所谓", "我没要求",
]

def gen_whatever_multi():
    rows = []
    seen = set()
    target = min(200, len(WHATEVER_MULTI_FIRST) * len(WHATEVER_MULTI_SECOND))
    max_try = target * 50
    tried = 0
    while len(rows) < target and tried < max_try:
        tried += 1
        first = random.choice(WHATEVER_MULTI_FIRST)
        second = random.choice(WHATEVER_MULTI_SECOND)
        q = f"user:{first}\nassistant:...\nuser:{second}"
        if q in seen:
            continue
        seen.add(q)
        rows.append(q)
    return rows


# ============================================================================
# 3. terminate 语料：明确表达不想点了/算了/取消
# ============================================================================

TERMINATE_SINGLE_TURN = [
    "不点了", "算了不点了", "取消点单", "不要了", "不喝了", "不买了",
    "算了不喝了", "算了不买了", "我不点了", "我不要了", "我不喝了",
    "我不买了", "取消吧", "取消订单", "取消下单", "停止点单",
    "别点了", "先不点了", "暂时不点了", "不点咖啡了", "不喝咖啡了",
    "不买咖啡了", "不要咖啡了", "咖啡不点了", "咖啡不要了",
    "算了取消吧", "算了我不要了", "算了我不喝了", "算了停一下",
    "停一下不点了", "等会儿再说先不点了", "我突然不想喝了",
    "突然不想喝咖啡了", "现在不想点了", "改主意了不点了",
    "改主意不喝了", "改主意取消", "我改主意了不要了",
    "退出点单", "退出咖啡点单", "结束点单", "终止点单",
    "不下单了", "我不想下单", "先取消", "先不要了",
]

TERMINATE_MULTI_FIRST = [
    "我想喝咖啡", "想点杯咖啡", "来杯瑞幸", "来杯星巴克",
    "瑞幸点一杯", "星巴克来一杯", "点杯拿铁", "来杯美式",
    "想喝杯咖啡", "想点杯咖啡外卖",
]
TERMINATE_MULTI_SECOND = [
    "算了不点了", "不点了", "取消吧", "不要了", "不喝了",
    "我改主意了不点了", "突然不想喝了", "先不点了", "暂时不点了",
    "停一下不点了", "我不要了", "取消订单", "取消下单",
    "算了取消", "算了我不喝了",
]

def gen_terminate_multi():
    rows = []
    seen = set()
    target = min(100, len(TERMINATE_MULTI_FIRST) * len(TERMINATE_MULTI_SECOND))
    max_try = target * 50
    tried = 0
    while len(rows) < target and tried < max_try:
        tried += 1
        first = random.choice(TERMINATE_MULTI_FIRST)
        second = random.choice(TERMINATE_MULTI_SECOND)
        q = f"user:{first}\nassistant:...\nuser:{second}"
        if q in seen:
            continue
        seen.add(q)
        rows.append(q)
    return rows


# ============================================================================
# 4. other 语料：与"咖啡点单"无关的车机/通用指令
# ============================================================================

OTHER_SINGLE_TURN = [
    # 多媒体
    "播放音乐", "播放周杰伦的歌", "下一首", "上一首", "暂停音乐", "继续播放",
    "随机播放", "我要听歌", "听点音乐", "放首歌", "放点轻音乐", "放点摇滚",
    "我要听评书", "播放有声书", "播放新闻", "播放电台", "播放新闻广播",
    "播放郭德纲相声", "听个相声", "听个评书", "讲个笑话", "讲个故事",
    # 导航
    "导航回家", "导航去公司", "去最近的加油站", "导航到天安门", "导航到首都机场",
    "去附近的加油站", "去最近的充电桩", "去医院", "去银行", "去超市",
    "怎么去人民广场", "去最近的洗车店", "导航去外滩", "带我去机场",
    "怎么走最近", "怎么走不堵车", "走高速", "不走高速",
    # 车控
    "打开空调", "关闭空调", "调高温度", "调低温度", "温度调到26度",
    "把窗户打开", "关闭车窗", "打开天窗", "关闭天窗", "打开后备箱",
    "关闭后备箱", "解锁车门", "锁车", "打开座椅加热", "关闭座椅加热",
    "打开方向盘加热", "关闭方向盘加热", "打开雨刷", "关闭雨刷",
    "打开远光灯", "关闭远光灯", "打开雾灯", "关闭雾灯",
    # 电话
    "打电话给老婆", "给老板打电话", "拨打10086", "打个电话", "接电话",
    "挂断电话", "回拨刚才那个号码", "给妈妈打电话",
    # 天气与信息
    "今天天气怎么样", "明天会下雨吗", "今天多少度", "今天空气质量",
    "查一下股票", "查一下大盘", "现在几点了", "今天星期几",
    "今天几号", "查一下日历", "现在路况怎么样", "前面堵车吗",
    # 视频
    "我要看电影", "打开腾讯视频", "打开爱奇艺", "看个电视剧",
    "看个综艺", "推荐个电视剧", "看新闻联播",
    # 美食/订餐（非咖啡）
    "附近有什么好吃的", "推荐个川菜馆", "找个火锅店", "查一下附近的餐厅",
    "我想吃火锅", "推荐个海底捞", "找家西餐厅", "我想吃日料",
    "点个外卖披萨", "点个外卖汉堡", "点个外卖盒饭", "我要点外卖麻辣烫",
    "点份外卖米饭", "外卖一份炒饭",
    # 其他闲聊
    "你叫什么名字", "你能干嘛", "今天有什么新闻", "讲点笑话",
    "1+1等于几", "今天农历几号", "你认识我吗", "你几岁了",
    # 取消别的事
    "算了帮我放首歌", "算了导航回家吧", "算了打开空调",
    "不想点了，给我放点音乐", "咖啡不要了，放首歌",
    "不喝咖啡了，导航回家",
    # 改去吃别的
    "改主意了，吃顿饭吧", "不喝咖啡了，找家餐厅", "算了，找个火锅店",
]

OTHER_MULTI_FIRST = [
    "我想喝咖啡", "想点杯咖啡", "想喝点东西", "推荐杯咖啡", "想点杯拿铁",
    "点杯咖啡外卖", "来杯咖啡", "点杯瑞幸", "点杯星巴克", "想喝点饮料",
    "点杯咖啡到公司", "有点困点杯咖啡", "来杯拿铁", "点杯冰美式", "点杯拿铁自取",
]
OTHER_MULTI_SECOND = [
    "算了帮我放首歌", "算了导航回家", "算了打开空调", "改主意了帮我放音乐",
    "改主意了导航去公司", "不喝了，导航回家", "不点了，放首歌",
    "不要了，给我打个电话", "改成放音乐吧", "还是听音乐吧",
    "还是导航去公司吧", "还是打开空调吧", "算了，找家火锅店",
    "不喝咖啡了，找家餐厅", "改主意了，吃顿饭吧", "不要咖啡了，给我设一个闹钟",
    "不喝了，给老婆打个电话", "不点了，帮我查下天气", "算了，打开车窗",
    "不点了，温度调刦30度", "算了，看个电影吧", "不喝了，查下股票",
    "不点了，放点轻音乐", "还是听点相声吧", "还是听点评书吧",
    "不喝了，给我查个股票", "不喝咖啡了，听首歌吧", "不点了，帮我调个闹钟",
    "不喝了，查个航班吧", "不喝咖啡了，让我打个电话先",
    "不点了，帮我预定个餐厅", "不喝了，看看路况",
]

def gen_other_multi():
    rows = []
    seen = set()
    target = min(80, len(OTHER_MULTI_FIRST) * len(OTHER_MULTI_SECOND))
    max_try = target * 50
    tried = 0
    while len(rows) < target and tried < max_try:
        tried += 1
        first = random.choice(OTHER_MULTI_FIRST)
        second = random.choice(OTHER_MULTI_SECOND)
        q = f"user:{first}\nassistant:...\nuser:{second}"
        if q in seen:
            continue
        seen.add(q)
        rows.append(q)
    return rows


# ============================================================================
# 主流程
# ============================================================================

def main():
    if not os.path.exists(INPUT_XLSX):
        raise FileNotFoundError(INPUT_XLSX)

    print(f"📂 读取：{INPUT_XLSX}")
    sheets = pd.read_excel(INPUT_XLSX, sheet_name=None)
    df_meituan = sheets["meituan"].copy()
    df_luckin = sheets["luckin"].copy()
    df_starbucks = sheets["starbucks"].copy()
    print(f"  原始 meituan: {len(df_meituan)} | luckin: {len(df_luckin)} | starbucks: {len(df_starbucks)}")

    # ---- Step 1: 从 luckin 中迁出"末轮随便"样本到 whatever ----
    luckin_query = df_luckin["query"].astype(str)
    move_mask = luckin_query.apply(is_last_turn_whatever)
    moved = df_luckin[move_mask].copy()
    moved["intent"] = "whatever"
    df_luckin = df_luckin[~move_mask].reset_index(drop=True)
    print(f"  ↪️  从 luckin 迁出 {len(moved)} 条 → whatever（剩余 luckin: {len(df_luckin)}）")

    # ---- Step 2: 生成 clarify ----
    clarify_rows = []
    for q in CLARIFY_SINGLE_TURN:
        clarify_rows.append(make_row(f"user:{q}", "clarify"))
    for q in gen_clarify_multi():
        clarify_rows.append(make_row(q, "clarify"))
    df_clarify = pd.DataFrame(clarify_rows, columns=COLS).drop_duplicates(subset=["query"]).reset_index(drop=True)
    print(f"  ➕ clarify: {len(df_clarify)}")

    # ---- Step 3: 生成 whatever（含从 luckin 迁出的 + 新增的）----
    whatever_rows = []
    for q in WHATEVER_SINGLE_TURN:
        whatever_rows.append(make_row(f"user:{q}", "whatever"))
    for q in gen_whatever_multi():
        whatever_rows.append(make_row(q, "whatever"))
    df_whatever_new = pd.DataFrame(whatever_rows, columns=COLS)
    # 与从 luckin 迁出的合并并去重
    df_whatever = pd.concat(
        [moved[COLS] if all(c in moved.columns for c in COLS) else moved.reindex(columns=COLS),
         df_whatever_new],
        ignore_index=True,
    ).drop_duplicates(subset=["query"]).reset_index(drop=True)
    print(f"  ➕ whatever: {len(df_whatever)}（含迁出 {len(moved)} + 新增 {len(df_whatever_new)}）")

    # ---- Step 4: 生成 terminate ----
    terminate_rows = []
    for q in TERMINATE_SINGLE_TURN:
        terminate_rows.append(make_row(f"user:{q}", "terminate"))
    for q in gen_terminate_multi():
        terminate_rows.append(make_row(q, "terminate"))
    df_terminate = pd.DataFrame(terminate_rows, columns=COLS).drop_duplicates(subset=["query"]).reset_index(drop=True)
    print(f"  ➕ terminate: {len(df_terminate)}")

    # ---- Step 5: 生成 other ----
    other_rows = []
    for q in OTHER_SINGLE_TURN:
        other_rows.append(make_row(f"user:{q}", "other"))
    for q in gen_other_multi():
        other_rows.append(make_row(q, "other"))
    df_other = pd.DataFrame(other_rows, columns=COLS).drop_duplicates(subset=["query"]).reset_index(drop=True)
    print(f"  ➕ other: {len(df_other)}")

    # ---- Step 6: 写回 xlsx ----
    print(f"💾 写回：{OUTPUT_XLSX}")
    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        df_meituan.to_excel(writer, sheet_name="meituan", index=False)
        df_luckin.to_excel(writer, sheet_name="luckin", index=False)
        df_starbucks.to_excel(writer, sheet_name="starbucks", index=False)
        df_clarify.to_excel(writer, sheet_name="clarify", index=False)
        df_whatever.to_excel(writer, sheet_name="whatever", index=False)
        df_terminate.to_excel(writer, sheet_name="terminate", index=False)
        df_other.to_excel(writer, sheet_name="other", index=False)

    print("\n=== 完成 ===")
    print(f"  meituan:   {len(df_meituan)}")
    print(f"  luckin:    {len(df_luckin)}")
    print(f"  starbucks: {len(df_starbucks)}")
    print(f"  clarify:   {len(df_clarify)}")
    print(f"  whatever:  {len(df_whatever)}")
    print(f"  terminate: {len(df_terminate)}")
    print(f"  other:     {len(df_other)}")
    total = len(df_meituan) + len(df_luckin) + len(df_starbucks) + \
            len(df_clarify) + len(df_whatever) + len(df_terminate) + len(df_other)
    print(f"  合计:      {total}")


if __name__ == "__main__":
    main()
