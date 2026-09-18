#!/usr/bin/env python3
"""给 query 直接输出工具标注建议（同句先例优先 + 规则兜底）。

用法:
  python3 label.py "今天星期几" --domain 信息查询
  python3 label.py --file queries.txt --domain 音乐
  python3 label.py --jsonl cases.jsonl              # 每行含 domain/last_user 或 messages

输出：建议工具 + 置信度来源 + 依据。参数需人工按 references/domain_rules.md 补全。
置信度：
  EXACT   训练集有同句先例（>=0.95 相似）→ 直接照抄，最可信
  NEAR    高相似先例（>=0.5）→ 参照
  RULE    无先例，按域规则关键词判定
  MANUAL  规则无法判定，需人工
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict

DEFAULT_TRAIN = os.environ.get(
    "WECAR_FC_TRAIN",
    "/Users/rwardzhang/PycharmProjects/wecar_agent/api_agent/train_dataset/"
    "log_annotation_pipeline/runs/webtest/final/train_fc_data_2026.08.24_v3.jsonl",
)

DOM_ALIAS = {
    "出行": "出行工具选择", "travel": "出行工具选择",
    "地点": "地点工具选择", "poi": "地点工具选择",
    "音乐": "音乐工具选择", "music": "音乐工具选择",
    "新闻": "新闻工具选择", "news": "新闻工具选择",
    "speech": "speech工具选择", "语音": "speech工具选择",
    "信息查询": "信息查询工具选择", "info_query": "信息查询工具选择",
    "影院电影": "影院电影工具选择", "video": "影院电影工具选择", "电影": "影院电影工具选择",
}

# 规则表：(域, 正则, 工具, 说明)  —— 顺序即优先级，全部来自训练集实证统计
RULES = [
    # ============================================================
    # 全域优先规则（域名为 "*"，先于域内规则匹配）
    # 这些动作在任何域都没有对应工具，实证 100% unknown
    # ============================================================
    ("*", r"(空调|车窗|天窗|后备箱|座椅(通风|加热)|后视镜|氛围灯|灯光|风扇|冷气|除雾|方向盘加热)",
     "unknown", "车控类：各域合计 200+ 条 100% unknown"),
    ("*", r"(提醒我|新增.{0,3}行程|加个日程|日程|待办|闹钟|备忘|记一下)",
     "unknown", "日程/提醒/备忘：全域无此工具"),
    ("*", r"(拨通|打.{0,4}电话给|给.{0,6}(打个|去个)电话|发(微信|短信)给)",
     "unknown", "通讯外呼：全域 unknown（车机无外呼动作）"),
    ("*", r"(你(的)?名字(是|叫)|怎么称呼你|你是谁|陪我聊|咱聊聊天|聊聊天吧)",
     "unknown", "AI 自身身份/闲聊：9/9 = 100% unknown"),
    ("*", r"(赋.{0,2}诗|来首诗|写(篇|个|首).{0,4}(文章|诗|祝福|爬虫|代码|程序)|讲个笑话|编个)",
     "unknown", "内容创作/编程：全域 unknown"),
    ("*", r"^(你好|您好|嗨|嘿|hi|hello|哈喽|喂|在吗|谢谢|再见|bye)[。，！？!?]?$",
     "unknown", "纯寒暄：全域 unknown"),
    # ===== 信息查询 =====
    ("信息查询工具选择", r"现在几点|几点了", "unknown",
     "「现在几点」33/33 全标 unknown（无时钟工具）"),
    ("信息查询工具选择", r"今天(星期几|周几|几号|多少号)", "web_search",
     "「星期几/几号」18/19 标 web_search（日历可联网查）"),
    ("信息查询工具选择", r"天气|下雨|气温|多少度|冷不冷|热不热", "weather",
     "天气类 → weather；type: 现在/今天→now，明天/未来N天→future，未来N小时/逐小时→hours"),
    # ===== 出行 =====
    ("出行工具选择", r"(违章|限行|扣分|罚款|过路费|高速费|油费|收费站|测速|电子眼|摄像头)",
     "unknown", "车务/路况设施查询：违章限行 78/79、过路费 24/24、测速 24/24 全 unknown"),
    ("出行工具选择", r"(航班|晚点|列车|车次).{0,6}(查|晚|到|信息)?|查.{0,3}(航班|车次)",
     "unknown", "航班/火车动态 15/15 = 100% unknown"),
    ("出行工具选择", r"(我家地址是|我家在哪|公司地址是|父母家在哪|家的地址)",
     "unknown", "记忆槽位反查 68/68 = 100%（『导航回家』是用槽位→navigation；『我家地址是什么』是查槽位→unknown）"),
    ("出行工具选择", r"(打车|出租车|叫.{0,2}车|网约车|滴滴|快车|专车)", "unknown", "打车叫车 41 条 unknown"),
    ("出行工具选择", r"(订|预订|买|退).{0,5}(火车票|机票|门票|民宿|酒店|房)",
     "unknown", "订票/订酒店/退票 50 条 unknown"),
    ("出行工具选择", r"怎么走|多远|几公里|远吗|多久|要多长", "plan_route",
     "521/523 = 99.6%"),
    ("出行工具选择", r"地铁|公交|骑行|步行|走路|打车", "plan_route",
     "249/265 = 94.0%，需带对应 travel_mode"),
    ("出行工具选择", r"(路上|沿途|顺路).{0,8}(找|有|买|加|充|吃)|(找|搜).{0,6}路上", "search_along_route",
     "沿途搜索三参数 keyword|origin|destination"),
    ("出行工具选择", r"行程|攻略|[一二三四五两三四1-9]\s*[日天]游|周边玩|自驾游|度假|怎么玩", "travel_plan",
     "query 需提炼为 9-14 字检索词，剥指代"),
    ("出行工具选择", r"路线", "plan_route", "313/353 = 88.7%"),
    ("出行工具选择", r"^(导航|去|出发|带我去|开车去|回)", "navigation",
     "947/1219 = 77.7%；destination|waypoints"),
    # ===== 音乐 =====
    # ⚠️ 人物问答三分：作品/获奖→web_search，年龄→unknown
    ("音乐工具选择", r"(今年多大|多大了|多大年纪|多大岁数|几岁|年龄|哪年出生)", "unknown",
     "歌手年龄 23/23 = 100% unknown（个人生平不在音乐知识范围内）"),
    ("音乐工具选择", r"(暂停|停下|把歌停|停了|关掉它|切.{0,2}下一首|下一首|上一首|换一首)",
     "unknown", "播放器控制：暂停 33/33、切歌 35/45 unknown"),
    ("音乐工具选择", r"(声音|音量).{0,4}(大|小|调)|调(大|小).{0,3}(声|音)", "unknown",
     "音量控制 26/26 = 100% unknown"),
    ("音乐工具选择", r"(看|显示|要).{0,3}歌词", "unknown",
     "歌词显示 81/119 unknown（用歌词内容搜歌则走 music_search）"),
    ("音乐工具选择", r"(下载|收藏).{0,4}(这首|歌)", "unknown", "下载/收藏 37/38 unknown"),
    ("音乐工具选择", r"(在听的|现在(播|放)的|刚(刚|才).{0,4}(播|放)|正在放).{0,6}(什么|哪首|是)",
     "unknown", "正在播放态查询 8/8 = 100% unknown"),
    ("音乐工具选择", r"(音质|单曲循环|随机播放|倍速)", "unknown", "音质/播放模式 12/13 unknown"),
    ("音乐工具选择", r"(谁在唱这首|这首歌.{0,4}(创作者|谁写)|这歌谁)", "unknown",
     "匿名指代（无歌名）22/70 unknown；有明确歌名才走 music_detail"),
    ("音乐工具选择", r"有哪些代表作", "web_search", "50/54 = 93%"),
    ("音乐工具选择", r"(上过春晚|前奏|音色|哪里人|榜.{0,3}(排名|是什么)|获奖|哪一年)", "web_search",
     "歌手/榜单级知识问答"),
    ("音乐工具选择", r"(创作背景|谁写的|谁唱的|这首歌怎么样|歌.{0,3}(信息|详情))", "music_detail",
     "列表内某首歌的详情"),
    ("音乐工具选择", r"还有(吗|别的|其他)|换一批|下一(页|批)|再来几首|接着看|看看别的", "load_more",
     "须上文有本域列表；无列表则 unknown"),
    ("音乐工具选择", r"第\s*[一二三四五1-9]\s*(首|个).{0,6}(放|播|听|来)|(放|播|来)\s*第\s*[一二三四五1-9]", "play_music",
     "上文有列表+动作词 248/251；无列表→unknown"),
    ("音乐工具选择", r"^(播放|放|来点|来一首|来首|放首|放点|听|我想听|想听)", "music_search",
     "need_play=true；random=true 仅当 query 无指向"),
    ("音乐工具选择", r"^(找一下|搜一下|搜索|查一下|搜下)|推荐", "music_search",
     "need_play=false；query 需剥动词前缀"),
    # ===== 地点 =====
    ("地点工具选择", r"(收藏|分享给|给.{0,4}(写|留)?个?(评价|点评|打分))", "unknown",
     "店铺社交操作：收藏 36/36、分享 17/17、评价 23/33 unknown"),
    ("地点工具选择", r"(WiFi|wifi|无线).{0,4}(密码|吗|有)|这条路叫什么", "unknown",
     "非标属性/道路名：WiFi 29/47、这条路 19/19 unknown"),
    ("地点工具选择", r"(订|预订|定个).{0,4}(位|座|桌)|帮我订第", "unknown",
     "订座 19 条 unknown（无订座工具）"),
    ("地点工具选择", r"还有(吗|别的|其他)|换一批|翻(页|到下一页)|下一(页|批)|再推荐几个", "load_more",
     "须上文有本域列表 392/441 = 88.9%"),
    # ⚠️ 「打电话」不等于 call_telephone！201 条实证：poi_detail 117 / unknown 77 / call_telephone 仅 6
    ("地点工具选择", r"电话是多少", "poi_detail",
     "『X电话是多少』= 查详情 → poi_detail（117/201 主流），不是 call_telephone"),
    ("地点工具选择", r"(打|拨).{0,4}电话|给.{0,6}打个电话", "unknown",
     "『打电话给X』实证 77/201 标 unknown（车机无外呼动作）；"
     "仅当上下文已明确给出号码或序号且需真实拨号才用 call_telephone（全库仅 6 条）"),
    ("地点工具选择", r"第\s*[一二三四五1-9]\s*(个|家|号店)|(评分|人均|营业|地址|停车场|怎么样|详情|简介).{0,6}$", "poi_detail",
     "上文有列表；index|poi_name 二选一填，另一位 -"),
    ("地点工具选择", r"^(搜索|搜一下|查一下|找|查询|附近|周围)|附近|周围|哪里有|推荐", "search_place",
     "纯地点名 → search_query=地点名（不可留 -）；有「附近的X」才拆到 near_address"),
    # ===== 影院电影 =====
    # ⚠️ 人物问答三分：已有作品信息→web_search，"最新作品"/在线看/票房→unknown
    ("影院电影工具选择", r"最新(的)?(作品|片子|电影|剧|新作)|新片是(啥|什么)", "unknown",
     "『X最新的作品是什么』6/6 = 100% unknown（需实时检索，超出 web_search 范围）"),
    ("影院电影工具选择", r"(在线(看|观看|播放)|哪里能看|哪能看|(能|可以)?在哪(儿|里)?看|怎么看)", "unknown",
     "在线观看 20/20 = 100% unknown（无播放工具）"),
    ("影院电影工具选择", r"票房", "unknown", "票房数据 21/21 = 100% unknown"),
    ("影院电影工具选择", r"影院.{0,4}(最近|近|在哪)", "unknown", "影院位置 7/7 = 100% unknown"),
    ("影院电影工具选择", r"幕后花絮|花絮", "unknown", "花絮不属标准详情 → unknown"),
    ("影院电影工具选择", r"^(帮我)?查(一)?下|场次|几点(的|有)|放映|排片|票价|买.{0,3}票|订.{0,3}票", "unknown",
     "查一下 4/4、场次 15/16 全 unknown（无此工具）"),
    ("影院电影工具选择", r"为什么.{0,4}火|经典台词|更新到多少集|常驻嘉宾|哪里人|讲的什么|豆瓣", "web_search",
     "已知作品/艺人的信息问答（233 条全此形态）"),
    ("影院电影工具选择", r"推荐.{0,4}[部个].{0,8}(电影|片|剧|动漫)|推荐几部", "unknown",
     "开放式推荐 81 条中 web_search=0"),
    ("影院电影工具选择", r"(即将上映|还没上映|待映)", "movie_list", "kind=coming"),
    ("影院电影工具选择", r"(最近|现在|正在).{0,4}(有什么|热映|上映).{0,4}电影|有什么电影|电影列表", "movie_list",
     "kind=hot|city"),
    ("影院电影工具选择", r"还有(吗|其他|别的)|换一(批|换)|翻页|下一(页|批)|换点别的|看看别的", "load_more",
     "须上文有列表"),
    ("影院电影工具选择", r"第\s*[一二三四五1-9]\s*部|最后一部|详细说说|介绍一下|简介|谁演|讲什么|评分多少", "movie_detail",
     "index|movie_name"),
    # ===== 新闻 =====
    ("新闻工具选择", r"(早报|晚报|简报|新闻播报)", "news_briefing",
     "when: 早报→morning，晚报→night，简报→auto"),
    # ⚠️ open_news vs news_detail：点开/进入=跳转页面，详情/讲了什么=朗读摘要
    ("新闻工具选择", r"(点开|进入)", "open_news",
     "点开 127/127 = 100%、进入 66/66 = 100% → open_news（跳转详情页）"),
    ("新闻工具选择", r"^打开|打开第|打开.{2,20}(那条|这条)?$", "open_news",
     "打开 159/210 = 76% → open_news"),
    ("新闻工具选择", r"还有(吗|其他|别的)|换一批|下一(页|批)|更多|接着看|再来几条", "load_more", "须上文有列表"),
    ("新闻工具选择", r"(详情|详细|展开说说|条内容|个内容)", "news_detail",
     "详情类 202/206 = 98% → news_detail（朗读摘要，不跳页）"),
    ("新闻工具选择", r"第\s*[一二三四五1-9]\s*(条|个)|具体讲|说说这条|讲了什么", "news_detail",
     "index|title；讲了什么 218/250 = 87%"),
    ("新闻工具选择", r"新闻|资讯|报道|头条", "news_search",
     "仅按分类/地区浏览时 query 留 -；category 必填（无法提取填 -）；region 用省级"),
    # ===== speech =====
    ("speech工具选择", r"(恢复|还是用回|重置|回默认|原来的声音|默认的语音)", "reset_speech", ""),
    ("speech工具选择", r"(粤语|日语|英语|四川话|普通话|东北话|天津话|方言|音色|萝莉|温柔|嗲|语速|快一?点|慢一?点|大点声|小点声|声音大|声音小|音量)",
     "set", "六位固定顺序 lang|emo|sty|role|speed|volume，只填变化位"),
]

# 跨域兜底：本域工具做不到的动作
CANT_DO = r"(交停车费|买.{0,3}(火车|机|门)票|我在哪|位置是哪|系安全带|空调|天窗|车窗|后备箱|备忘|提醒我|新增.{0,3}行程|日程)"

# 上文是否已有本域编号列表。必须同时覆盖两种形态：
#   换行式：  "\n1. 起风了 - 买辣椒也用券\n2) 光年之外 - 邓紫棋"
#   行内式：  "广州正在热映的电影有：1.恶意 2.戏台 3.疯狂动物城3"（影院域主流，258/288）
LIST_PAT = re.compile(
    r"\n\s*1\s*[.、)]"                      # 换行编号
    r"|1\s*[.、]\s*\S+.{0,40}?\s2\s*[.、]"   # 行内 "1.X 2.Y"
    r"|为(你|您)找到"
    r"|共\s*\d+\s*(部|个|条|首)"
    r"|(以下是|为您搜到|找到.{0,6}(如下|以下))"
)


def has_domain_list(ctx: str) -> bool:
    """检测上下文里是否已有本域编号列表（决定序号型/load_more 能否成立）。"""
    return bool(LIST_PAT.search(ctx))


def grams(s, n=3):
    s = re.sub(r"\s+", "", s)
    if len(s) < n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def last_user(text):
    lines = [x for x in text.strip().split("\n") if x.strip()]
    for x in reversed(lines):
        m = re.match(r"^user:?\s*(.*)$", x.strip())
        if m and m.group(1).strip():
            return m.group(1).strip()
    return lines[-1] if lines else ""


def dom_of(sysc):
    m = re.match(r"你是一个(.+?)(助手|专家)", sysc)
    return m.group(1) if m else None


def load_index(path):
    idx = defaultdict(list)
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        sysc = d["messages"][0]["content"]
        if "工具与参数" not in sysc:
            continue
        dn = dom_of(sysc)
        if not dn:
            continue
        lu = last_user(d["messages"][1]["content"])
        idx[dn].append((lu, d["messages"][2]["content"], grams(lu)))
    return idx


def suggest(idx, query, domain, has_list=None):
    """返回 (置信度, 工具, 依据)。has_list=上文是否有本域列表（None=未知）"""
    g = grams(query)
    pool = idx.get(domain, [])
    scored = []
    for lu, gt, tg in pool:
        inter = len(g & tg)
        if inter:
            scored.append((inter / len(g | tg), lu, gt))
    scored.sort(reverse=True)

    # 上下文依赖型工具：必须有本域列表才成立（硬约束，优先于同句先例）
    CTX_DEP = ("load_more", "play_music", "poi_detail", "music_detail",
               "movie_detail", "news_detail", "open_news")

    # 1) 同句先例
    exact = [x for x in scored if x[0] >= 0.95]
    if exact:
        votes = Counter(gt.split("|")[0] for _, _, gt in exact)
        tool, n = votes.most_common(1)[0]
        note = f"同句先例 {len(exact)} 条"
        if len(votes) > 1:
            note += f"  ⚠️ 训练集本身有冲突: {dict(votes)}，需人工裁决"
        # 硬约束：先例给了上下文依赖型工具，但当前上文明确无列表 → 降级 unknown
        if tool in CTX_DEP and has_list is False:
            return ("RULE", "unknown",
                    f"同句先例是 {tool}，但当前上文无本域列表 → 降级 unknown"
                    f"（『第N首』无列表时 125/132 = 94.7% 标 unknown）",
                    [gt for _, _, gt in exact[:2]])
        return "EXACT", tool, note, [gt for _, _, gt in exact[:3]]

    # 2) 规则（域名为 "*" 的全域规则也参与匹配）
    for dn, pat, tool, why in RULES:
        if dn != domain and dn != "*":
            continue
        if re.search(pat, query):
            # 上下文依赖型工具需要上文列表
            if tool in CTX_DEP and has_list is False:
                return "RULE", "unknown", f"命中「{tool}」规则但上文无本域列表 → 降级 unknown（125/132=94.7%）", []
            return "RULE", tool, why, []

    # 3) 做不到的动作 → unknown
    if re.search(CANT_DO, query):
        return "RULE", "unknown", "本域工具做不到的动作", []

    # 4) 近似先例
    near = [x for x in scored if x[0] >= 0.5]
    if near:
        votes = Counter(gt.split("|")[0] for _, _, gt in near[:5])
        tool, _ = votes.most_common(1)[0]
        return "NEAR", tool, f"近似先例 top5 投票 {dict(votes)}", [gt for _, _, gt in near[:3]]

    # 5) 域默认工具
    fallback = {"信息查询工具选择": "web_search", "地点工具选择": "search_place",
                "speech工具选择": "unknown", "影院电影工具选择": "unknown"}
    if domain in fallback:
        return "MANUAL", fallback[domain], f"无先例无规则命中，按域默认给 {fallback[domain]}，请人工确认", []
    return "MANUAL", "?", "无先例无规则命中，需人工按 references/domain_rules.md 判定", []


def report(idx, query, domain, has_list):
    conf, tool, why, ex = suggest(idx, query, domain, has_list)
    mark = {"EXACT": "✅", "RULE": "📐", "NEAR": "≈", "MANUAL": "⚠️"}[conf]
    print(f"{mark} [{conf:<6}] {query[:44]:<46} -> {tool}")
    print(f"          依据: {why}")
    for e in ex:
        print(f"          先例: {e[:70]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?")
    ap.add_argument("--domain", "-d", required=False)
    ap.add_argument("--has-list", choices=["yes", "no"],
                    help="上文是否已有本域编号列表（影响序号型/load_more 判定）")
    ap.add_argument("--file", "-f")
    ap.add_argument("--jsonl", "-j")
    ap.add_argument("--train", default=DEFAULT_TRAIN)
    args = ap.parse_args()

    if not os.path.exists(args.train):
        sys.exit(f"[FATAL] 训练集不存在: {args.train}")
    idx = load_index(args.train)
    hl = {"yes": True, "no": False}.get(args.has_list)

    if args.jsonl:
        for line in open(args.jsonl, encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            if "messages" in d:
                dn = dom_of(d["messages"][0]["content"])
                q = last_user(d["messages"][1]["content"])
                ctx = d["messages"][1]["content"]
            else:
                dn = DOM_ALIAS.get(d.get("domain", ""), d.get("domain"))
                q = d.get("last_user") or last_user(d.get("user", ""))
                ctx = d.get("user", "")
            auto_hl = has_domain_list(ctx)
            report(idx, q, dn, hl if hl is not None else auto_hl)
        return

    dom = DOM_ALIAS.get(args.domain, args.domain) if args.domain else None
    if not dom:
        sys.exit("[FATAL] 需要 --domain（出行/地点/音乐/新闻/speech/信息查询/影院电影）")
    if dom not in idx:
        sys.exit(f"[FATAL] 未知域 {dom}，可选: {sorted(idx)}")

    if args.file:
        for q in open(args.file, encoding="utf-8"):
            q = q.strip()
            if q:
                report(idx, q, dom, hl)
    elif args.query:
        report(idx, args.query, dom, hl)
    else:
        ap.error("需要 query / --file / --jsonl")


if __name__ == "__main__":
    main()
