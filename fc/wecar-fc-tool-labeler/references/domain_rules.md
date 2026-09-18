# 7 个域 × 27 个工具完整边界规则

所有数字来自 `train_fc_data_2026.08.24_v3.jsonl`（29831 条，其中 FC 工具选择 23078 条）实证统计。
非 FC 域（Query 改写专家 6753 条）不在本文件范围内。

---

## 一、出行工具选择域（5736 条 / 6 工具）

### 工具签名

```
plan_route（路线规划/对比路线信息）: origin(起点地址)|destination(终点地址)|travel_mode(交通方式：driving/walking/bicycling/ebicycling/transit，默认driving)
search_along_route（沿途搜索）: keyword(兴趣点类型/名称)|origin(起点地址)|destination(终点地址)
navigation（发起导航到目的地）: destination(目的地地点名)|waypoints(途经点，多个用;分隔)
travel_plan（旅行规划：行程/攻略/周边游/自驾游/找地方玩）: query(完整行程需求描述)
call_telephone（拨打电话）: phone(电话号码)|index(列表序号，从1开始)
unknown（无法匹配任何工具的兜底）: -
```

### 分布

| 工具 | n | 占比 | arity |
|---|---|---|---|
| navigation | 2410 | 42.0% | 2 |
| plan_route | 1343 | 23.4% | 3 |
| unknown | 1092 | 19.0% | 1 |
| search_along_route | 462 | 8.1% | 3 |
| travel_plan | 427 | 7.4% | 1 |
| call_telephone | 2 | 0.0% | 2 |

### 判定规则（按优先级）

1. **含「怎么走 / 多远 / 几公里 / 远吗 / 多久 / 要多长」→ `plan_route`**（521/523 = 99.6%）
2. **含交通方式词「地铁 / 公交 / 骑行 / 步行 / 走路 / 打车」→ `plan_route`** + 对应 travel_mode（249/265 = 94.0%）
3. **含「路线」（名词）→ `plan_route`**（313/353 = 88.7%）
4. **「X 路上 / 沿途 / 顺路 + 找Y」→ `search_along_route`**
5. **「导航 / 去X / 出发 / 带我去 / 开车去」→ `navigation`**（947/1219 = 77.7%）
6. **含「行程 / 攻略 / N日游 / 周边玩 / 自驾游 / 度假」→ `travel_plan`**
7. 本域做不到（买票 / 交停车费 / 问所在区 / 车控）→ `unknown`

**核心区分：要"执行导航动作"→ navigation；要"看信息（距离/耗时/路线对比）"→ plan_route。**

### 参数规则

**navigation**（arity=2）
- `destination`：目的地地点名。可为「家/公司」等记忆槽位，也可为具体地址。`-` 占位仅 31/2410
- `waypoints`：途经点，多个用 `;` 分隔。**无途经点填 `-`**（1487/2410 = 61.7%）
```
先去加油站，再去超市，然后去父母家，最后回家 → navigation|家|加油站;超市;父母家
导航去公司                              → navigation|深圳南山区腾讯滨海大厦|-
```

**plan_route**（arity=3）
- `origin`：起点。当前位置可省略为 `-`（155/1343）
- `destination`：终点，**从不为 `-`**
- `travel_mode` 枚举：`driving` 946 / `walking` 133 / `transit` 116 / `bicycling` 103 / `ebicycling` 36
```
坐地铁回家怎么走      → plan_route|-|杭州西湖区文三路 88 号|transit
骑行从家到公司        → plan_route|家|公司|bicycling
到公司还有几公里      → plan_route|深圳福田区会展中心|公司|driving
```

**search_along_route**（arity=3，顺序 keyword|origin|destination）
- `keyword`：兴趣点类型/名称，**必须语义归一，不得搬 ASR 噪声**
- `origin` `-` 占位 61/462；`destination` `-` 占位 5/462
```
去咖啡店的路上加一个chongwud → search_along_route|充电站|<当前位置>|咖啡店   ← chongwud 必须归一
顺路看看海底捞              → search_along_route|海底捞|<当前位置>|亚洲金融大厦
```

