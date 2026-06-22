# maoyan & tc_travel 酒店 - 首轮 query 槽位提取案例

> 范围：用户**首轮 query**（session 内 LLM 尚未调任何业务工具前的第一句话），
> 经 `parse_movie_ticket_intent`（maoyan）/ `parse_hotel_intent`（tc_travel 酒店）解析后的槽位提取结果。
>
> 用途：review prompt 规则 / 训练槽位提取 LLM / 写新场景 prompt 的对照参考。
>
> 约定：所有"日期/时间"均按 prompt 要求转换后填入（maoyan=X月X日 / 原话相对时间；hotel=ISO YYYY-MM-DD）。

---

## 1. maoyan 电影票 — `parse_movie_ticket_intent`

**槽位定义（6 个）**：
| 槽位 | 含义 | 取值规则 |
|---|---|---|
| `movie_name` | 电影标题 | 如"哪吒3""流浪地球"，**片名里的数字不是 quantity**（"复仇者联盟4"的 4 不是 4 张票）|
| `person_name` | 演员名/导演名 | 如"刘德华""张艺谋" |
| `cinema_name` | 影院名 | 用户说"序号"也填具体名（cinema_name 不收序号）|
| `date` | 具体日期 | "X月X日"（如"6月12日"），"明天"先**查日期速查表**转 |
| `time` | 时间原话 | "19:30"/"下午3点"，不带时段词且 X≤12 时**双向尝试** 6:xx/18:xx |
| `quantity` | 购票张数 | "N张/买N张/N个人/N位"才提取，未提=None；**片名中的数字不算** |

---

### 0 槽位（仅意图，无具体信息）— 反问"您想看哪部电影？"

| # | 首轮 query | movie_name | person_name | cinema_name | date | time | quantity |
|---|---|---|---|---|---|---|---|
| 1 | 我想看电影 | | | | | | |
| 2 | 帮我买电影票 | | | | | | |

---

### 1 槽位（每种槽位各 2 个例子）

| # | 槽位类型 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `movie_name` | 我想看哪吒3 | `movie_name="哪吒3"` |
| 2 | `movie_name` | 给我看复仇者联盟4 | `movie_name="复仇者联盟4"` |
| 3 | `person_name` | 看刘德华主演的电影 | `person_name="刘德华"` |
| 4 | `person_name` | 找张艺谋导演的 | `person_name="张艺谋"` |
| 5 | `cinema_name` | 去中影影城看 | `cinema_name="中影影城"` |
| 6 | `cinema_name` | 中影影城买张票 | `cinema_name="中影影城"` |
| 7 | `date` | 明天看电影 | `date="6月12日"`（查表）|
| 8 | `date` | 周五看场电影 | `date="6月13日"`（查表）|
| 9 | `time` | 晚上 8 点看电影 | `time="晚上8点"` |
| 10 | `time` | 下午 3 点看场 | `time="下午3点"` |
| 11 | `quantity` | 买 2 张电影票 | `quantity=2` |
| 12 | `quantity` | 我要 3 张 | `quantity=3` |

> 1 槽位必走**反问**补足剩余 5 个槽位，按 stage_tools_config 顺序选场（先 movie_name → date → cinema_name → time → quantity → person_name）。

---

### 2 槽位

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `movie_name+date` | 明天看哪吒3 | `movie_name="哪吒3"`, `date="6月12日"` |
| 2 | `movie_name+date` | 周五给我看流浪地球 | `movie_name="流浪地球"`, `date="6月13日"` |
| 3 | `movie_name+quantity` | 帮我买 2 张哪吒3 的票 | `movie_name="哪吒3"`, `quantity=2` |
| 4 | `movie_name+quantity` | 我要 3 张复仇者联盟4 | `movie_name="复仇者联盟4"`, `quantity=3` |
| 5 | `movie_name+time` | 哪吒3 晚上 8 点的 | `movie_name="哪吒3"`, `time="晚上8点"` |
| 6 | `movie_name+time` | 流浪地球下午 3 点 | `movie_name="流浪地球"`, `time="下午3点"` |
| 7 | `date+time` | 明天晚上 8 点看电影 | `date="6月12日"`, `time="晚上8点"` |
| 8 | `date+time` | 周五下午 3 点看场 | `date="6月13日"`, `time="下午3点"` |
| 9 | `date+quantity` | 明天 2 张 | `date="6月12日"`, `quantity=2` |
| 10 | `date+quantity` | 周五要 3 张 | `date="6月13日"`, `quantity=3` |
| 11 | `cinema_name+quantity` | 中影影城 2 张 | `cinema_name="中影影城"`, `quantity=2` |
| 12 | `cinema_name+quantity` | 博纳院线 3 张票 | `cinema_name="博纳院线"`, `quantity=3` |
| 13 | `cinema_name+date` | 明天下午去中影影城 | `cinema_name="中影影城"`, `date="6月12日"` |
| 14 | `cinema_name+date` | 周六去博纳院线看 | `cinema_name="博纳院线"`, `date="6月14日"` |
| 15 | `time+quantity` | 晚上 8 点 2 张 | `time="晚上8点"`, `quantity=2` |
| 16 | `time+quantity` | 下午 3 点 3 张票 | `time="下午3点"`, `quantity=3` |

> **易错**：2 槽位时"刘德华主演的电影"算 `person_name` 单独 1 槽位（因电影名缺失需反问），不算 `person_name+movie_name` 2 槽位；用户补"哪吒3"后才升 2 槽位。

---

