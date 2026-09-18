---
name: wecar-fc-tool-labeler
description: 车机 Agent function-calling 训练数据的工具选择标注器与日志回标器。给定 query（单轮或多轮上下文）与所在业务域，可判定应调用哪个工具、参数怎么填，并输出 train_fc_data 格式的训练样本；也支持接收每天的线上日志导出，按工具职能说明文档筛出错误数据，并只基于错误数据生成新的训练数据。覆盖 7 个域（出行/地点/音乐/新闻/speech/信息查询/影院电影）共 27 个工具的边界规则，全部规则来自 29831 条训练集实证统计。当用户要求"标注这批 query 用哪个工具"、"审核标注是否正确"、"每天日志里哪些是错的"、"根据错误日志回标训练数据"、"把错误样本转训练集"时触发。Trigger: 工具选择, 标注, gt, function calling, fc, unknown 兜底, 工具边界, api_agent, train_fc_data, 日志审计, 错误数据, 日志回标, 回标训练集
agent_created: true
---

# 车机 FC 工具选择标注器

给一条 query 就输出应该调哪个工具、参数怎么填。所有规则来自 `train_fc_data` 29831 条实证统计，不是主观判断。

## 快速上手

```bash
S=~/.workbuddy/skills/wecar-fc-tool-labeler/scripts

# 1) 单条自动标注（核心用法）
python3 $S/label.py "今天星期几" -d 信息查询
python3 $S/label.py "放第2首" -d 音乐 --has-list yes     # 上文有列表
python3 $S/label.py "放第2首" -d 音乐 --has-list no      # 上文无列表 → 降级 unknown

# 2) 批量：纯文本每行一条 / jsonl（自动识别 domain 与上文列表）
python3 $S/label.py --file queries.txt -d 出行
python3 $S/label.py --jsonl cases.jsonl

# 3) 查同句先例（拿不准时必查）
python3 $S/find_similar.py "播放轻松的音乐" -d 音乐

# 4) 标注完过质量门禁
python3 $S/audit_labels.py your_labels.jsonl --csv errors.csv

# 5) 转可训练格式
python3 $S/to_trainable.py src.jsonl -o out.jsonl

# 6) 从原始日志抽取 tool_select 样本
python3 $S/extract_tool_select_logs.py raw_export.json -o extracted_cases.jsonl --csv extracted_cases.csv

# 7) 审计线上日志时，最终只交付“错误数据”
# 错误数据至少包含：case_id / query / 上下文历史消息 / original_answer / corrected_answer / reason

# 8) 只基于“错误” verdict 回标成新的训练样本
python3 $S/build_relabel_train.py extracted_cases.jsonl reviewed.csv -o relabeled_from_errors.jsonl --verdict-only 错误 --keep-meta

# 9) 再转可训练格式
python3 $S/to_trainable.py relabeled_from_errors.jsonl -o relabeled_from_errors.trainable.jsonl
```

域名可用简称：`出行 / 地点 / 音乐 / 新闻 / speech / 信息查询 / 影院电影`
训练集路径可用 `WECAR_FC_TRAIN` 环境变量覆盖，默认指向
`wecar_agent/api_agent/train_dataset/log_annotation_pipeline/runs/webtest/final/train_fc_data_2026.08.24_v3.jsonl`

### label.py 的置信度含义

| 标记 | 含义 | 实测准确率 |
|---|---|---|
| ✅ `EXACT` | 训练集有同句先例（相似度≥0.95）→ **直接照抄** | **99.1%**（覆盖 98.9%） |
| 📐 `RULE` | 无先例，按域规则关键词判定 | 69.2% —— **需人工复核** |
| ≈ `NEAR` | 高相似先例投票（≥0.5） | 参照 |
| ⚠️ `MANUAL` | 规则无法判定 → 查 `references/domain_rules.md` 人工定 | — |

**整体工具名准确率 98.75%**（1200 条留一回测）。改了规则后跑 `backtest.py` 确认无回退。

同句先例若训练集本身有冲突，会自动告警：
```
✅ [EXACT] 今天星期几 -> unknown
   依据: 同句先例 3 条  ⚠️ 训练集本身有冲突: {'web_search': 1, 'unknown': 2}，需人工裁决
```