**travel_plan**（arity=1）
- `query`：**完整行程需求描述**，非原话。长度 9-14 字占 66.4%（中位 9 字）
- 结构公式：`[时间/人群] + [城市] + [天数] + [主题] + [方式] + 收尾词`
- 收尾词分布：其他 231 / 攻略 80 / 推荐 61 / 规划·计划 27 / 行程 25
- **含指代词（这个/那个/按照/上面/刚才/这条）的 4/4 全部做了总结改写**
- 不带人数（425 条中含「朋友」0 条、含具体人数 0 条）
```
按照这个路线帮我规划一条自驾路线 → travel_plan|武汉三日赏樱自驾路线规划
我周末有两个朋友来深圳         → travel_plan|周末深圳两日游行程规划
帮我规划一条自驾路线          → travel_plan|规划一条腾讯武汉研发中心到苏州站自驾路线
```

**unknown 典型**
```
今天星期几 / 现在几点了 / 我在哪个区 / 我现在的位置是哪儿
帮我交停车费 / 帮我买张去北京的火车票 / 17点我要接孩子，新增一个行程
```

---

## 二、地点工具选择域（4861 条 / 5 工具）

### 工具签名

```
search_place（地点搜索）: search_query(搜索关键词)|near_address(中心点地址)
poi_detail（列表内地点详情）: index(列表序号)|poi_name(地点名，index 兜底)
load_more（加载更多/翻下一页，须有上一轮同域列表）: -
call_telephone（拨打电话）: phone(电话号码)|index(列表序号)
unknown（无法匹配任何工具的兜底）: -
```

### 分布

| 工具 | n | 占比 | arity |
|---|---|---|---|
| search_place | 2465 | 50.7% | 2 |
| poi_detail | 1174 | 24.2% | 2 |
| unknown | 1006 | 20.7% | 1 |
| load_more | 208 | 4.3% | 1 |
| call_telephone | 8 | 0.2% | 2 |

### 判定规则

1. **要找地点/品类 → `search_place`**
2. **问列表内某项的详情（评分/人均/营业时间/电话/地址/有无停车场）→ `poi_detail`**
   - 区分度词：`号店的详` `家人均多` `几点` `个怎么样` `体讲讲` `个营业到` `分怎样` `家电话是` `停车场吗`
3. **「还有吗/换一批/翻页/再推荐几个」+ 上文有列表 → `load_more`**
4. **要打电话 → `call_telephone`**
5. 本域做不到 → `unknown`

### 参数规则

**search_place**（arity=2，顺序 search_query|near_address）

⚠️ **最易错点**：「搜索**纯地点名**」110 条实证 → **search_query = 地点名 101 条（91.8%），search_query = `-` 为 0 条**

```
✅ 搜索深圳湾公园              → search_place|深圳湾公园|-
✅ 搜索深圳南山               → search_place|深圳南山|广东省深圳市腾讯大厦
❌ 搜索深圳市南山区粤海街道腾讯滨海大厦 → search_place|-|深圳市南山区粤海街道腾讯滨海大厦   ← 参数颠倒！
✅ 同上                     → search_place|深圳市南山区粤海街道腾讯滨海大厦|-
✅ 搜索腾讯大厦附近的餐厅        → search_place|餐厅|深圳腾讯大厦              ← 有"附近的X"才拆开
```

`near_address` 分布（1211 条搜地点本身场景）：其他地点 708 / **`-` 317** / 当前位置 186 → **`-` 与当前位置都合法**

**poi_detail**（arity=2，顺序 index|poi_name）
- `index` 枚举：`-` 406 / `2` 268 / `1` 261 / `3` 238 / `4` 1
- **有序号填 index、poi_name 留 `-`；有地点名填 poi_name、index 留 `-`**（713/1174 为 `-`）
```
1号店的详情       → poi_detail|1|-
第三家评分怎样     → poi_detail|3|-
亚朵酒店营业到几点   → poi_detail|-|亚朵酒店
建设银行ATM要预约吗 → poi_detail|-|建设银行ATM
```

**call_telephone**（arity=2，顺序 phone|index）

⚠️ **「打电话」≠ call_telephone！** 201 条含「打电话/电话是多少/拨」的实证：

| 标注 | n | 场景 |
|---|---|---|
| **poi_detail** | **117 (58.2%)** | `X电话是多少` = 查详情 |
| **unknown** | **77 (38.3%)** | `打电话给X` = 要执行外呼动作，车机做不到 |
| call_telephone | **6 (3.0%)** | 上下文已明确给出号码/序号且要真实拨号 |
| set | 1 | 误标 |