### 3 槽位

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `movie_name+date+time` | 明天晚上 8 点看哪吒3 | `movie_name`, `date`, `time` |
| 2 | `movie_name+date+time` | 周五下午 3 点流浪地球 | `movie_name`, `date`, `time` |
| 3 | `movie_name+date+quantity` | 明天买 2 张哪吒3 | `movie_name`, `date`, `quantity=2` |
| 4 | `movie_name+date+quantity` | 周五我要 3 张复仇者联盟4 | `movie_name`, `date`, `quantity=3` |
| 5 | `movie_name+cinema_name+date` | 明天中影影城哪吒3 | `movie_name`, `cinema_name`, `date` |
| 6 | `movie_name+cinema_name+date` | 周五博纳院线看流浪地球 | `movie_name`, `cinema_name`, `date` |
| 7 | `movie_name+time+quantity` | 晚上 8 点 2 张哪吒3 | `movie_name`, `time`, `quantity=2` |
| 8 | `movie_name+time+quantity` | 下午 3 点 3 张复仇者联盟4 | `movie_name`, `time`, `quantity=3` |
| 9 | `movie_name+cinema_name+time` | 中影影城晚上 8 点哪吒3 | `movie_name`, `cinema_name`, `time` |
| 10 | `movie_name+cinema_name+time` | 博纳院线下午 3 点流浪地球 | `movie_name`, `cinema_name`, `time` |
| 11 | `person_name+date+quantity` | 帮我买 2 张刘德华主演的电影明天看 | `person_name`, `date`, `quantity=2` |
| 12 | `person_name+date+quantity` | 周五要 3 张张艺谋导演的 | `person_name`, `date`, `quantity=3` |
| 13 | `date+time+quantity` | 明天晚上 8 点 2 张 | `date`, `time`, `quantity=2` |
| 14 | `date+time+quantity` | 周五下午 3 点 3 张 | `date`, `time`, `quantity=3` |
| 15 | `cinema_name+date+time` | 明天下午 3 点去中影影城 | `cinema_name`, `date`, `time` |
| 16 | `cinema_name+date+time` | 周五晚上 8 点博纳院线 | `cinema_name`, `date`, `time` |

---

### 4 槽位

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `movie_name+cinema_name+date+time` | 明天晚上 8 点中影影城哪吒3 | 4 槽位（缺 quantity, person_name）|
| 2 | `movie_name+cinema_name+date+time` | 周五下午 3 点博纳院线流浪地球 | 4 槽位 |
| 3 | `movie_name+date+time+quantity` | 明天晚上 8 点 2 张哪吒3 | 4 槽位（缺 cinema_name, person_name）|
| 4 | `movie_name+date+time+quantity` | 周五下午 3 点 3 张复仇者联盟4 | 4 槽位 |
| 5 | `movie_name+cinema_name+date+quantity` | 明天中影影城 2 张哪吒3 | 4 槽位（缺 time, person_name）|
| 6 | `movie_name+cinema_name+date+quantity` | 周五博纳院线 3 张流浪地球 | 4 槽位 |
| 7 | `movie_name+cinema_name+time+quantity` | 中影影城晚上 8 点 2 张哪吒3 | 4 槽位（缺 date, person_name）|
| 8 | `movie_name+cinema_name+time+quantity` | 博纳院线下午 3 点 3 张复仇者联盟4 | 4 槽位 |
| 9 | `cinema_name+date+time+quantity` | 明天下午 3 点中影影城 2 张 | 4 槽位（缺 movie_name, person_name）|
| 10 | `cinema_name+date+time+quantity` | 周五晚上 8 点博纳院线 3 张 | 4 槽位 |

> 4 槽位时常缺 `person_name`（用户没提演员名）和 `quantity`（用户没提张数）；按 stage_tools_config 顺序反问补足。

---

### 5 槽位

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `movie_name+person_name+cinema_name+date+time` | 明天晚上 8 点中影影城刘德华主演哪吒3 | 5 槽位（缺 quantity）|
| 2 | `movie_name+person_name+cinema_name+date+time` | 周五下午 3 点博纳院线张艺谋导演流浪地球 | 5 槽位 |
| 3 | `movie_name+person_name+date+time+quantity` | 明天晚上 8 点刘德华主演 2 张哪吒3 | 5 槽位（缺 cinema_name）|
| 4 | `movie_name+person_name+date+time+quantity` | 周五下午 3 点 3 张张艺谋导演哪吒3 | 5 槽位 |
| 5 | `movie_name+cinema_name+date+time+quantity` | 明天晚上 8 点中影影城 2 张哪吒3 | 5 槽位（缺 person_name）|
| 6 | `movie_name+cinema_name+date+time+quantity` | 周五下午 3 点博纳院线 3 张流浪地球 | 5 槽位 |
| 7 | `movie_name+person_name+cinema_name+date+quantity` | 明天中影影城刘德华主演 2 张哪吒3 | 5 槽位（缺 time）|
| 8 | `movie_name+person_name+cinema_name+date+quantity` | 周五博纳院线 3 张张艺谋导演流浪地球 | 5 槽位 |
| 9 | `movie_name+person_name+cinema_name+time+quantity` | 中影影城晚上 8 点刘德华主演 2 张哪吒3 | 5 槽位（缺 date）|
| 10 | `movie_name+person_name+cinema_name+time+quantity` | 博纳院线下午 3 点 3 张张艺谋导演哪吒3 | 5 槽位 |

> 5 槽位最常见缺 `time`（用户常说"晚上"而不说具体到分）→ 反问"晚上几点？"；或缺 `person_name`（用户没特别提演员）。

---

### 6 槽位（全填，最理想首轮 query）

| # | 首轮 query | 槽位值 |
|---|---|---|
| 1 | 明天晚上 8 点中影影城 2 张刘德华主演哪吒3 | `movie_name="哪吒3"`, `person_name="刘德华"`, `cinema_name="中影影城"`, `date="6月12日"`, `time="晚上8点"`, `quantity=2` |
| 2 | 帮我买 2 张今晚 7 点半中影影城刘德华主演哪吒3 | `movie_name="哪吒3"`, `person_name="刘德华"`, `cinema_name="中影影城"`, `date="6月11日"`, `time="19:30"`, `quantity=2` |

---

## 2. maoyan 演唱会 — `parse_concert_intent`

**槽位定义（6 个）**：

| 槽位 | 含义 | 取值规则 |
|---|---|---|
| `show_name` | 演唱会名 / 歌手名 | 如「周杰伦」「五月天演唱会」；**没有 time 槽位**（场次由 date 决定，不需精确时分） |
| `city` | 城市偏好 | 如「北京」「上海」；**没有 cinema 槽位**（演唱会场馆由演唱会本身决定） |
| `date` | 演出日期 | "X月X日"（如"6月12日"），"下周末"先**查日期速查表**转 |
| `ticket_count` | 购票张数 | "N张/买N张/N个人/N位"才提取，未提=None；**严禁默认传 1** |
| `ticket_grade_preference` | 票档偏好 | "VIP/内场/看台/999元"；**提到价格必须包含价格**（如「999元」而非「一千左右」） |
| `viewer_names` | 观演人名单 | 数组；"给张三李四买"→`["张三","李四"]`；同音字按读音匹配 |

