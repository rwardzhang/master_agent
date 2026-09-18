# tool_select 日志审计报告（2026-08-27）

**数据来源**：`export-e5482e5d-9d9d-468b-98a6-893939c5f3ad.json`（CLS 导出，测试环境 prj4rrwq-testing，2026-08-27 19:05~19:09）
**样本规模**：200 条 tool_select 样本
**审计依据**：`references/fc-工具职能说明.md`（新版）+ 训练集 `train_fc_data_2026.08.27.jsonl`（30680 条，新 schema：movie_list 4 段 / plan_route 5 段 / search_along_route 5 段）同句先例与权威 arity + 逐条上下文复核
**verdict 口径**：正确 / 错误 / 可接受但建议优化（仅「错误」进入回标训练集）
**版本说明**：v3 —— 基准为 2026.08.27 新 schema（v2 切换）；v3 依据新数据集先例核查，撤销 case 190 的 web_search 修正（影院域影人作品集 → unknown 与新数据集 15 条先例一致，原答案正确）

## 一、审计总览

| verdict | 条数 | 占比 | 说明 |
|---|---|---|---|
| ✅ 正确 | 173 | 86.5% | 工具与参数均符合职能边界（新 schema） |
| ❌ 错误 | 18 | 9.0% | **需回标**，corrected_answer 已给出 |
| ⚠️ 可接受但建议优化 | 9 | 4.5% | 不入回标，格式/口径建议 |

### 错误模式分布

| 错误模式 | 条数 | case_id | 典型表现 |
|---|---|---|---|
| 导航意图误判 unknown | 3 | 21, 22, 25 | 「导航回家/我要回家帮我导航」明确导航意图被判 unknown，同句在别的轮次又判对（线上输出不稳定） |
| 时间日期类误判 unknown | 8 | 63, 119, 122, 137, 147, 155, 165, 177 | 「星期几/几号」被默认打成 unknown，训练集先例主流为 web_search（「几点」才是 unknown） |
| 影院泛泛推荐误判 unknown | 4 | 69, 92, 94, 103 | 「推荐个电影/我要看电影」无约束推荐应压成 movie_list|hot|城市|-，被默认 unknown |
| plan_route 缺第 5 位占位 | 1 | 132 | 新 schema plan_route 为 5 段，原答案 4 段缺 waypoints 占位；数据集做法：中间站不入 waypoints（98.9% 填 `-`） |
| 补槽未继承意图 | 2 | 191, 198 | 「苏州吧/五一」是对上轮待确认槽位的回答，应继承 travel_plan 意图，被默认 unknown |

## 二、错误数据明细（verdict=错误，共 18 条，回标监督答案来源）

> corrected_answer 直接作为第 4 步 `build_relabel_train.py` 的监督答案；标注 ★ 的 corrected 需人工确认细节。

### case 21 [出行] — 导航意图误判 unknown

- **query**：我要回家，帮我导航一下。
- **original_answer**：`unknown|-`
- **corrected_answer**：`navigation|深圳南山区蛇口花园城|-`
- **reason**：「我要回家，帮我导航一下」与同 session「导航回家」(case 20 已正确标 navigation) 同义，明确导航意图误判 unknown；destination 用记忆中家地址
- **上下文摘要**：A: 小鹅记得你之前说过家是深圳滨海腾讯大厦，不过具体的小区或门牌号还没告诉我呢。要不 / U: 导航回家。 / A: 好的，导航回家～不过小鹅目前只知道你家在深圳滨海腾讯大厦附近，能告诉我具体的小区 / U: 我要回家，帮我导航一下。

### case 22 [出行] — 导航意图误判 unknown

- **query**：导航回家。
- **original_answer**：`unknown|-`
- **corrected_answer**：`navigation|深圳南山区蛇口花园城|-`
- **reason**：「导航回家」用槽位发起导航 → navigation（同 session case 20/26 已正确标注，同句不同判属线上输出不稳定）
- **上下文摘要**：A: 嗯嗯，那你说地址，我记下来，以后你一说“回家”我就懂啦～ / U: 你知道我家在哪儿吗？ / A: 小鹅记得你之前说过家是深圳滨海腾讯大厦，不过具体的小区或门牌号还没告诉我呢。要不 / U: 导航回家。

### case 25 [出行] — 导航意图误判 unknown