```
第一个电话是多少   → poi_detail|1|-          ← 查详情，不是打电话
全季酒店电话是多少  → poi_detail|-|全季酒店
打电话给这家店     → unknown|-              ← 要执行外呼，做不到
打电话给第二家     → unknown|-
拨打这家店电话     → unknown|-
打这个电话 028-85551234 → call_telephone|028-85551234|-   ← 号码已给全
第一家电话是多少    → call_telephone|-|1     ← 少数写法，与 poi_detail 冲突
```

**判定顺序：问号码 → poi_detail；要拨号 → unknown；号码已在上下文且明确要拨 → call_telephone。**
`给第一家打个电话` 训练集有 **两种标注冲突**（unknown 与 call_telephone 各 1），属噪声，建议统一为 unknown。

### 跨域边界

poi 域含「电影/热映」54 条：`search_place` 36（找**电影院**=场所）/ `unknown` 18（订票、找**影片内容**）
```
帮我找附近电影院              → search_place|电影院|...
搜索深圳南山区附近正在热映的电影   → unknown|-            ← 求影片内容，非场所
帮我订张电影票               → unknown|-
```

---

## 三、音乐工具选择域（4498 条 / 6 工具）

### 工具签名

```
web_search（音乐知识联网搜索，歌曲基础信息/创作背景/音乐特点/获奖经历等音乐领域知识问答，不用于搜歌或播歌）: -
music_search（音乐搜索）: query(用户原始搜索语句)|need_play(true/false)|random_search(true/false)
music_detail（列表内歌曲详情）: index(列表序号)|title(歌名，index 兜底)
play_music（播放指定歌曲）: index(列表序号)|song_name(歌名)
load_more（加载更多/翻下一页，须有上一轮同域列表）: -
unknown（无法匹配任何工具的兜底）: -
```

### 分布

| 工具 | n | 占比 | arity |
|---|---|---|---|
| music_search | 1559 | 34.7% | 3 |
| unknown | 956 | 21.3% | 1 |
| play_music | 864 | 19.2% | 2 |
| music_detail | 579 | 12.9% | 2 |
| web_search | 383 | 8.5% | 1 |
| load_more | 157 | 3.5% | 1 |

### 判定规则

```
有明确歌名/歌手/风格 + 要搜或听 → music_search
指定列表序号 + 播放动作        → play_music
问某首歌"怎么样/创作背景/谁写的/什么特点" → music_detail
问歌手/榜单"有哪些代表作/上过春晚/前奏什么音色/哪里人" → web_search
「还有吗/换一批/再来几首」+ 上文有列表 → load_more
上文无歌曲列表却说"第N首" / 本域做不到（消人声/收藏管理）→ unknown
```

**`web_search` vs `music_detail` 的分界**：
- `music_detail` = **列表内**某首歌的详情（`第三首歌怎么样` / `富士山下的创作背景`）
- `web_search` = **歌手/榜单/专辑级**的知识问答（`田馥甄有哪些代表作？` / `《天黑黑》前奏用了什么音色？`）

**`XX有哪些歌` / `XX有哪些代表作`**：
| 模式 | n | web_search | music_search |
|---|---|---|---|
| 有哪些代表作 | 39 | **39 (100%)** | 0 |
| 有哪些歌 | 14 | 11 (78.6%) | 3 |

例外 3 条特征：纯歌手名 + 无书名号 → query 提炼成 `X的歌曲`
```
邓紫棋有哪些歌 → music_search|邓紫棋的歌曲|false|false
刘德华有哪些代表作？ → web_search|-
《魔杰座》这张专辑都有哪些歌？ → web_search|-
```

### 序号型两级决策树（578 条实证，命中率 99%+）

```
「第N首」
├── 上文有歌曲列表（578 条）
│   ├── 播放动作词（放/播/听/来）→ play_music   248/251 = 98.8%
│   └── 询问词（怎么样/介绍/谁/背景/什么/信息）→ music_detail  218/219 = 99.5%
└── 上文无歌曲列表（132 条）→ unknown  125/132 = 94.7%
```

### music_search 参数规则（arity=3）

**`query`：67.1% 是提炼改写，仅 32.9% 原话复刻**

「找一下/搜一下/搜索」开头 **100% 剥掉动词前缀**：
```
找一下林宥嘉的歌曲 → query=林宥嘉的歌曲
找一下周深的歌     → query=周深的歌曲          （补"曲"）
搜一下光年之外     → query=邓紫棋的光年之外      （补歌手名）
搜一下江南 林俊杰   → query=林俊杰的江南         （重排为"歌手的歌名"）
搜索邓紫棋的热门歌曲 → query=邓紫棋热门歌曲       （去"的"）
```