> **vs 电影 4 点关键差异**：
> 1. **无 `time` 槽位**——演唱会场次日期（+城市/场馆）通常就唯一确定，不需精确时分
> 2. **无 `cinema_name`，有 `city`**——演唱会按城市巡演，城市是核心决策点
> 3. **有 `ticket_grade_preference`**——票档是演唱会核心决策点（VIP/内场/看台/具体价位）
> 4. **`viewer_names` 与 `ticket_count` 关系**：**以观演人数为准**——若 `len(viewer_names)>=1`，覆盖 `ticket_count=len(viewer_names)`（LLM 乱填数会被覆盖）

---

### 0 槽位（仅意图）— 反问"想看谁的演唱会/在哪个城市？"

| # | 首轮 query | 6 个槽位全空 |
|---|---|---|
| 1 | 我想看演唱会 | ✓ |
| 2 | 帮我订演唱会的票 | ✓ |

---

### 1 槽位（每种槽位各 2 个例子）

| # | 槽位类型 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | show_name | 我想买周杰伦演唱会门票 | `show_name="周杰伦"` |
| 2 | show_name | 帮我搜五月天演唱会 | `show_name="五月天"` |
| 3 | city | 北京最近有什么演唱会 | `city="北京"` |
| 4 | city | 上海的演唱会 | `city="上海"` |
| 5 | date | 6 月 12 号演唱会有吗 | `date="6月12日"` |
| 6 | date | 明天晚上的演唱会 | `date=查表得具体日期`（无 time 槽位） |
| 7 | ticket_count | 买两张周杰伦的票 | `ticket_count=2` |
| 8 | ticket_count | 一个人想去看五月天 | `ticket_count=1` |
| 9 | ticket_grade_preference | 想买 VIP 票 | `ticket_grade_preference="VIP"` |
| 10 | ticket_grade_preference | 999 元的内场票 | `ticket_grade_preference="内场999元"` |
| 11 | viewer_names | 给张三买一张演唱会 | `viewer_names=["张三"]` |
| 12 | viewer_names | 给李四王五买周杰伦的票 | `viewer_names=["李四","王五"]` |

---

### 2 槽位

| # | 首轮 query | 槽位值 |
|---|---|---|
| 1 | 我想看周杰伦演唱会 6 月 12 号 | `show_name="周杰伦"`, `date="6月12日"` |
| 2 | 买两张五月天的票 | `show_name="五月天"`, `ticket_count=2` |
| 3 | 北京 6 月 1 号的演唱会 | `city="北京"`, `date="6月1日"` |
| 4 | 周杰伦上海演唱会 | `show_name="周杰伦"`, `city="上海"` |
| 5 | VIP 票两张 | `ticket_count=2`, `ticket_grade_preference="VIP"` |
| 6 | 999 元的周杰伦 | `show_name="周杰伦"`, `ticket_grade_preference="999元"` |
| 7 | 明天上海有什么演唱会 | `city="上海"`, `date=查表得具体日期` |
| 8 | 给张三买一张 VIP | `viewer_names=["张三"]`, `ticket_grade_preference="VIP"` |
| 9 | 北京 VIP 票 2 张 | `city="北京"`, `ticket_count=2`, `ticket_grade_preference="VIP"` |
| 10 | 帮我买 2 张周杰伦的 999 元票 | `show_name="周杰伦"`, `ticket_count=2`, `ticket_grade_preference="999元"` |
| 11 | 给张三李四买两张演唱会 | `viewer_names=["张三","李四"]`, `ticket_count=2` |
| 12 | 周杰伦上海 6 月 12 号 | `show_name="周杰伦"`, `city="上海"`, `date="6月12日"` |
| 13 | 6 月 12 号北京 VIP | `city="北京"`, `date="6月12日"`, `ticket_grade_preference="VIP"` |
| 14 | 明天周杰伦 VIP 票 | `show_name="周杰伦"`, `date=查表`, `ticket_grade_preference="VIP"` |
| 15 | 999 元两张北京 | `city="北京"`, `ticket_count=2`, `ticket_grade_preference="999元"` |
| 16 | 给张三买周杰伦 6 月 12 号 | `show_name="周杰伦"`, `viewer_names=["张三"]`, `date="6月12日"` |

---

### 3 槽位

| # | 首轮 query | 槽位值 |
|---|---|---|
| 1 | 我想买周杰伦上海 6 月 12 号的票 | `show_name="周杰伦"`, `city="上海"`, `date="6月12日"` |
| 2 | 6 月 12 号北京 VIP 票 1 张 | `city="北京"`, `date="6月12日"`, `ticket_grade_preference="VIP"`, `ticket_count=1` |
| 3 | 周杰伦上海 999 元 1 张 | `show_name="周杰伦"`, `city="上海"`, `ticket_grade_preference="999元"`, `ticket_count=1` |
| 4 | 给张三买周杰伦 6 月 12 号 VIP | `show_name="周杰伦"`, `viewer_names=["张三"]`, `date="6月12日"`, `ticket_grade_preference="VIP"` |
| 5 | 北京 6 月 12 号 VIP 两张 | `city="北京"`, `date="6月12日"`, `ticket_count=2`, `ticket_grade_preference="VIP"` |
| 6 | 明天上海 VIP 一张 | `city="上海"`, `date=查表`, `ticket_count=1`, `ticket_grade_preference="VIP"` |
| 7 | 给张三买周杰伦上海 6 月 12 号 | `show_name="周杰伦"`, `city="上海"`, `viewer_names=["张三"]`, `date="6月12日"` |
| 8 | 周杰伦北京 999 元两张给张三 | `show_name="周杰伦"`, `city="北京"`, `ticket_grade_preference="999元"`, `ticket_count=2`, `viewer_names=["张三"]` |
| 9 | 6 月 12 号北京 999 元的两张 | `city="北京"`, `date="6月12日"`, `ticket_grade_preference="999元"`, `ticket_count=2` |
| 10 | 给张三李四买周杰伦上海 6 月 12 号 | `show_name="周杰伦"`, `city="上海"`, `viewer_names=["张三","李四"]`, `date="6月12日"` |
| 11 | 明天上海两张 VIP | `city="上海"`, `date=查表`, `ticket_count=2`, `ticket_grade_preference="VIP"` |
| 12 | 999 元的周杰伦北京 6 月 12 号 | `show_name="周杰伦"`, `city="北京"`, `ticket_grade_preference="999元"`, `date="6月12日"` |