- **query**：导航回家。
- **original_answer**：`unknown|-`
- **corrected_answer**：`navigation|深圳南山区蛇口花园城|-`
- **reason**：同「导航回家」→ navigation，与 case 20/26 同句冲突
- **上下文摘要**：A: 小鹅当然记得，你之前提到过家在深圳，不过具体地址还没告诉我呢。要是你愿意，可以现 / U: 导航回家。 / A: 好嘞，你说的“家”具体在哪个小区或者哪条路呀？告诉我地址，我就能带你出发啦～ / U: 导航回家。

### case 63 [信息查询] — 时间日期类误判 unknown

- **query**：今天星期几？
- **original_answer**：`unknown|-`
- **corrected_answer**：`web_search|-`
- **reason**：「今天星期几」训练集先例 web_search 18/19 条，主流为 web_search，非 unknown
- **上下文摘要**：A: 哈哈，这个问题可难倒我啦。我呀，没有具体的年龄，就像住在你车里的邻家姐姐，永远都 / U: 你会说英语吗？ / A: 当然会啦，中英文切换都没问题。不过其他语种还在学习中，要是想用英文聊天，随时可以 / U: 今天星期几？

### case 69 [影院电影] — 影院泛泛推荐误判 unknown

- **query**：推荐个电影看看
- **original_answer**：`unknown|-`
- **corrected_answer**：`movie_list|hot|深圳|-` ★
- **reason**：「推荐个电影看看」泛泛无约束推荐，按职能说明可压成热映片单 movie_list|hot|城市|-（case 144/153 同句已正确标注）
- **上下文摘要**：U: 我要份别太腻吃的 / A: 我们目前支持点瑞幸咖啡, 麦当劳, 肯德基，可到店自取，选择哪个品牌去下单呢？ / U: 推荐个电影看看

### case 92 [影院电影] — 影院泛泛推荐误判 unknown

- **query**：我要看看今天有什么好看的电影。
- **original_answer**：`unknown|-`
- **corrected_answer**：`movie_list|hot|芜湖|-`
- **reason**：「我要看看今天有什么好看的电影」与 case 90/93/97 同义，同 session 上文有芜湖片单语境，应继承 movie_list
- **上下文摘要**：U: 我想看看今天有什么好看的电影。 / A: 芜湖hot共3部： / U: 我要看看今天有什么好看的电影。

### case 94 [影院电影] — 影院泛泛推荐误判 unknown

- **query**：来介绍一下今天的。
- **original_answer**：`unknown|-`
- **corrected_answer**：`movie_list|hot|芜湖|-`
- **reason**：「来介绍一下今天的」承接上文电影片单语境（上文刚列芜湖hot片单），补槽式回复应继承意图，不能默认 unknown
- **上下文摘要**：U: 我点了。 那个，我想看一下今天有什么电影儿。 / A: 芜湖hot共3部： / U: 来介绍一下今天的。

### case 103 [影院电影] — 影院泛泛推荐误判 unknown

- **query**：我要看电影
- **original_answer**：`unknown|-`
- **corrected_answer**：`movie_list|hot|武汉|-` ★
- **reason**：「我要看电影」泛泛想看电影、无题材/评分等约束 → movie_list|hot|城市|-（职能说明：仅带明显偏好约束才 unknown）
- **上下文摘要**：U: 最近有什么好看的电影 / A: 武汉hot共3部： / U: 我要看电影

### case 119 [信息查询] — 时间日期类误判 unknown

- **query**：明天几号来着？
- **original_answer**：`unknown|-`
- **corrected_answer**：`web_search|-`
- **reason**：「明天几号」日期类问答 → web_search（「几点」才是 unknown，几号≠几点）
- **上下文摘要**：A: 广东省/深圳市/南山区当前天气：阴，气温28℃，湿度86%，西南风1-2级；（更 / U: 给我讲个笑话 / A: 好啊，给你讲个轻松的小笑话。 / U: 明天几号来着？

### case 122 [信息查询] — 时间日期类误判 unknown

- **query**：今天星期几
- **original_answer**：`unknown|-`
- **corrected_answer**：`web_search|-`
- **reason**：同「今天星期几」，先例主流 web_search
- **上下文摘要**：A: 收到，正在为您搜索门店及商品在最近的车速取门店，为您推荐以下餐品 / U: 帮我导航回家 / A: 好嘞，你说“回家”——具体是哪个小区呀？告诉我地址，我就能带你出发啦！ / U: 今天星期几

### case 132 [出行] — plan_route 缺第 5 位占位