**`need_play` / `random_search` 按句式分桶（1559 条）**

| 句式 | true\|false | true\|true | false\|false | false\|true |
|---|---|---|---|---|
| 播放/来点/放/听 | **559** | 56 | 1 | 0 |
| 我想听 | **143** | 10 | 0 | 0 |
| 找一下/搜一下/搜索 | 3 | 0 | **48** | 0 |
| 推荐 | 0 | 0 | **19** | 3 |
| 其他 | 457 | 41 | 219 | 0 |

**`random_search=true` 仅当 query 完全无指向**（`query='-'` 共 108 条，句式：播放/来点 55、其他 40、我想听 10、推荐 3）：
```
来点音乐 / 放首歌听听 / 播放音乐 / 随便放点音乐吧 → music_search|-|true|true
```

⚠️ **风格词（轻松/安静/舒缓/治愈）也算有指向 → random=false**（62 条实证几乎全 `true|false`）：
```
播放轻松的音乐   → music_search|播放轻松的音乐|true|false     ← 不是 true|true
来点安静舒缓    → music_search|来点安静舒缓|true|false
播放轻松风格的歌曲 → music_search|-|true|true                ← query='-' 才 random=true
```

`false|true` 全库仅 2 条：`推荐两首歌。` / `推荐些我喜欢听的歌`，**query 均为 `-`**

### play_music / music_detail 参数

**play_music**（arity=2，顺序 index|song_name）：`index` 枚举 `-` 335 / `1` 272 / `2` 142 / `3` 115；`song_name` `-` 占位 520
```
放第2首   → play_music|2|-
来一首起风了 → play_music|-|起风了
```

**music_detail**（arity=2，顺序 index|title）：`index` 枚举 `-` 257 / `1` 128 / `2` 111 / `3` 82
```
第三首歌怎么样  → music_detail|3|-
富士山下的创作背景 → music_detail|-|富士山下
```

---

## 四、新闻工具选择域（2794 条 / 6 工具）

### 工具签名

```
news_search（新闻搜索）: query(从用户语句中提炼的核心实体/关键词，去掉修饰词；仅按分类或地区浏览新闻时留空，勿与category/region重复)|category(新闻类型)|region(省级/直辖市，无法提取填-)
news_briefing（新闻早报/晚报）: when(时段：morning早报/night晚报/auto自动)
news_detail（列表内新闻详情）: index(列表序号)|title(新闻标题，index 兜底)
open_news（打开新闻详情页）: index(列表序号)|title(新闻标题)
load_more（加载更多/翻下一页，须有上一轮同域列表）: -
unknown（无法匹配任何工具的兜底）: -
```

`category` 33 种枚举：热点/要闻/财经/房产/健康/数码/军事/国际/体育/生活/汽车/农业/美食/旅游/历史/电视剧/科技/教育/综艺/育儿/游戏/文化/娱乐/音乐/摄影/社会/情感/动物/电影/动漫/时尚/搞笑/科学

### 分布

news_search 1147 (41.1%) / news_detail 617 (22.1%) / 其余见下

### news_search 参数规则（arity=3）

**`query` 留空规则**（1147 条）：

| 组合 | n |
|---|---|
| query 有值 + region 空 | 530 |
| **query 空 + region 空** | **439** |
| **query 空 + region 有值** | **168** |
| query 有值 + region 有值 | 10 |

→ **仅按分类/地区浏览时 query 留 `-`**（607/1147 = 52.9%）：
```
看看军事相关新闻   → news_search|-|军事|-
北京科技新闻      → news_search|-|科技|北京
山东的新闻看看     → news_search|-|要闻|山东     ← 无分类词时 category 兜底填「要闻」
看看新闻         → news_search|-|要闻|-
深圳这两天有什么新闻吗？ → news_search|-|要闻|广东    ← region 用省级
```

有具体实体则 query 填**提炼后的核心实体**（去修饰词），不与 category/region 重复。

**`region` 用省级/直辖市**，不用市级：`深圳` → `广东`、`南京` → `江苏`、`成都` → `四川`

**news_briefing**（arity=1）：`when` 枚举 morning/night/auto
```
今日新闻早报          → news_briefing|morning
播报一下今晚的新闻晚报    → news_briefing|night
来份新闻简报 / 获取今日新闻简报 → news_briefing|auto
```

---