---

### 4 槽位

| # | 首轮 query | 槽位值 |
|---|---|---|
| 1 | 买周杰伦上海 6 月 12 号 VIP 票 1 张 | `show_name="周杰伦"`, `city="上海"`, `date="6月12日"`, `ticket_grade_preference="VIP"`, `ticket_count=1` |
| 2 | 明天北京 VIP 两张给张三 | `city="北京"`, `date=查表`, `ticket_count=2`, `ticket_grade_preference="VIP"`, `viewer_names=["张三"]` |
| 3 | 周杰伦北京 6 月 12 号 999 元 2 张 | `show_name="周杰伦"`, `city="北京"`, `date="6月12日"`, `ticket_grade_preference="999元"`, `ticket_count=2` |
| 4 | 给张三买周杰伦上海 6 月 12 号 VIP | `show_name="周杰伦"`, `city="上海"`, `viewer_names=["张三"]`, `date="6月12日"`, `ticket_grade_preference="VIP"` |
| 5 | 6 月 12 号北京 999 元两张给张三 | `city="北京"`, `date="6月12日"`, `ticket_grade_preference="999元"`, `ticket_count=2`, `viewer_names=["张三"]` |
| 6 | 明天上海 VIP 票 1 张给张三 | `city="上海"`, `date=查表`, `ticket_grade_preference="VIP"`, `ticket_count=1`, `viewer_names=["张三"]` |
| 7 | 周杰伦上海 6 月 12 号两张 VIP 给张三李四 | `show_name="周杰伦"`, `city="上海"`, `date="6月12日"`, `ticket_count=2`, `ticket_grade_preference="VIP"`, `viewer_names=["张三","李四"]` |
| 8 | 给张三买周杰伦北京 6 月 12 号 999 元两张 | `show_name="周杰伦"`, `city="北京"`, `viewer_names=["张三"]`, `date="6月12日"`, `ticket_grade_preference="999元"`, `ticket_count=2` |
| 9 | 北京 6 月 12 号 VIP 票给张三李四 | `city="北京"`, `date="6月12日"`, `ticket_grade_preference="VIP"`, `viewer_names=["张三","李四"]` |
| 10 | 周杰伦上海 6 月 12 号 999 元两张给张三 | `show_name="周杰伦"`, `city="上海"`, `date="6月12日"`, `ticket_grade_preference="999元"`, `ticket_count=2`, `viewer_names=["张三"]` |

---

### 5 槽位

| # | 首轮 query | 槽位值 |
|---|---|---|
| 1 | 买周杰伦上海 6 月 12 号 VIP 票 1 张给张三 | `show_name="周杰伦"`, `city="上海"`, `date="6月12日"`, `ticket_grade_preference="VIP"`, `ticket_count=1`, `viewer_names=["张三"]` |
| 2 | 明天北京 VIP 两张给张三李四 | `city="北京"`, `date=查表`, `ticket_count=2`, `ticket_grade_preference="VIP"`, `viewer_names=["张三","李四"]` |
| 3 | 周杰伦北京 6 月 12 号 999 元两张给张三 | `show_name="周杰伦"`, `city="北京"`, `date="6月12日"`, `ticket_grade_preference="999元"`, `ticket_count=2`, `viewer_names=["张三"]` |
| 4 | 给张三买周杰伦上海 6 月 12 号 VIP 两张 | `show_name="周杰伦"`, `city="上海"`, `viewer_names=["张三"]`, `date="6月12日"`, `ticket_grade_preference="VIP"`, `ticket_count=2` |
| 5 | 明天上海 VIP 票 1 张给张三李四 | `city="上海"`, `date=查表`, `ticket_grade_preference="VIP"`, `ticket_count=1`, `viewer_names=["张三","李四"]` |
| 6 | 周杰伦上海 6 月 12 号两张 999 元给张三李四 | `show_name="周杰伦"`, `city="上海"`, `date="6月12日"`, `ticket_count=2`, `ticket_grade_preference="999元"`, `viewer_names=["张三","李四"]` |
| 7 | 北京 6 月 12 号 999 元两张 VIP 给张三 | `city="北京"`, `date="6月12日"`, `ticket_grade_preference="999元"`, `ticket_count=2`, `viewer_names=["张三"]` |
| 8 | 给张三李四买周杰伦北京 6 月 12 号 VIP 一张 | `show_name="周杰伦"`, `city="北京"`, `viewer_names=["张三","李四"]`, `date="6月12日"`, `ticket_grade_preference="VIP"`, `ticket_count=1` |
| 9 | 明天北京 VIP 一张给张三 | `city="北京"`, `date=查表`, `ticket_grade_preference="VIP"`, `ticket_count=1`, `viewer_names=["张三"]` |
| 10 | 周杰伦北京 6 月 12 号 999 元 VIP 两张给张三 | `show_name="周杰伦"`, `city="北京"`, `date="6月12日"`, `ticket_grade_preference="999元"`, `ticket_count=2`, `viewer_names=["张三"]` |

---

### 6 槽位（全填，最理想首轮 query）

| # | 首轮 query | 槽位值 |
|---|---|---|
| 1 | 给张三买周杰伦上海 6 月 12 号 VIP 票 1 张 | `show_name="周杰伦"`, `city="上海"`, `viewer_names=["张三"]`, `date="6月12日"`, `ticket_grade_preference="VIP"`, `ticket_count=1` |
| 2 | 明天北京 999 元的 VIP 票两张给张三李四 | `city="北京"`, `date=查表`, `ticket_grade_preference="999元"`, `ticket_count=2`, `viewer_names=["张三","李四"]` |
| 3 | 周杰伦上海 6 月 12 号 999 元 VIP 两张给张三李四 | `show_name="周杰伦"`, `city="上海"`, `date="6月12日"`, `ticket_grade_preference="999元"`, `ticket_count=2`, `viewer_names=["张三","李四"]` |
| 4 | 给张三李四买周杰伦北京明天 999 元两张 VIP | `show_name="周杰伦"`, `city="北京"`, `viewer_names=["张三","李四"]`, `date=查表`, `ticket_grade_preference="999元"`, `ticket_count=2` |
| 5 | 北京明天 VIP 票 1 张给张三李四 999 元的 | `city="北京"`, `date=查表`, `ticket_grade_preference="VIP"`, `ticket_count=1`, `viewer_names=["张三","李四"]` |