- **query**：规划从广东省深圳市南山区腾讯滨海大厦(白石路东)出发，先前往长安亭院火锅(深圳总店)，再前往璟德·茶馆·茶空间(海岸城店)的驾车路线
- **original_answer**：`plan_route|广东省深圳市南山区腾讯滨海大厦(白石路东)|璟德·茶馆·茶空间(海岸城店)|driving`
- **corrected_answer**：`plan_route|广东省深圳市南山区腾讯滨海大厦(白石路东)|璟德·茶馆·茶空间(海岸城店)|driving|-`
- **reason**：新数据集 plan_route 1358 条全部 5 段，原答案 4 段缺 waypoints 占位。按数据集实际做法「先去B再去C」的中间站 B **不入** waypoints（1343/1358=98.9% 填 `-`，含同场景先例「先前往长安亭院火锅…再前往…」→ waypoints=`-`），补 `-` 即可；不填长安亭院火锅
- **上下文摘要**：A: [search_place] 1. 长安亭院火锅(深圳总店) 美食:火锅，深圳市 / U: 搜索深圳南山区适合休闲放松的地方 / A: [search_place] 1. 璟德·茶馆·茶空间(海岸城店) 娱乐休闲:茶 / U: 规划从广东省深圳市南山区腾讯滨海大厦(白石路东)出发，先前往长安亭院火锅(深圳总

### case 137 [信息查询] — 时间日期类误判 unknown

- **query**：今天几号了
- **original_answer**：`unknown|-`
- **corrected_answer**：`web_search|-`
- **reason**：「今天几号」训练集先例为 web_search
- **上下文摘要**：U: 点个早餐 / A: 我们目前支持点瑞幸咖啡, 麦当劳, 肯德基，可到店自取，选择哪个品牌去下单呢？ / U: 今天几号了

### case 147 [信息查询] — 时间日期类误判 unknown

- **query**：今天几号了
- **original_answer**：`unknown|-`
- **corrected_answer**：`web_search|-`
- **reason**：同「今天几号了」→ web_search
- **上下文摘要**：U: 点个早餐 / A: 我们目前支持点瑞幸咖啡, 麦当劳, 肯德基，可到店自取，选择哪个品牌去下单呢？ / U: 今天几号了

### case 155 [信息查询] — 时间日期类误判 unknown

- **query**：今天几号了
- **original_answer**：`unknown|-`
- **corrected_answer**：`web_search|-`
- **reason**：同「今天几号了」→ web_search
- **上下文摘要**：U: 点个早餐 / A: 我们目前支持点瑞幸咖啡, 麦当劳, 肯德基，可到店自取，选择哪个品牌去下单呢？ / U: 今天几号了

### case 165 [信息查询] — 时间日期类误判 unknown

- **query**：明天几号来着？
- **original_answer**：`unknown|-`
- **corrected_answer**：`web_search|-`
- **reason**：「明天几号来着」同上 → web_search
- **上下文摘要**：A: 广东省/深圳市/南山区当前天气：小雨，气温27℃，湿度95%，西北风1-2级；（ / U: 给我讲个笑话 / A: 一只小企鹅去肯德基点餐，它对服务员说：“我要一份新奥尔良烤鸡腿堡！”服务员愣了一 / U: 明天几号来着？

### case 177 [信息查询] — 时间日期类误判 unknown

- **query**：今天周几？
- **original_answer**：`unknown|-`
- **corrected_answer**：`web_search|-`
- **reason**：「今天周几」同「星期几」口径 → web_search
- **上下文摘要**：A: 好的，那就不发。 / U: 3个人，拜拜。 / A: 好的，拜拜，路上注意安全，祝您和朋友们一路顺风！ / U: 今天周几？

### case 191 [出行] — 补槽未继承意图

- **query**：苏州吧
- **original_answer**：`unknown|-`
- **corrected_answer**：`travel_plan|苏州周末游攻略` ★
- **reason**：上一轮 assistant 问「你更想感受哪种氛围（杭州/苏州）」，本轮「苏州吧」为补槽式回复，应继承上文周末出游意图 → travel_plan（query 为提炼建议，可按 9-14 字口径打磨）
- **上下文摘要**：U: 杭州跟苏州搁一块儿比这周末去哪个更得劲儿 / A: 杭州和苏州各有各的味道。这周末杭州西湖边桂花正香，适合散步赏秋；苏州园林里银杏渐 / U: 苏州吧

### case 198 [出行] — 补槽未继承意图

- **query**：五一。
- **original_answer**：`unknown|-`
- **corrected_answer**：`travel_plan|五一台北旅游攻略` ★
- **reason**：上一轮 assistant 问「你打算什么时候出发」（规划去台北），本轮「五一」为时间补槽，应继承 travel_plan 意图，不能默认 unknown
- **上下文摘要**：A: 好的，那我们接下来去台北。我先帮你规划一下从武汉到台北的路线，看看是坐飞机还是走 / U: 晚上前那天。 / A: 嗯，我猜你是说“今天晚上之前到台北”对吗？现在已经是晚上快十二点了，今晚到台北恐 / U: 五一。

## 三、可接受但建议优化（verdict=可接受，共 9 条，不入回标）

| case | 域 | query | original_answer | 建议修正 | 说明 |
|---|---|---|---|---|---|
| 1 | 音乐 | 狂飙里面高启强的bgm | `music_search|狂飙里面高启强的bgm|false|false` | `music_search|狂飙高启强bgm|false|false` | 工具与 need_play/random_search 正确；query 原话复刻（32.9% 先例也如此），可提炼去「的/里面 |
| 8 | 出行 | 软件园基地。 | `navigation|深圳南山软件园基地|-` | `unknown|-` | 上文 assistant 在问新公司地址（记忆登记语境），出行域无记忆更新工具 → 严格口径应为 unknown；原答案 nav |
| 18 | 出行 | 导航去公司。 | `navigation|公司|-` | `navigation|生产力大楼|-` | 工具正确；destination 填「公司」未展开，建议用记忆中公司地址「生产力大楼」（同 session case 12 已填 |
| 26 | 出行 | 导航回家。 | `navigation|家|-` | `navigation|深圳南山区蛇口花园城|-` | 工具正确；destination 填「家」未展开，与 case 20（填具体地址）口径不一，建议统一为记忆中家地址 |
| 37 | 地点 | 我想吃点东西。 他就 | `unknown|-` | `维持原答案` | 「我想吃点东西」无明确品类检索词，unknown 可辩护；若按意图推断也可 search_place|吃的|<中心点>，建议人工 |
| 39 | 地点 | 我想吃点东西。 | `unknown|-` | `维持原答案` | 同 case 37：无明确检索词的吃饭需求，unknown/search_place 两可 |
| 91 | 影院电影 | 你看一下啊，我我再来一遍。 | `unknown|-` | `movie_list|hot|芜湖|-` | 「你看一下啊，我我再来一遍」ASR 噪声大，「再来一遍」更像重复列表请求（应继承 movie_list）；原 unknown 在 |
| 128 | 出行 | 规划从长安亭院火锅到深圳湾公园的驾车路线 | `plan_route|长安亭院火锅|深圳湾公园|driving` | `plan_route|长安亭院火锅|深圳湾公园|driving|-` | 工具与参数正确；缺第 5 位 waypoints 占位「-」（新数据集 plan_route 1358 条全部 5 段），aud |
| 161 | 出行 | 到高铁站近的那个。 | `navigation|芜湖镜湖万达广场|-` | `navigation|芜湖镜湖万达广场|同庆楼(银湖店)` | destination 正确（镜湖万达离芜湖站最近）；若训练标签要求自包含，建议回填上一轮已锁定 waypoints=同庆楼(银 |

> 其中 case 8/37/39/91 存在口径分歧，建议人工裁决后统一；case 128 为 arity 格式偏差（缺 waypoints 占位），若直接入训会被 `audit_labels.py` 拦截。

> **v2 变更**：case 30/32/44/46（movie_list 4 段）在新 schema 下完全合规，由「可接受但建议优化」改判「正确」；case 132 按新职能说明的同场景标准示例改判「错误」。

## 四、正确样本清单（verdict=正确，共 172 条）

### 信息查询（105 条）

| case | query | original_answer |
|---|---|---|
| 3 | 今天的天气怎么样？ | `weather|深圳南山区|now` |
| 6 | 天气怎么样？ | `weather|深圳南山区|now` |
| 27 | 深圳明天天气怎么样？ | `weather|深圳|future` |
| 28 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 34 | 未来一周呢？ | `weather|深圳南山区|future` |
| 35 | 明天呢？ | `weather|深圳南山区|future` |
| 36 | 今天的天气怎么样？ 这么说，这个问答有没有问题？然后第二部分。 | `weather|深圳南山区|now` |
| 38 | 今天的天气怎么样？ | `weather|深圳市南山区|now` |
| 40 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 41 | 是 | `unknown|-` |
| 42 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 43 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 48 | 最近肯德基有什么新品 | `web_search|-` |
| 49 | 帮我查下天气 | `weather|深圳市南山区|now` |
| 50 | 天气怎么了 | `weather|深圳南山区|now` |
| 51 | 今天天气怎么样了 | `weather|深圳市南山区|now` |
| 53 | 帮我查一下印享星的会员权益。 | `web_search|-` |
| 57 | 明天天气怎么样 | `weather|深圳市南山区|future` |
| 59 | 现在几点了？ | `unknown|-` |
| 61 | user:搜索麦当劳麦辣鸡翅点餐入口或点餐方式 | `web_search|-` |
| 62 | 六合彩今晚开什么号 | `web_search|-` |
| 64 | 帮我查一下深圳限号 | `web_search|-` |
| 65 | 今天天气怎么样？ | `weather|深圳市南山区|now` |
| 66 | 今天深圳天气怎么样 | `weather|深圳|now` |
| 67 | 帮我查下今晚的球赛赔率 | `web_search|-` |
| 68 | 今天股市行情怎么样？ | `web_search|-` |
| 72 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 73 | 选第五个。 | `unknown|-` |
| 74 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 75 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 76 | user:搜索肯德基香骨鸡的订购方式或在线下单入口 | `web_search|-` |
| 77 | user:搜索肯德基香辣鸡翅订购方式或在线下单入口 | `web_search|-` |
| 78 | user:搜索肯德基土豆泥的订购方式或在线下单链接 | `web_search|-` |
| 79 | user:查询肯德基在线订购两个蛋挞的渠道或流程 | `web_search|-` |
| 80 | user:搜索肯德基在线订购薯条的渠道或小程序 | `web_search|-` |
| 81 | user:搜索肯德基红豆派订购方式或小程序入口 | `web_search|-` |
| 82 | user:查询肯德基在线订餐服务或小程序入口 | `web_search|-` |
| 83 | user:搜索肯德基鸡排堡的订购方式或肯德基外卖平台入口 | `web_search|-` |
| 84 | user:搜索肯德基香辣鸡腿汉堡的订购方式或在线下单链接 | `web_search|-` |
| 85 | 正常 | `unknown|-` |
| 86 | 今天天气怎么样 | `weather|武汉市江夏区|now` |
| 105 | 今天的天气怎么样 | `weather|武汉市江夏区|now` |
| 106 | 今天天气。 | `weather|深圳南山区|now` |
| 107 | 选第一个 | `unknown|-` |
| 108 | 今天天气怎么样 | `weather|武汉市江夏区|now` |
| 109 | 选第四个。 | `unknown|-` |
| 110 | 今天天气怎么样？ 一个人。 | `weather|武汉市江夏区|now` |
| 111 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 112 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 113 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 116 | 明天会下雨吗 | `weather|深圳南山区|future` |
| 117 | 我该买什么股票 | `web_search|-` |
| 118 | 帮我查下火车票 | `web_search|-` |
| 120 | 今天天气怎么样？ | `weather|深圳市南山区|now` |
| 123 | 帮我查一下明天的天气 | `weather|深圳市南山区|future` |
| 124 | 今天天气怎么样 | `weather|深圳市南山区|now` |
| 125 | 今天股票行情怎么样 | `web_search|-` |
| 126 | 帮我查一下今天限行 | `web_search|-` |
| 127 | 明天天气怎么样 | `weather|深圳南山区|future` |
| 130 | 今天天气怎么样？武汉的天气再说下一雨。 | `weather|武汉|now` |
| 131 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 135 | 查一下深圳到广州的高铁 | `web_search|-` |
| 136 | 查一下油价 | `web_search|-` |
| 138 | 今天限号吗 | `web_search|-` |
| 139 | 今天天气怎么样 | `weather|深圳市南山区|now` |
| 140 | 今天深圳天气怎么样 | `weather|深圳|now` |
| 141 | 你觉得中美会打仗吗 | `web_search|-` |
| 142 | 帮我查下今晚的球赛赔率 | `web_search|-` |
| 143 | 今天股市行情怎么样？ | `web_search|-` |
| 145 | 查一下深圳到广州的高铁 | `web_search|-` |
| 146 | 查一下油价 | `web_search|-` |
| 148 | 今天限号吗 | `web_search|-` |
| 149 | 今天天气怎么样 | `weather|深圳市南山区|now` |
| 150 | 今天深圳天气怎么样 | `weather|深圳|now` |
| 151 | 帮我查下今晚的球赛赔率 | `web_search|-` |
| 152 | 今天股市行情怎么样？ | `web_search|-` |
| 154 | 查一下深圳到广州的高铁 | `web_search|-` |
| 156 | 查一下油价 | `web_search|-` |
| 157 | 今天限号吗 | `web_search|-` |
| 158 | 今天天气怎么样 | `weather|深圳市南山区|now` |
| 159 | 明天天气 | `weather|深圳南山区|future` |
| 163 | 天气 | `weather|深圳市南山区|now` |
| 166 | 今天天气怎么样？ | `weather|深圳南山区|now` |
| 168 | 最近千问发布了什么新的模型？ | `web_search|-` |
| 169 | 查一下高铁信息吧。 | `web_search|-` |
| 170 | 请问最近发布了什么模型是？ | `web_search|-` |
| 172 | 今天天气。 | `weather|深圳市南山区|now` |
| 173 | 点第一个吧。 | `unknown|-` |
| 174 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 175 | 今天天气怎么样 | `weather|深圳市南山区|now` |
| 176 | 退出订单。 | `unknown|-` |
| 178 | 明天天气怎么样 | `weather|深圳市南山区|future` |
| 179 | 选第一个吧。 | `unknown|-` |
| 180 | 帮我查一下今天限行 | `web_search|-` |
| 181 | 今天天气怎么样？ | `weather|武汉市江夏区|now` |
| 182 | 今天天气怎么样 | `weather|深圳市南山区|now` |
| 183 | 今天武汉的天气。 | `weather|武汉|now` |
| 184 | 嗯 | `unknown|-` |
| 185 | 嗯 | `unknown|-` |
| 186 | 嗯 | `unknown|-` |
| 187 | 有没有 | `unknown|-` |
| 188 | 嗯 | `unknown|-` |
| 189 | 你的时间 | `unknown|-` |
| 199 | 是不是也是馆内啊？ | `web_search|-` |
| 200 | 呃，我周末要带孩子去科技馆看一下那个深圳哪几个科技馆周末开门。 | `web_search|-` |

### 出行（24 条）

| case | query | original_answer |
|---|---|---|
| 4 | 帮我导航到第二个吧。 | `navigation|脆鲜生·脆鲩鱼火锅(海岸城店)|-` |
| 7 | 沿途的路况怎么样？ | `plan_route|广东省深圳市南山区腾讯滨海大厦(海天二路南)|南山软件园产业基地|driv` |
| 9 | 我的公司换了，现在在。 | `unknown|-` |
| 10 | 公司在生产力大楼。 | `unknown|-` |
| 11 | 路况怎么样？ | `plan_route|广东省深圳市南山区腾讯滨海大厦(桂庙路北)|生产力大楼|driving|-` |
| 12 | 导航去生产力大楼吧。 | `navigation|腾讯生产力大楼|-` |
| 13 | 我的公司在生产力大楼。 | `unknown|-` |
| 14 | 南山区。 | `unknown|-` |
| 16 | 到世界之窗有多远？ | `plan_route|广东省深圳市南山区腾讯滨海大厦(海天二路南)|深圳世界之窗|driving` |
| 17 | 世界之窗。 | `navigation|深圳世界之窗|-` |
| 19 | 深圳腾讯大厦。 | `navigation|深圳腾讯大厦|-` |
| 20 | 导航回家。 | `navigation|深圳南山区蛇口花园城|-` |
| 23 | 你知道我家在哪儿吗？ | `unknown|-` |
| 24 | 可以可以。 | `unknown|-` |
| 29 | 我要回家，顺便经过科技园，直接说吧，你还是直接写吧。 | `navigation|深圳安居鸿栖台1栋2单元1802|科技园` |
| 55 | 导航到八大家花园38街坊 | `navigation|八大家花园38街坊|-` |
| 60 | 我下周要去北京出差，在北京国贸附近。 | `unknown|-` |
| 70 | 我下班要去接孩子。 因为我下班要去接孩子。 | `unknown|-` |
| 71 | 我下班要去接孩子。 | `unknown|-` |
| 121 | 导航去亚洲金融大厦店瑞幸咖啡 | `navigation|瑞幸咖啡(亚洲金融大厦店)|-` |
| 160 | 途经点帮我添加了吗？ | `unknown|-` |
| 162 | 帮我导航到万达广场，途经同庆楼，嗯，银湖店。 | `navigation|万达广场|同庆楼(银湖店)` |
| 164 | 我的公司在腾讯大厦。 | `unknown|-` |
| 171 | 我明天要去上海出差。 | `unknown|-` |

### 影院电影（23 条）

| case | query | original_answer |
|---|---|---|
| 30 | 我看一下影院上映的功夫女足。 | `movie_list|hot|深圳|-` |
| 32 | 帮我看一下影院上映的功夫女足。 | `movie_list|hot|深圳|-` |
| 44 | 帮我看一下影院上映的八仙电影。 | `movie_list|hot|深圳|-` |
| 45 | 最近有什么好看的电影？ | `movie_list|hot|芜湖|-` |
| 46 | 最近有什么？ | `movie_list|hot|芜湖|-` |
| 47 | 最近有什么好看的电影？ | `movie_list|hot|芜湖|-` |
| 88 | 没事，那个就来试吧，看一下今天都有什么好看的电影。 | `movie_list|hot|芜湖` |
| 89 | 没事没事，我就问一下。 | `unknown|-` |
| 90 | 看一下今天都有什么好看的电影。 | `movie_list|hot|芜湖` |
| 93 | 我想看看今天有什么好看的电影。 | `movie_list|hot|芜湖` |
| 95 | 我点了。 那个，我想看一下今天有什么电影儿。 | `movie_list|hot|芜湖` |
| 96 | 我点了。 | `unknown|-` |
| 97 | 看一下今天有什么好看的电影。 | `movie_list|hot|芜湖` |
| 98 | 没法看。 | `unknown|-` |
| 99 | 看一下最近有什么好看的电影。 | `movie_list|hot|芜湖` |
| 100 | 不对呀，操[angry]。 | `unknown|-` |
| 101 | 我，我想看一下最近有什么好看的电影。 | `movie_list|hot|芜湖` |
| 102 | 第一集 | `unknown|-` |
| 104 | 最近有什么好看的电影 | `movie_list|hot|武汉` |
| 114 | 麦当劳最近的代言人是谁 | `unknown|-` |
| 115 | 麦当劳最近的代言人是谁 | `unknown|-` |
| 144 | 推荐个电影看看 | `movie_list|hot|深圳` |
| 153 | 推荐个电影看看 | `movie_list|hot|深圳` |

### 地点（15 条）

| case | query | original_answer |
|---|---|---|
| 5 | 帮我找一下附近的好吃的餐厅。 | `search_place|好吃的餐厅|广东省深圳市南山区腾讯滨海大厦(海天二路南)` |
| 15 | 世界之窗好玩吗？ | `unknown|-` |
| 31 | 帮我看一下影院上映的功夫女足。 你别说这个，说的有没有那个，看还有有没有 | `search_place|清淡一点的吃的|广东省深圳市南山区腾讯滨海大厦(海天二路西)` |
| 33 | 帮我看一下附近有什么好吃的。 | `search_place|好吃的|广东省深圳市南山区腾讯滨海大厦(海天二路西)` |
| 52 | 附近有瑞幸咖啡吗 | `search_place|瑞幸咖啡|广东省深圳市南山区腾讯滨海大厦(白石路东)` |
| 56 | user:搜索武汉市青山区三十八街 | `search_place|武汉市青山区三十八街|-` |
| 58 | 给我找个离国贸近还安静点的商务酒店。 | `search_place|安静商务酒店|北京市国贸` |
| 87 | 附近有什么好吃的？ | `search_place|好吃的|广东省深圳市南山区腾讯滨海大厦(白石路东)` |
| 129 | user:搜索深圳南山区的公园 | `search_place|公园|深圳南山区` |
| 133 | 搜索深圳南山区适合休闲放松的地方 | `search_place|适合休闲放松的地方|深圳南山区` |
| 134 | user:搜索深圳南山区适合5人聚餐且适合拍照的餐厅 | `search_place|适合5人聚餐且适合拍照的餐厅|深圳南山区` |
| 167 | 上海有什么好玩的吗？ | `search_place|好玩的|上海市` |
| 192 | 武汉有哪些地方适合观星的天文台 | `search_place|适合观星的天文台|武汉市` |
| 193 | 搜索深圳市南山区腾讯滨海大厦附近评价高的川菜馆 | `search_place|评价高的川菜馆|深圳市南山区腾讯滨海大厦` |
| 195 | 搜索深圳南山区附近评价高的川菜馆 | `search_place|评价高的川菜馆|深圳南山区` |

### 音乐（3 条）

| case | query | original_answer |
|---|---|---|
| 2 | 给我推荐一些适合深南大道上收听的轻松的歌 | `music_search|适合深南大道上收听的轻松的歌|false|false` |
| 54 | 播放音乐 | `music_search|-|true|true` |
| 197 | 放首周杰伦的歌 | `music_search|周杰伦|true|false` |

### 新闻（2 条）

| case | query | original_answer |
|---|---|---|
| 194 | user:获取今日新闻简报 | `news_briefing|auto` |
| 196 | user:获取今日新闻简报 | `news_briefing|auto` |

## 五、需人工复核项

1. **corrected 中带 ★ 的 4 条**：
   - case 69/103：movie_list 的 city 已从该 case 的 location 自动提取（深圳/武汉），请按 session 实际城市核对
   - case 191：`travel_plan|苏州周末游攻略` 的 query 为提炼建议，建议按 9-14 字口径打磨
   - case 198：`travel_plan|五一台北旅游攻略` 同上
2. **口径分歧 4 条**（case 8/37/39/91）：存在两种合理标注，建议团队定口径后统一
3. **同句冲突提示**：「导航回家」case 20/26=navigation、case 22/25=unknown；「推荐个电影看看」case 69=unknown、case 144/153=movie_list，说明线上模型输出不稳定，回标时应以训练集先例口径统一
4. **schema 已对齐**：本批日志 system prompt 与新训练集 2026.08.27 的 6 域 prompt 完全一致；三个改动工具的新口径——movie_list 增 movie_name 位（4 段）、plan_route/search_along_route 增 waypoints 位（5 段）——已在裁决中生效
5. **新数据集自身存疑先例（泛化数据相似度核对时发现，建议清理）**：
   - 信息查询域「今天星期几」共 4 条：1 条干净上下文 → web_search（与职能说明一致），**3 条带点单上下文 → unknown**（上下文形态与线上日志回标数据一致，疑似上次日志审计把线上模型的 unknown 错误直接回标入训，与本域干净先例及职能说明矛盾）。出行域另有 17 条「今天星期几」→unknown 属跨域场景，**合理，不需处理**
   - 影院域影人作品集类共 15 条 → **unknown** 高度一致（含「刘德华都有哪些代表作」「徐峥导演的作品有哪些」「诺兰导演的作品有哪些」等）。注意与音乐域相反（歌手代表作 39 条 → web_search）——**同一个人按所在域取不同标签是数据集既有口径**。本报告 case 190 已按此口径改判正确，撤销 web_search 修正
6. **waypoints 实际做法与职能说明文档分歧（已按数据集对齐）**：数据集 plan_route waypoints 位 1343/1358=98.9% 填 `-`、search_along_route 462/477=96.6% 填 `-`——「先去B再去C」「经B到C」的中间站 B **不入** waypoints（同场景先例「先前往长安亭院火锅…再前往…」→ waypoints=`-`），仅显式「途经/路过 X」且 X 为城市/服务区级时才填值。而新版职能说明的标准示例（先去长安亭院火锅再去璟德·茶馆 → waypoints=长安亭院火锅）与数据集主流相反。**本报告与泛化数据一律按数据集做法**（waypoints 填 `-`），建议同步修订职能说明文档。另：plan_route「从当前位置出发」的 origin 按数据集填**当前位置完整地址**（不填 `-`）
7. **家/公司槽位展开规则（数据集实证，已对齐）**：plan_route 遇「家/公司」时——**记忆中有对应地址则一律展开为记忆地址**（9/9 先例，如「从家到公司怎么走最近」→ `plan_route|北京市朝阳区建国路88号|北京市海淀区中关村软件园|driving|-`），**记忆无对应地址才保留槽位名**（「从公司回家的路线」无记忆 → `plan_route|公司|家|driving|-`）。navigation 回家/回公司两种填法并存（具体地址 398 条 vs 槽位名 216 条，65%/35%）。本批 case 18/26 的「参数展开优化」建议与此规则吻合；泛化数据已按此规则修正

## 六、后续步骤

```bash
# 基准训练集（新 schema）
export WECAR_FC_TRAIN=/Users/rwardzhang/PycharmProjects/master_agent_qc/fc/wecar-fc-tool-labeler/train_fc_data_2026.08.27.jsonl

# 1) 按本报告第二节制作 reviewed.csv
#    列：case_id,verdict,original_answer,md_answer,final_train_answer,use_for_training,reason
#    verdict=错误 且 corrected 无歧义 → use_for_training=yes（★ 的 4 条建议复核后再定）

# 2) 回标（只基于错误样本，绝不改 user）
python3 scripts/build_relabel_train.py \
    /Users/rwardzhang/PycharmProjects/master_agent_qc/fc/extracted_cases_20260827.jsonl \
    reviewed.csv -o relabeled_20260827.jsonl --verdict-only 错误 --keep-meta

# 3) 质量门禁（--train 已默认指向新数据集）
python3 scripts/audit_labels.py relabeled_20260827.jsonl --csv errors.csv

# 4) 转可训练格式
python3 scripts/to_trainable.py relabeled_20260827.jsonl -o relabeled_20260827.trainable.jsonl
```