## 五、speech 工具选择域（2182 条 / 3 工具）

### 工具签名

```
set（切换AI朗读语音参数）: lang(朗读语种)|emo(朗读情绪)|sty(演绎风格或语气)|role(角色音色)|speed(语速调整档位)|volume(音量调整档位)
reset_speech（恢复默认语音参数）: -
unknown（非语音参数切换的兜底）: -
```

### 分布

| 工具 | n | 占比 | arity |
|---|---|---|---|
| unknown | 1171 | 53.7% | 1 |
| set | 872 | 40.0% | **6** |
| reset_speech | 139 | 6.4% | 1 |

### 判定规则

- **要求改语种/情绪/风格/音色/语速/音量 → `set`**
- **要求"恢复默认/还是用回原来的/全部重置" → `reset_speech`**（区分度词：`还是用回` `默认的语` `恢复默认` `算了`）
- **非语音参数切换的一切内容 → `unknown`**（占 53.7%，本域是纯二分类 + 兜底）

### set 参数规则（arity=6，六位固定顺序，只填变化的位，其余 `-`）

| 位 | 参数 | 取值 |
|---|---|---|
| 0 | `lang` | `-` 620 / 粤语 95 / 日语 51 / 四川话 48 / 普通话 30 / 英语 28 |
| 1 | `emo` | 10 种，`-` 占位 700 |
| 2 | `sty` | 15 种（温柔等），`-` 占位 724 |
| 3 | `role` | `-` 674 / `1`-`5`（音色编号） |
| 4 | `speed` | 10 种（`default` / `-1` / `2` 等档位），`-` 占位 656 |
| 5 | `volume` | 10 种，`-` 占位 685 |

```
用广东话温柔地跟我说说 → set|粤语|-|温柔|-|-|-
讲慢一点，听不清     → set|-|-|-|-|-1|-
换成四川辣妹的声音讲   → set|-|-|-|1|-|-
又太慢了          → set|-|-|-|-|default|-
```

---

## 六、信息查询工具选择域（1589 条 / 3 工具）

### 工具签名

```
weather（天气查询）: address(地区名)|weather_type(天气类型：now实时/future未来/hours逐小时)
web_search（通用联网搜索，信息查询默认工具，无需提取）: -
unknown（无法匹配任何工具的兜底）: -
```

### 分布

| 工具 | n | 占比 | arity |
|---|---|---|---|
| web_search | 797 | 50.2% | 1 |
| weather | 524 | 33.0% | 2 |
| unknown | 268 | 16.9% | 1 |

### 判定规则

1. **问天气 → `weather`**
2. **其他一切时效性/知识性信息查询 → `web_search`**（本域默认工具，占 50.2%）
3. **本域做不到（车控/记事/闲聊/创作）→ `unknown`**

### ⚠️ 时间类必须分开统计（曾在此栽过）

| query 模式 | 命中 | 标注 |
|---|---|---|
| 含「现在几点」 | 33 | **unknown 100%** |
| 含「今天星期几 / 今天周几」 | 19 | **web_search 18 / unknown 1** |
| 含「今天几号 / 今天多少号」 | 1 | **web_search** |

**规则：问「几点」→ unknown（无时钟工具且不该联网查时间）；问「星期几/几号」→ web_search（日历信息可联网查）。**

⚠️ 千万别用 `(星期几|几号|几点)` 混统 —— 33 条「几点」会把结果压成假的 "unknown 主流"。
这是我第一、二轮都判错的地方。

### weather 参数规则（arity=2）

**`address` 只到市/区级 —— 522 条中含「大厦/大楼/园区」的为 0 条**
- 长度分布：min=2 / **P50=2** / P90=6 / max=28
- 形态：短城市名（≤3字）306 (58.6%) / 省市区级 150 (28.7%) / 其他市区 65 (12.5%)

```
✅ 明天天气怎么样 → weather|深圳市南山区|future
❌ 明天天气怎么样 → weather|广东省深圳市南山区腾讯滨海大厦(白石路东)|future   ← 22 字含楼宇，0 条先例
```

**`weather_type` 触发词**

| 值 | n | 高频触发词 |
|---|---|---|
| `now` | 188 | 现在 65 / 今天 55 / 这会 9 / 此刻 4 |
| `future` | 236 | 明天 79 / 未来 37 / 后天 23 / 一周 16 / 这周 12 |
| `hours` | 98 | 几点 15 / 未来 15 / 下午 12 / 24小时 12 / 逐小时 7 / 每小时 3 |