---

## 3. tc_travel 酒店 — `parse_hotel_intent`

**槽位定义（12 个）**：
| 槽位 | 含义 | 取值规则 |
|---|---|---|
| `destination` | 目的地（城市+区/商圈）| "武汉江汉区"**整串**合并；"武汉亚朵"**拆分**（武汉→destination，亚朵→hotel_name）|
| `hotel_name` | 酒店品牌/名 | 不含城市前缀；含品牌时只填品牌 |
| `is_nearby` | 附近/周边 | 仅"附近/周边/周围"**字面**才 True |
| `auto_select_first` | 最近的 | 仅"最近的/离我最近"**字面**才 True；**与 is_nearby 不等价**|
| `check_in_date` | 入住日期 | ISO `YYYY-MM-DD`；"今晚"**强制**同时填 in/out |
| `check_out_date` | 离店日期 | ISO `YYYY-MM-DD`；"住 X 晚"在 in 基础上 +N 天 |
| `adult_count` | 成人人数 | **仅**"X人/几个大人"字面才提取；"双人床/三人间"**不算人数**|
| `child_count` | 儿童人数 | **仅**"儿童/小孩"字面才提取 |
| `child_ages` | 儿童年龄列表 | JSON 数组字符串；"6 个月/不到 1 岁"统一传 `'小于1岁'`；**严禁编造**|
| `guest_names` | 入住人姓名列表 | 数组；"给张三李四订"→`["张三","李四"]` |
| `room_count` | 房间数 | **仅**"X 间/X 个房间"字面才提取；"X 个人"**不算房间数**|
| `room_type` | 房型偏好 | "大床房/双床房"；**严禁**人数反推房型 |

> **铁律**：所有字段**只能从字面提取**，禁止"X 人 → X 间房"或"X 间房 → X 人"等任何跨字段联想。

---

### 0 槽位（仅意图）— 反问"您想去哪/什么时候入住？"

| # | 首轮 query | 12 个槽位全空 |
|---|---|---|
| 1 | 我想订酒店 | ✓ |
| 2 | 帮我订个酒店 | ✓ |

---

### 1 槽位（每种槽位各 2 个例子）

| # | 槽位类型 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `destination` | 武汉订酒店 | `destination="武汉"` |
| 2 | `destination` | 上海订个酒店 | `destination="上海"` |
| 3 | `hotel_name` | 亚朵酒店 | `hotel_name="亚朵酒店"` |
| 4 | `hotel_name` | 维也纳 | `hotel_name="维也纳"` |
| 5 | `is_nearby` | 附近的酒店 | `is_nearby=True` |
| 6 | `is_nearby` | 周边找家酒店 | `is_nearby=True` |
| 7 | `auto_select_first` | 最近的酒店 | `auto_select_first=True` |
| 8 | `auto_select_first` | 离我最近的那家 | `auto_select_first=True` |
| 9 | `check_in_date` | 明天入住 | `check_in_date=...`（ISO）|
| 10 | `check_in_date` | 周五住 | `check_in_date=...`（查周换 ISO）|
| 11 | `check_out_date` | 后天离店 | `check_out_date=...`（ISO）|
| 12 | `check_out_date` | 周日退房 | `check_out_date=...`（查周换 ISO）|
| 13 | `adult_count` | 2 个人 | `adult_count=2` |
| 14 | `adult_count` | 1 个人 | `adult_count=1` |
| 15 | `child_count` | 1 个小孩 | `child_count=1` |
| 16 | `child_count` | 带 2 个儿童 | `child_count=2` |
| 17 | `guest_names` | 给张三订 | `guest_names=["张三"]` |
| 18 | `guest_names` | 李四订个酒店 | `guest_names=["李四"]` |
| 19 | `room_count` | 订 2 间 | `room_count="2"` |
| 20 | `room_count` | 来 3 间房 | `room_count="3"` |
| 21 | `room_type` | 要大床房 | `room_type="大床房"` |
| 22 | `room_type` | 双床房 | `room_type="双床房"` |

> **不成立**：单独 `child_ages` 不会作为 1 槽位出现（必须随 `child_count` 一起）；"今晚住一晚"是 `check_in_date+check_out_date` 双填，**不是 1 槽位**。

---