## 输出格式

单行 JSONL，`assistant` 为 `工具名|参数1|参数2|...`（管道分隔，无值填 `-`）：

```json
{"messages":[{"role":"system","content":"<该域的工具声明>"},{"role":"user","content":"【用户记忆】…\n【当前位置】…\n【上下文对话信息】\nuser: …"},{"role":"assistant","content":"navigation|深圳南山区腾讯滨海大厦|-"}]}
```

- 顶层键**只要 `messages`**（`_meta` 不参与训练，见 references/format.md）
- role 序列恒为 `system` / `user` / `assistant`
- assistant **不得有前后空白、不得含换行、不得含 `<think>`**、分隔符 `|` 两侧不留空格

## 参考文档（判定时按需读取）

| 文件 | 何时读 |
|---|---|
| **`references/工具职能说明.md`** | **主参考。** 判定 query 归属时先读这个 —— 27 个工具逐个展开的详细边界说明（核心职责、必要前提、绝不能落它的情况、与相邻工具的切分）、参数格式、**结合上下文/当前位置/指代承接的参数提取规则**、具体 query→标准输出示例、易错反例、全局规则 |
| `references/domain_rules.md` | 需要更细的参数约束时再读 —— arity、枚举取值、参数分布统计、触发词命中率 |
| `references/log_audit_workflow.md` | 用户给了每天日志导出文件，希望筛出错误数据并只基于错误数据生成新的训练数据时必读 —— 定义最终交付物、reviewed.csv 过滤口径、错误样本回标流程 |

## 每日日志审计与回标工作流

当用户提供每天的线上日志导出，并要求“根据职能说明文档找出错误数据 + 基于错误数据生成新的训练数据”时，按下面顺序执行：

1. **先抽日志，不要直接对原始导出文件做人工逐条阅读**
   - 运行 `scripts/extract_tool_select_logs.py`
   - 只抽 `tool_select` 样本，保留 `case_id / timestamp / domain / system / user / query / location / context / original_answer`

2. **按 `references/工具职能说明.md` 逐条裁决，但最终只保留错误样本**
   - 先定域
   - 再看上下文继承 / 列表依赖 / 消歧补槽
   - 再判工具边界与参数提取
   - 对每条样本得到 `verdict / corrected_answer / reason`
   - `verdict=正确` 或 `可接受但建议优化` 的样本不作为最终交付物

3. **生成错误数据明细**
   - 最终交付给用户的明细只保留 `verdict=错误` 的 case
   - 至少包含：`case_id, query, context, original_answer, corrected_answer, reason`
   - `corrected_answer` 直接作为后续生成新训练数据的监督答案

4. **只基于错误样本生成 reviewed.csv / 回标训练集**
   - `reviewed.csv` 至少要有：`case_id, verdict, original_answer, md_answer, final_train_answer, use_for_training, reason`
   - 只有 `verdict=错误` 且可直接入训的 case 才写 `use_for_training=yes`
   - 运行 `scripts/build_relabel_train.py ... --verdict-only 错误`
   - 只改 `assistant`，**绝不改 `user`**
   - 若需要追溯，可用 `--keep-meta` 保留 `case_id / original_answer / verdict / reason`

5. **回标后必须过质量门禁再训练**
   - 先跑 `scripts/audit_labels.py`
   - 再跑 `scripts/to_trainable.py`
   - 最终交付给用户的训练文件只包含“错误样本生成的新数据”

## 高风险坑位（POI 参数提取）