**关键区分：「未来 N 小时 / 逐小时 / 每小时 / 具体几点」→ `hours`；「未来 N 天 / 一周 / 明天」→ `future`。**
```
深圳未来12小时的天气。 → weather|深圳|hours     ← 不是 future
那杭州西湖未来一周的天气呢？ → weather|杭州西湖区|future
重庆天气怎么样 → weather|重庆|now
```

⚠️ 训练集自身有 **2 条 `weather_type='no w'`**（now 中间多空格）脏数据，建议修。

---

## 七、影院电影工具选择域（1418 条 / 5 工具）

### 工具签名

```
movie_list（影院当前档期电影列表）: kind(hot热映/coming待映，默认hot)|city(城市名)
movie_detail（列表内电影详情）: index(列表序号)|movie_name(电影名，index 兜底)
web_search（影视内容联网搜索，非影院上映的电影/电视剧/综艺/动漫/纪录片等视频内容搜索与询问）: -
load_more（加载更多/翻下一页，须有上一轮同域列表）: -
unknown（无法匹配任何工具的兜底）: -
```

### 分布

| 工具 | n | 占比 | arity |
|---|---|---|---|
| unknown | 427 | 30.1% | 1 |
| movie_list | 318 | 22.4% | 2 |
| movie_detail | 288 | 20.3% | 2 |
| web_search | 233 | 16.4% | 1 |
| load_more | 152 | 10.7% | 1 |

### 四工具边界（本域最易错）

| 工具 | 适用 | 实证 |
|---|---|---|
| `movie_list` | 要**当前档期列表** | 区分度词：`有什么电` `即将上映` `还没上映` `现在有什` |
| `movie_detail` | 列表内某部片的详情 | 区分度词：`部的简介` `详细说说` `看看第` `最后一部` `部是谁演` `讲什么` `分多少` |
| `web_search` | **已知作品/艺人的具体信息问答** | 区分度词：`为什么这么火` `的常驻嘉宾` `动画更新到多少集` `的经典台词` `哪里人` |
| `load_more` | 承接上轮列表要更多 | 区分度词：`看看别的` `换一批看` `翻页` `换一换` `换点别的` |
| `unknown` | ①开放式推荐 ②场次/票价/购票 ③含糊无检索意图 | 区分度词：`推荐几部` |

### web_search 不覆盖的三类（233 条全是"已知对象的信息问答"）

```
✅ 《狂飙》为什么这么火？        → web_search|-
✅ 雷佳音是哪里人？             → web_search|-
✅ 《进击的巨人》更新到多少集了？   → web_search|-
✅ 《辛德勒的名单》经典台词有哪些？  → web_search|-
```

| 不该走 web_search 的场景 | 实证 |
|---|---|
| **开放式推荐** | 推荐类 81 条：unknown 42 / movie_list 24 / load_more 15 / **web_search 0** |
| **场次/票价/购票** | 含「场次/几点/放映/排片」16 条：**unknown 15** / movie_list 1 |
| **「查一下/帮我查一下」开头** | 4 条：**unknown 4 (100%)** |

```
❌ 帮我推荐一个科幻的，评分高的电影 → web_search    应为 unknown|-
❌ 帮我查一下吧。（查明天场次）    → web_search    应为 unknown|-
✅ 查询上海正在热映且评分高的电影   → movie_list|hot|上海   ← 明确"正在热映"才走列表
✅ 历史上评分最高的电影         → unknown|-
✅ 帮我推荐一部热血动漫，不要剧场版  → unknown|-
```

**含糊指代一律 unknown**：`追光？` / `播行吗？` / `我看一下啊。` / `是这个意思吗？` / `我看有没有。`

### 参数规则

**movie_list**（arity=2）：`kind` 枚举 `hot` 223 / `coming` 95；`city` 17 种，`-` 占位 28
**movie_detail**（arity=2，顺序 index|movie_name）：`index` 枚举 `-` 65 / `1`-`6`；`movie_name` `-` 占位仅 10

---

## 附：load_more vs unknown 通用判据（跨域，441+428 条实证）

```
「还有吗 / 换一批 / 下一页 / 下一批 / 别的 / 再来几个 / 接着看 / 换一换 / 更多」
├── 上一轮 assistant 给了本域编号列表 → load_more   392/441 = 88.9%
└── 上一轮无列表                     → unknown 41.1% / 该域主搜索工具
```