### 2 槽位

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `destination+hotel_name` | 武汉亚朵 | `destination="武汉"`, `hotel_name="亚朵"` |
| 2 | `destination+hotel_name` | 上海维也纳 | `destination="上海"`, `hotel_name="维也纳"` |
| 3 | `destination+check_in_date` | 武汉明天入住 | `destination="武汉"`, `check_in_date=...` |
| 4 | `destination+check_in_date` | 上海周五住 | `destination="上海"`, `check_in_date=...` |
| 5 | `destination+check_out_date` | 武汉后天离店 | `destination="武汉"`, `check_out_date=...` |
| 6 | `destination+check_out_date` | 北京周日退房 | `destination="北京"`, `check_out_date=...` |
| 7 | `destination+room_type` | 武汉大床房 | `destination="武汉"`, `room_type="大床房"` |
| 8 | `destination+room_type` | 上海双床房 | `destination="上海"`, `room_type="双床房"` |
| 9 | `destination+adult_count` | 武汉 2 个人 | `destination="武汉"`, `adult_count=2` |
| 10 | `destination+adult_count` | 上海 1 个人 | `destination="上海"`, `adult_count=1` |
| 11 | `destination+child_count` | 武汉 1 个小孩 | `destination="武汉"`, `child_count=1` |
| 12 | `destination+child_count` | 上海带 2 个儿童 | `destination="上海"`, `child_count=2` |
| 13 | `destination+room_count` | 武汉订 2 间 | `destination="武汉"`, `room_count="2"` |
| 14 | `destination+room_count` | 上海来 3 间房 | `destination="上海"`, `room_count="3"` |
| 15 | `destination+is_nearby` | 武汉附近的 | `destination="武汉"`, `is_nearby=True` |
| 16 | `destination+is_nearby` | 上海周边的酒店 | `destination="上海"`, `is_nearby=True` |
| 17 | `destination+auto_select_first` | 武汉最近的 | `destination="武汉"`, `auto_select_first=True` |
| 18 | `destination+auto_select_first` | 上海离我最近的那家 | `destination="上海"`, `auto_select_first=True` |
| 19 | `destination+guest_names` | 武汉给张三订 | `destination="武汉"`, `guest_names=["张三"]` |
| 20 | `destination+guest_names` | 上海给张三李四 | `destination="上海"`, `guest_names=["张三","李四"]` |
| 21 | `check_in_date+check_out_date` | 今晚住一晚 | `check_in_date=...`, `check_out_date=...`**强制双填** |
| 22 | `check_in_date+check_out_date` | 明晚住一晚 | 同上 |
| 23 | `check_in_date+check_out_date` | 住 2 晚 | `check_in_date=...`, `check_out_date=in+2` |
| 24 | `check_in_date+room_type` | 明天大床房 | `check_in_date=...`, `room_type="大床房"` |
| 25 | `check_in_date+room_type` | 周五双床房 | `check_in_date=...`, `room_type="双床房"` |
| 26 | `check_in_date+adult_count` | 明天 2 个人 | `check_in_date=...`, `adult_count=2` |
| 27 | `check_in_date+adult_count` | 周五 1 个人 | `check_in_date=...`, `adult_count=1` |
| 28 | `hotel_name+check_in_date` | 亚朵明天 | `hotel_name="亚朵"`, `check_in_date=...` |
| 29 | `hotel_name+check_in_date` | 维也纳周五住 | `hotel_name="维也纳"`, `check_in_date=...` |
| 30 | `hotel_name+room_type` | 亚朵大床房 | `hotel_name="亚朵"`, `room_type="大床房"` |
| 31 | `hotel_name+room_type` | 维也纳双床房 | `hotel_name="维也纳"`, `room_type="双床房"` |
| 32 | `adult_count+room_count` | 2 个人订 1 间房 | `adult_count=2`, `room_count="1"` |
| 33 | `adult_count+room_count` | 3 个人 1 间房 | `adult_count=3`, `room_count="1"` |
| 34 | `adult_count+room_type` | 2 个人大床房 | `adult_count=2`, `room_type="大床房"` |
| 35 | `adult_count+room_type` | 1 个人双床房 | `adult_count=1`, `room_type="双床房"` |
| 36 | `child_count+child_ages` | 1 个 6 岁小孩 | `child_count=1`, `child_ages=["6"]` |
| 37 | `child_count+child_ages` | 2 个儿童一个 6 岁一个 3 岁 | `child_count=2`, `child_ages=["6","3"]` |
| 38 | `room_count+room_type` | 2 间大床房 | `room_count="2"`, `room_type="大床房"` |
| 39 | `room_count+room_type` | 3 间双床房 | `room_count="3"`, `room_type="双床房"` |
| 40 | `is_nearby+hotel_name` | 附近亚朵 | `is_nearby=True`, `hotel_name="亚朵"` |
| 41 | `is_nearby+hotel_name` | 周边维也纳 | `is_nearby=True`, `hotel_name="维也纳"` |
| 42 | `auto_select_first+hotel_name` | 最近的亚朵 | `auto_select_first=True`, `hotel_name="亚朵"` |
| 43 | `auto_select_first+hotel_name` | 离我最近的维也纳 | `auto_select_first=True`, `hotel_name="维也纳"` |

---

### 3 槽位

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `destination+hotel_name+check_in_date` | 武汉亚朵明天 | 3 槽位 |
| 2 | `destination+hotel_name+check_in_date` | 上海维也纳周五住 | 3 槽位 |
| 3 | `destination+check_in_date+room_type` | 武汉明天大床房 | 3 槽位 |
| 4 | `destination+check_in_date+room_type` | 上海周五双床房 | 3 槽位 |
| 5 | `destination+check_in_date+check_out_date` | 武汉今晚住一晚 | 3 槽位（强制双填）|
| 6 | `destination+check_in_date+check_out_date` | 上海明晚住一晚 | 3 槽位 |
| 7 | `destination+adult_count+room_type` | 武汉 2 个人大床房 | 3 槽位 |
| 8 | `destination+adult_count+room_type` | 上海 1 个人双床房 | 3 槽位 |
| 9 | `destination+adult_count+room_count` | 武汉 2 个人订 1 间房 | 3 槽位 |
| 10 | `destination+adult_count+room_count` | 上海 3 个人 2 间房 | 3 槽位 |
| 11 | `destination+check_in_date+adult_count` | 武汉明天 2 个人 | 3 槽位 |
| 12 | `destination+check_in_date+adult_count` | 上海周五 3 个人 | 3 槽位 |
| 13 | `destination+child_count+child_ages` | 武汉 1 个 6 岁小孩 | 3 槽位 |
| 14 | `destination+child_count+child_ages` | 上海 2 个儿童一个 6 岁一个 3 岁 | 3 槽位 |
| 15 | `destination+hotel_name+room_type` | 武汉亚朵大床房 | 3 槽位 |
| 16 | `destination+hotel_name+room_type` | 上海维也纳双床房 | 3 槽位 |
| 17 | `destination+is_nearby+hotel_name` | 武汉附近亚朵 | 3 槽位 |
| 18 | `destination+auto_select_first+hotel_name` | 武汉最近的亚朵 | 3 槽位 |
| 19 | `destination+guest_names+room_type` | 武汉给张三订大床房 | 3 槽位 |
| 20 | `destination+guest_names+check_in_date` | 武汉给张三明天订 | 3 槽位 |

---