- **纯地点名默认是目标对象，不是中心点**：`搜深圳湾公园` 应是 `search_place|深圳湾公园|-`，不能写成 `search_place|-|深圳湾公园`
- **`附近/周边/这附近` 才触发中心点抽取**：`腾讯大厦附近的咖啡店` 才拆成 `search_query=咖啡店`、`near_address=腾讯大厦`
- **默认从当前位置出发时，出行域起点通常填 `-`**：`plan_route` / `search_along_route` 只有在显式给出起点时才填 `origin`
- **上下文承接只在对象唯一时成立**：`这家/那边/去那儿` 这类指代，必须能唯一回指到上文 POI，否则不要硬补参数
- **补槽式短回复不是新任务**：上一轮 assistant 刚问“杭州还是苏州”“什么时候出发”“第几个”，当前轮只回“苏州吧 / 五一 / 第一个吧”时，应继承上一轮待确认的意图与槽位，不能默认打成 `unknown`
- **消歧轮先判断“新确认槽位”是否正确**：像“到高铁站近的那个”“第一个”“苏州吧”这类回复，先看当前轮是不是把候选 destination / index / city 选对了
- **消歧轮的旧参数是否必须重写，要区分口径**：若训练标签要求每条输出自包含，则应回填上一轮已锁定的 `waypoints` / `near_address` / 其他筛选条件；若是线上日志审计或运行态补槽，系统可能已保留旧参数，此时不要仅因未重写旧参数就把 case 直接判成错误。例如“导航到万达广场，途经同庆楼(银湖店)”后接“到高铁站近的那个”，`navigation|芜湖镜湖万达广场|-` 至少应先判 destination 正确
- **`路上/顺路/沿途` 必须真的有路线语境**：没有当前终点或既有路线，不要把“顺路找个加油站”硬标成 `search_along_route`
- **`plan_route` 的多站点 query 允许 schema 压缩**：当用户问“从A出发，先去B，再去C 的驾车路线”时，工具仍是 `plan_route`；由于当前只有 `origin|destination|travel_mode` 三个位，输出允许只保留 `origin=A`、`destination=C`、`travel_mode=driving`，不要因为中间站 B 没编码进 assistant 就判错
- **影院域“推荐个电影看看”默认可压成热映片单**：如果用户只是泛泛想看电影，没有题材/评分/人群等附加约束，`movie_list|hot|城市` 是合法答案；只有带明显偏好约束的推荐（如“高分科幻”“适合情侣”）才应进 `unknown`

## 标注三步法

### 第 1 步：定域

看 system 首句 `你是一个XX工具选择助手`。7 个域各自的工具集互不通用——**不能跨域选工具**。

| 域 | 工具集 |
|---|---|
| 出行 | navigation / plan_route / search_along_route / travel_plan / call_telephone / unknown |
| 地点 | search_place / poi_detail / load_more / call_telephone / unknown |
| 音乐 | music_search / play_music / music_detail / web_search / load_more / unknown |
| 新闻 | news_search / news_detail / news_briefing / open_news / load_more / unknown |
| speech | set / reset_speech / unknown |
| 信息查询 | weather / web_search / unknown |
| 影院电影 | movie_list / movie_detail / web_search / load_more / unknown |

### 第 2 步：查同句先例（**最重要，别跳过**）

**凡训练集里有逐字相同或高度相似的 query，一律照抄它的标注。** 这条铁律能避免绝大多数错标：

```bash
python3 ~/.workbuddy/skills/wecar-fc-tool-labeler/scripts/find_similar.py "你的query" --domain 音乐
```

实证：曾有一批 35 条标注，13 条必改全部源于没查同句先例。
`label.py` 已内置这一步（EXACT 层覆盖 98.9% 且准确 99.1%）。

### 第 3 步：按职能边界判定

**读 `references/工具职能说明.md`** —— 每个工具的职能范围、不属于本域能力的清单都写清了。判定顺序：

```
Q1. 用户要的动作，本域工具做得到吗？  → 做不到 → unknown（不管语义多接近）
Q2. 做得到 → 是"查信息"还是"执行动作"？→ 分别落到查询类/执行类工具
```

各域的「查信息 vs 执行动作」落点：