### 4 槽位

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `destination+check_in_date+adult_count+room_type` | 武汉明天 2 个人订大床房 | 4 槽位 |
| 2 | `destination+check_in_date+adult_count+room_type` | 上海周五 3 个人双床房 | 4 槽位 |
| 3 | `destination+check_in_date+check_out_date+adult_count` | 武汉明晚 2 个人 | 4 槽位（强制双填）|
| 4 | `destination+check_in_date+check_out_date+adult_count` | 上海今晚住一晚 1 个人 | 4 槽位 |
| 5 | `destination+hotel_name+check_in_date+room_type` | 武汉亚朵明晚大床房 | 4 槽位 |
| 6 | `destination+hotel_name+check_in_date+room_type` | 上海维也纳周五双床房 | 4 槽位 |
| 7 | `destination+hotel_name+check_in_date+adult_count` | 武汉亚朵明天 2 个人 | 4 槽位 |
| 8 | `destination+hotel_name+check_in_date+adult_count` | 上海维也纳周五 3 个人 | 4 槽位 |
| 9 | `destination+check_in_date+check_out_date+room_type` | 武汉明晚大床房 | 4 槽位（强制双填）|
| 10 | `destination+check_in_date+check_out_date+room_type` | 上海今晚住一晚双床房 | 4 槽位 |
| 11 | `destination+adult_count+room_count+room_type` | 武汉 2 个人 1 间大床房 | 4 槽位 |
| 12 | `destination+adult_count+room_count+room_type` | 上海 3 个人 2 间双床房 | 4 槽位 |
| 13 | `destination+hotel_name+adult_count+room_type` | 武汉亚朵 2 个人大床房 | 4 槽位 |
| 14 | `destination+hotel_name+adult_count+room_type` | 上海维也纳 1 个人双床房 | 4 槽位 |

> 注意 4 槽位时容易混 `room_count` 和 `adult_count`——用户说"2 个房间 2 个人"才同时填；说"2 个人住一间"只填 `adult_count`。

---

### 5 槽位

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `destination+check_in_date+adult_count+child_count+room_type` | 武汉明天 2 大 1 小订大床房 | 5 槽位 |
| 2 | `destination+check_in_date+adult_count+child_count+room_type` | 上海周五 3 大 2 小双床房 | 5 槽位 |
| 3 | `destination+hotel_name+check_in_date+adult_count+room_type` | 武汉亚朵明天 2 个人大床房 | 5 槽位 |
| 4 | `destination+hotel_name+check_in_date+adult_count+room_type` | 上海维也纳周五 3 个人双床房 | 5 槽位 |
| 5 | `destination+check_in_date+check_out_date+adult_count+room_type` | 武汉明晚 2 个人大床房 | 5 槽位（强制双填）|
| 6 | `destination+check_in_date+check_out_date+adult_count+room_type` | 上海今晚住一晚 1 个人双床房 | 5 槽位 |
| 7 | `destination+hotel_name+check_in_date+check_out_date+adult_count` | 武汉亚朵明晚 2 个人 | 5 槽位（强制双填）|
| 8 | `destination+hotel_name+check_in_date+check_out_date+adult_count` | 上海维也纳今晚住一晚 3 个人 | 5 槽位 |
| 9 | `destination+adult_count+child_count+child_ages+room_type` | 武汉 2 大 1 小（6 岁）大床房 | 5 槽位 |
| 10 | `destination+adult_count+child_count+child_ages+room_type` | 上海 3 大 2 小（一个 6 岁一个 3 岁）双床房 | 5 槽位 |
| 11 | `destination+check_in_date+adult_count+room_count+room_type` | 武汉明天 2 个人 1 间大床房 | 5 槽位 |
| 12 | `destination+check_in_date+adult_count+room_count+room_type` | 上海周五 3 个人 2 间双床房 | 5 槽位 |

> 5 槽位常见缺：`hotel_name`（不指定品牌时反问）或 `check_out_date`（仅说"明天"不强制填 out）。

---

### 6 槽位

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `destination+check_in_date+check_out_date+adult_count+child_count+room_type` | 武汉明晚 2 大 1 小订大床房 | 6 槽位（强制双填）|
| 2 | `destination+check_in_date+check_out_date+adult_count+child_count+room_type` | 上海今晚住一晚 2 大 1 小双床房 | 6 槽位 |
| 3 | `destination+hotel_name+check_in_date+check_out_date+adult_count+room_type` | 武汉亚朵明晚 2 个人大床房 | 6 槽位（强制双填）|
| 4 | `destination+hotel_name+check_in_date+check_out_date+adult_count+room_type` | 上海维也纳今晚住一晚 3 个人双床房 | 6 槽位 |
| 5 | `destination+hotel_name+check_in_date+adult_count+room_count+room_type` | 武汉亚朵明天 2 个人 1 间大床房 | 6 槽位 |
| 6 | `destination+hotel_name+check_in_date+adult_count+room_count+room_type` | 上海维也纳周五 3 个人 2 间双床房 | 6 槽位 |
| 7 | `destination+check_in_date+check_out_date+adult_count+room_count+room_type` | 武汉明晚 2 个人 1 间大床房 | 6 槽位（强制双填）|
| 8 | `destination+check_in_date+check_out_date+adult_count+room_count+room_type` | 上海今晚住一晚 3 个人 2 间双床房 | 6 槽位 |
| 9 | `destination+hotel_name+check_in_date+check_out_date+room_count+room_type` | 武汉亚朵明晚 1 间大床房 | 6 槽位（强制双填，缺 adult_count）|
| 10 | `destination+hotel_name+check_in_date+check_out_date+room_count+room_type` | 上海维也纳今晚住一晚 2 间双床房 | 6 槽位 |
| 11 | `destination+check_in_date+adult_count+child_count+child_ages+room_type` | 武汉明天 2 大 1 小（6 岁）大床房 | 6 槽位 |
| 12 | `destination+check_in_date+adult_count+child_count+child_ages+room_type` | 上海周五 3 大 2 小（一个 6 岁一个 3 岁）双床房 | 6 槽位 |

> 6 槽位开始出现 `guest_names` 较合理

---

### 7 槽位

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | `destination+hotel_name+check_in_date+check_out_date+adult_count+child_count+room_type` | 武汉亚朵明晚 2 大 1 小订大床房 | 7 槽位（强制双填）|
| 2 | `destination+hotel_name+check_in_date+check_out_date+adult_count+child_count+room_type` | 上海维也纳今晚住一晚 3 大 2 小双床房 | 7 槽位 |
| 3 | `destination+check_in_date+check_out_date+adult_count+child_count+child_ages+room_type` | 武汉明晚 2 大 1 小（6 岁、3 岁）大床房 | 7 槽位（强制双填）|
| 4 | `destination+check_in_date+check_out_date+adult_count+child_count+child_ages+room_type` | 上海今晚住一晚 3 大 2 小（一个 6 岁一个 3 岁）双床房 | 7 槽位 |
| 5 | `destination+hotel_name+check_in_date+check_out_date+adult_count+room_count+room_type` | 武汉亚朵明晚 2 个人 1 间大床房 | 7 槽位（强制双填）|
| 6 | `destination+hotel_name+check_in_date+check_out_date+adult_count+room_count+room_type` | 上海维也纳今晚住一晚 3 个人 2 间双床房 | 7 槽位 |
| 7 | `destination+check_in_date+check_out_date+adult_count+child_count+child_ages+room_type` | 武汉江汉区明晚 2 大 1 小（6 岁、3 岁）大床房 | 7 槽位（强制双填）|
| 8 | `destination+check_in_date+check_out_date+adult_count+child_count+child_ages+room_type` | 上海陆家嘴今晚住一晚 3 大 2 小（一个 6 岁一个 3 岁）双床房 | 7 槽位 |
| 9 | `destination+hotel_name+check_in_date+check_out_date+guest_names+room_type+adult_count` | 武汉亚朵明晚给张三订大床房 2 个人 | 7 槽位（强制双填，缺 child_count）|
| 10 | `destination+hotel_name+check_in_date+check_out_date+guest_names+room_type+adult_count` | 上海维也纳今晚住一晚给张三李四大床房 3 个人 | 7 槽位 |

---

### 8+ 槽位（最理想首轮 query）

| # | 组合 | 首轮 query | 槽位值 |
|---|---|---|---|
| 1 | 全填 8 槽位 | 武汉亚朵明晚 2 大 1 小订大床房给张三李四 | 8 槽位（强制双填）|
| 2 | 全填 8 槽位 | 上海维也纳今晚住一晚 3 大 2 小（一个 6 岁一个 3 岁）双床房给张三李四王五 | 8 槽位 |
| 3 | 全填 9 槽位 | 武汉江汉区亚朵明晚 2 大 1 小（6 岁、3 岁）订大床房给张三李四 | 9 槽位（强制双填）|
| 4 | 全填 9 槽位 | 上海陆家嘴维也纳今晚住一晚 3 大 2 小（一个 6 岁一个 3 岁）双床房给张三李四王五 | 9 槽位 |
| 5 | 全填 10 槽位 | 武汉江汉区亚朵明晚 2 大 1 小（6 岁、3 岁）订大床房 2 间给张三李四 | 10 槽位（强制双填）|
| 6 | 全填 10 槽位 | 上海陆家嘴维也纳今晚住一晚 3 大 2 小（一个 6 岁一个 3 岁）双床房 3 间给张三李四王五 | 10 槽位 |
| 7 | 全填 11 槽位 | 武汉江汉区亚朵最近的明晚 2 大 1 小（6 岁、3 岁）订大床房 2 间给张三李四 | 11 槽位（强制双填，"最近的"→auto_select_first）|
| 8 | 全填 12 槽位 | 武汉江汉区亚朵附近最近的明晚 2 大 1 小（6 岁、3 岁）订大床房 2 间给张三李四 | **注**："附近+最近"语义矛盾，is_nearby=True / auto_select_first=True 需 LLM 判断保留 |

> 12 槽位全填非常罕见，首轮 user 一般只能精确说出 6-8 个；剩余靠**反问补全**（反问时 LLM 调用对应 select_xxx 工具，user 下一轮补足）

---

## 4. 对照与差异

| 维度 | maoyan 电影票 | maoyan 演唱会 | tc_travel 酒店 |
|---|---|---|---|
| 槽位数 | 6 | 6 | 12 |
| 跨字段联想 | **片名数字**不算 quantity | **观演人数覆盖 ticket_count**（viewer-first policy）| **房型/床型**不算人数、**人数**不算房间数 |
| 日期格式 | "X月X日"（如"6月12日"）| "X月X日"（如"6月12日"）| ISO `YYYY-MM-DD` |
| 必填双写 | 无强制 | 无强制 | **"今晚/明晚/X 晚上"必须同时填 in+out**（住 1 晚）|
| 城市+区/商圈 | 无 | 无 | **整串合并**到 destination |
| 城市+品牌 | 无 | 无 | **拆分**（城市→destination，品牌→hotel_name）|
| time 槽位 | 有（场次时分）| **无**（场次日期就够）| 无 |
| cinema 槽位 | `cinema_name` | **无**（`city` 替代，按城市巡演）| 无 |
| 票档偏好 | 无（统一票价）| `ticket_grade_preference`（VIP/内场/看台/999元）| `room_type`（大床房/双床房）|
| 演员/导演 | `person_name` 单独槽位 | 无（歌手就是 show_name）| 无此概念 |
| is_nearby vs auto_select_first | 无 | 无 | **不等价**："附近"≠"最近的" |

---

## 5. 易错点速查（review prompt 时重点查）

1. **maoyan 电影 `quantity` 是否被"复仇者联盟4"误提为 4？** → 必须查 docstring 强制规则
2. **maoyan 电影 `time` 是否在不带时段词时双向试探？** → "8 点"既查 08:xx 又查 20:xx
3. **maoyan 电影 `date` 是否查日期速查表？** → "明天"必须转 "6月12日"，禁止原话传入
4. **maoyan 演唱会 `ticket_count` 是否被 `viewer_names` 覆盖？** → "给张三李四买 4 张"会被覆盖为 2 张（viewer-first policy）
5. **maoyan 演唱会 `ticket_grade_preference` 是否包含价格？** → 提到价格必须包含价格（"999元"而非"一千左右"）
6. **maoyan 演唱会 `city` 是否被误填 `cinema_name`？** → 演唱会无 cinema，按城市巡演
7. **hotel 城市+区/商圈是否被拆到 hotel_name？** → "武汉江汉区"必须整串到 destination
8. **hotel 城市+品牌是否被整串塞 hotel_name？** → "武汉亚朵"必须拆 destination + hotel_name
9. **hotel 房型词是否被误提为 adult_count？** → "双人床"是房型不是 2 人
10. **hotel 人数词是否被误提为 room_count？** → "3 个人"不是 3 间房
11. **hotel "今晚"是否强制双填 in+out？** → 漏 out 会导致跨夜判定错误
12. **hotel child_ages 6 个月/不到 1 岁是否统一 `'小于1岁'`？** → 禁止编造
13. **hotel "最近的"是否走了 `auto_select_first` 而非 `is_nearby`？** → 两者不等价