| 域 | 查信息 | 执行动作 |
|---|---|---|
| 出行 | `plan_route`（距离/耗时/路况） | `navigation`（发起导航） |
| 地点 | `poi_detail`（评分/营业时间/**电话号码**） | 拨号/订座 → **unknown** |
| 音乐 | `music_detail` / `web_search` | `play_music`；播放器控制 → **unknown** |
| 新闻 | `news_detail`（朗读摘要） | `open_news`（**跳转打开**） |
| 影院 | `movie_detail` / `web_search` | 购票/在线看 → **unknown** |

## 跨域通用铁律（4 条）

### 铁律 1：`unknown` = 本域工具确实做不到的动作

**不是**"我不确定"的出口。三种情形：

| 情形 | 说明 | 例 |
|---|---|---|
| **A. 能力缺失** | 该动作车机没有对应工具 | 交停车费 / 订座 / 收藏店铺 / 查违章 / 外呼电话 |
| **B. 跨域越界** | 动作属别的域，本域不得代劳 | 地点域说"播放新闻" / 音乐域说"开车窗" |
| **C. 前置缺失** | 工具存在但依赖的上文列表不存在 | 上文无列表却说"第2个"（94.7% unknown） |

**全域 unknown 通用清单**（任何域出现都是 unknown）：

| 类别 | 关键词 | 实证 |
|---|---|---|
| 车控/车机系统 | 空调 / 车窗 / 天窗 / 座椅通风 / 后视镜加热 / 灯光 / 音量 / 投屏 | 各域合计 200+ 条 100% |
| 日程/提醒/备忘 | 提醒我 / 新增行程 / 闹钟 / 记一下 | 全域 |
| 通讯外呼 | 打电话给X / 拨通妈妈电话 / 发微信给小王 | 全域 |
| AI 自身身份 | 你叫什么 / 怎么称呼你 / 陪我聊聊天 | 9/9 = 100% |
| 内容创作 | 赋诗一首 / 写篇文章 / 写个爬虫 / 讲个笑话 | 全域 |
| 纯寒暄 | 你好 / 嗨 / 喂 / 在吗 / 谢谢 | 全域 |
| 孤立确认/否定词 | 嗯 / 对 / 好的 / 算了 / 取消（**且上文无待确认动作**） | 全域 |

⚠️ **孤立确认词有例外**：若上一轮 assistant 在提问或给了待选列表，应**继承上文意图**填对应工具。
例：上文列了 3 家火锅店，用户说"对的" → `search_place|早茶店|<地址>`（继承检索意图），不是 unknown。

**反例（不该 unknown）**：问已知作品信息 → `web_search`；问天气 → `weather`；上文有列表说"第2个" → `*_detail`。

### 铁律 2：序号型指令必须先看"上文有无本域列表"

这是**两级决策树**，实测命中率 99%+（578 条样本）：

```
用户说「第N个 / 第N首 / 最后一个」
├── 上文有本域编号列表（"1. xxx" / "为你找到3个"）
│   ├── 含播放/动作词（放/播/听/来/去/导航）→ play_music / navigation (248/251)
│   └── 含询问词（怎么样/介绍/谁/背景/详情/几点/多少）→ music_detail / poi_detail / movie_detail (218/219)
└── 上文无本域列表 → unknown (125/132 = 94.7%)
```

**同理 `load_more`**（441 条实证）：
- 上文**有**列表 + 「还有吗/换一批/下一页/别的」→ `load_more`（88.9%）
- 上文**无**列表 → `unknown`（41.1%）或该域主搜索工具

### 铁律 3：自由文本参数是"给下游用的检索词"，不是原话转录

必须做四件事：

| 处理 | 例 |
|---|---|
| **ASR 噪声归一** | `chongwud` → `充电站`；`周围推进` → 品类词 |
| **剥动词前缀** | `找一下林宥嘉的歌曲` → `林宥嘉的歌曲`（找/搜类 100% 剥前缀） |
| **补指代** | `按照这个路线帮我规划自驾` → `武汉三日赏樱自驾路线规划`（从上文提取城市/天数/主题） |
| **补缺失实体** | `搜一下光年之外` → `邓紫棋的光年之外`（补歌手名） |

`music_search.query` 实证：**67.1% 是提炼改写，仅 32.9% 原话复刻**。
`travel_plan.query` 实证：含指代词（这个/那个/按照/上面/刚才/这条）的 **4/4 全部做了总结**，长度应落在 **9-14 字**（占 66.4%）。

### 铁律 4：只改 gt，**绝不改 user 输入**

改 user 等于伪造线上流量分布。训练数据的价值就是「真实口语输入 → 规范结构化输出」这个映射。

## 高频混淆点速查

### ⚠️ 「人物问答」三分（最反直觉，务必记住）

| 问什么 | 判定 | 实证 |
|---|---|---|
| 音乐人的**作品/获奖/春晚/榜单** | `web_search` | 代表作 93%、春晚获奖 96% |
| 影人的**籍贯/作品评价/剧情** | `web_search` | 哪里人 100%、为什么火 100% |
| 任何人的**年龄** | **`unknown`** | 歌手多大 **23/23 = 100%** |
| 任何人的**"最新作品"** | **`unknown`** | 最新作品 **6/6 = 100%** |

`web_search` 的域内定义限于「作品/内容相关知识」；个人生平（年龄）与需实时检索的"最新动态"在能力边界外。

### ⚠️ 新闻域：`news_detail` vs `open_news`

| 工具 | 职能 | 动词信号 | 命中率 |
|---|---|---|---|
| `news_detail` | **朗读/摘要**，留在对话里 | 详情 / 详细 / 展开 / 讲了什么 / 第N条内容 | 详情类 **202/206 = 98%** |
| `open_news` | **跳转打开**详情页 | **点开 / 进入 / 打开** | 点开 **127/127 = 100%**<br>进入 **66/66 = 100%** |

**口诀：点开/进入 → open_news；详情/讲了什么 → news_detail。**

### 出行域：navigation vs plan_route（最大混淆）

| 触发词 | 判定 | 命中率 |
|---|---|---|
| 怎么走 / 多远 / 几公里 / 多久 | **plan_route** | 521/523 = 99.6% |
| 地铁 / 公交 / 骑行 / 步行 / 打车 | **plan_route**（+ travel_mode） | 249/265 = 94.0% |
| "路线"（名词） | **plan_route** | 313/353 = 88.7% |
| 导航 / 去X / 出发 / 带我去 | **navigation** | 947/1219 = 77.7% |
| X**路上**找Y / 沿途 / 顺路 | **search_along_route** | — |
| 行程 / 攻略 / 几日游 / 周边玩 | **travel_plan** | — |

一句话：**要"执行导航"→navigation；要"看信息（距离/耗时/路线对比）"→plan_route。**

### 音乐域：播放器控制全归 unknown（易漏）

音乐域**只管搜歌/播歌/歌曲知识**，播放器操作一律 `unknown`：

| 用户说 | 判定 | 实证 |
|---|---|---|
| 把歌停了 / 暂停 / 关掉它 | `unknown` | 33/33 = 100% |
| 把声音调大一点 | `unknown` | 26/26 = 100% |
| 切下一首 / 换一首 | `unknown` | 35/45 |
| 我想看歌词 / 显示歌词 | `unknown` | 81/119（用歌词**搜歌**则走 music_search） |
| 下载这首歌 / 收藏这首 | `unknown` | 37/38 |
| 我现在在听的是什么歌 | `unknown` | 8/8 = 100% |

### 地点域：标准属性 vs 非标属性

| 用户问 | 判定 |
|---|---|
| 评分 / 人均 / 营业时间 / **电话号码** / 地址 / 有无停车场 / 特色菜 | `poi_detail` |
| WiFi 密码 / 排队情况 / 这条路叫什么 | **`unknown`**（WiFi 29/47、道路名 19/19） |
| 收藏 / 分享 / 写评价 | **`unknown`**（收藏 36/36、分享 17/17） |

### 影院域：unknown 的六类（本域最大标签，30.1%）

| 类别 | 例 | 实证 |
|---|---|---|
| 开放式推荐 | 推荐一部热血动漫 / 有没有好看的纪录片 | 推荐类 81 条中 web_search=**0** |
| 场次/票价/购票 | 帮我查一下明天场次 / 订张电影票 | 场次 15/16 |
| **在线观看** | 在哪里能看甄嬛传 / 狂飙在线观看 | **20/20 = 100%** |
| **票房数据** | 这部电影票房多少 | **21/21 = 100%** |
| **影院位置** | 哪个影院离我最近 | **7/7 = 100%** |
| 幕后花絮 | 第6部的幕后花絮讲讲 | — |

### 出行域：车务查询 & 记忆槽位（易漏）

| 用户说 | 判定 | 实证 |
|---|---|---|
| 我的车今天限行吗 / 查违章记录 | `unknown` | 78/79 |
| 高速过路费多少钱 | `unknown` | 24/24 = 100% |
| 附近有没有测速摄像头 | `unknown` | 24/24 = 100% |
| 帮我查航班晚点了没 | `unknown` | 15/15 = 100% |
| **我家地址是什么**（查槽位） | **`unknown`** | **68/68 = 100%** |
| **导航回家**（用槽位） | `navigation` | — |

**槽位「用」与「查」的分界**：拿槽位当目的地 → navigation；反问槽位内容 → unknown（无此工具）。

### 音乐域：music_search vs play_music vs music_detail vs web_search

```
有明确歌名/歌手 + 要听      → music_search（query=提炼词, need_play=true）
指定列表序号 + 动作         → play_music
问某首歌"怎么样/创作背景/谁写的" → music_detail
问歌手"有哪些代表作/上过春晚/前奏用什么音色" → web_search
「还有吗/换一批」+ 上文有列表 → load_more
```

`XX有哪些代表作` → **web_search 39/39 = 100%**
`XX有哪些歌` → web_search 11/14；例外 3 条都提炼成 `X的歌曲` 走 music_search

### 影院电影域：web_search 的边界（易错）

`web_search` = **对已知作品/艺人的具体信息问答**，233 条全是这形态：
`《狂飙》为什么这么火` / `雷佳音是哪里人` / `《进击的巨人》更新到多少集`

**不覆盖**：
- 开放式推荐（81 条推荐类里 web_search = **0**）→ unknown 42 / movie_list 24 / load_more 15
- 场次/票价/购票（16 条里 **unknown 15**）
- 「查一下/帮我查一下」开头（4/4 全部 unknown）

### 信息查询域：时间类要分开看（**曾在此栽过**）

| query 模式 | 命中 | 标注 |
|---|---|---|
| 「现在几点」 | 33 | **unknown 100%** |
| 「今天星期几/周几」 | 19 | **web_search 18 / unknown 1** |
| 「今天几号/多少号」 | 1 | **web_search** |

⚠️ 千万别用 `(星期几|几号|几点)` 混统——33 条「几点」会把结果压成假的 unknown 主流。

### 地点域：search_place 参数序（易错）

「搜索**纯地点名**」110 条实证：**search_query = 地点名 101 条，search_query = `-` 为 0 条**

```
✅ 搜索深圳湾公园        → search_place|深圳湾公园|-
❌ 搜索深圳湾公园        → search_place|-|深圳湾公园      ← 参数颠倒
✅ 搜索腾讯大厦附近的餐厅  → search_place|餐厅|腾讯大厦      ← 有"附近的X"才拆
```

### 地点域：「打电话」≠ call_telephone（易错）

201 条含「打电话/电话是多少/拨」的实证：**poi_detail 117 (58.2%) / unknown 77 (38.3%) / call_telephone 仅 6 (3.0%)**

```
第一个电话是多少 → poi_detail|1|-     ← 问号码 = 查详情
打电话给这家店   → unknown|-          ← 要执行外呼，车机做不到
打这个电话 028-85551234 → call_telephone|028-85551234|-   ← 号码已给全才用
```

## 参数规则（参数位不可随意留 `-`）

各工具的 arity 是唯一的，参数取值受严格约束。完整表见 `references/domain_rules.md`，高频几个：

| 工具 | arity | 关键约束 |
|---|---|---|
| `weather` | 2 | **address 只到市/区级**（522 条含大厦/园区的为 **0**，长度 P50=2 P90=6）；`weather_type`：现在/今天→now，明天/未来N天/一周→future，未来N小时/逐小时/几点→hours |
| `music_search` | 3 | `need_play`：播放/来点/我想听→true；找/搜/推荐→false。`random_search`：**仅当 query 完全无指向（query='-'）才 true**，风格词（轻松/安静）也算有指向→false |
| `plan_route` | 3 | `travel_mode` 枚举 driving/walking/bicycling/ebicycling/transit，默认 driving |
| `movie_list` | 2 | `kind` 枚举 hot/coming |
| `news_search` | 3 | **仅按分类或地区浏览时 query 留 `-`**（439+168=607/1147）；有具体实体则填提炼后的实体；`category` 必填（33 种枚举，无法提取填 `-`）；`region` 省级/直辖市 |
| `news_briefing` | 1 | `when` 枚举 morning/night/auto |
| `set`（speech） | 6 | lang/emo/sty/role/speed/volume 六位固定顺序，只填变化的那几位，其余 `-` |
| `unknown` | 1 | 恒为 `unknown|-` |

## 质量门禁（产出前必查）

```bash
python3 ~/.workbuddy/skills/wecar-fc-tool-labeler/scripts/audit_labels.py <你的jsonl>
```

检查项：
1. **格式层**：role 序列 / assistant 非空 / 无前后空白 / 无换行 / 无 `<think>` / 分隔符无空格
2. **合法性层**：工具名必须在该条 system 声明的工具清单内（正则 `^([a-z_]+)（` 提取，**不要用另一份硬编码白名单**）
3. **arity 层**：参数个数须等于训练集该工具的标准 arity
4. **枚举层**：枚举位取值须在训练集已有集合内
5. **一致性层**：同一 query 在同批数据内不得给出两种标注（曾出现「今天星期几」4 条 unknown + 1 条 web_search）
6. **查重**：与主训练集做 system+user 签名比对

## 已知踩坑（务必避开）

1. **白名单与 system prompt 脱节**：曾有 pipeline 用独立硬编码白名单校验，导致 `web_search` 明明在 system 声明内却被判"不在白名单"，gt 被强改成 unknown（波及 5 条）。**校验必须从 system prompt 现场解析工具名。**
2. **教师模型思维链未剥离**：`gold_valid=False: 工具名不在本域白名单: 我们被要求根据对话上下文选择工具。用户说…` —— 解析器把整段思维链当工具名了。修法：`raw.split("</think>")[-1].strip().split("\n")[-1].strip()`
3. **校验失败却静默采纳**：21 条 `gold_valid=False` 全被写成 gt。校验失败应进人工队列。
4. **空 assistant**：`assistant.content == ""` 会产生全 `-100` label，白跑 step。必须给显式占位或剔除。
5. **全角/半角括号**：训练集用**半角** `长安亭院火锅(深圳总店)`，别用全角。
6. **列表检测要覆盖两种形态**：换行式 `\n1. 起风了 - 买辣椒也用券`，**行内式** `1.恶意 2.戏台 3.疯狂动物城3`（影院域主流，258/288 是这形态）。只写换行正则会漏检 89.6%，导致大量 detail 类被误降级成 unknown。
7. **日志审计结论不等于训练答案**：原日志可以判“正确”或“可接受”，但训练时仍可能需要更稳定的 `final_train_answer`；不要把“原答案没错”直接等价成“原答案可直接入训练”。
8. **`需澄清 / schema 无法表达` 的 case 不要硬塞进训练集**：这类 case 可以留在对比文档里，但 `reviewed.csv` 必须标 `use_for_training=no`，否则会把不完整 supervision 写进训练数据。

## 训练集自身已知噪声（标注时别被带偏）

| 位置 | 问题 |
|---|---|
| 信息查询域 | 2 条 `weather_type='no w'`（now 中间多空格） |
| 信息查询域 | 「今天星期几」既有 web_search 也有 unknown（3 条冲突） |
| 地点域 | 「给第一家打个电话」既有 unknown 也有 call_telephone |
| 音乐域 | 「还有别的歌吗」既有 load_more 也有 unknown |
| Query 改写域 | 曾有 17 条 `assistant.content==""`（v3 已剔除） |

`label.py` 遇到同句冲突会主动告警，不会静默取多数。

## 产物落地

标注完成后转训练格式：

```bash
python3 ~/.workbuddy/skills/wecar-fc-tool-labeler/scripts/to_trainable.py <src.jsonl> -o <out>.jsonl
```

自动剥 `_meta`、剔除空 assistant、生成 dataset_info 片段、算出 `cutoff_len` 建议值。

**dataset_info 配置**（`formatting: sharegpt` 只读 `messages`，多余顶层键静默忽略）：

```json
{"<name>": {"file_name": "<绝对路径>", "formatting": "sharegpt",
  "columns": {"messages": "messages"},
  "tags": {"role_tag":"role","content_tag":"content","user_tag":"user",
           "assistant_tag":"assistant","system_tag":"system"}}}
```

⚠️ **`cutoff_len` 必须 ≥ 4096**（训练集 max 3923 字符 ≈ 2451 token；沿用 512 会从 P90 就开始截断，砍掉 assistant 目标）。
