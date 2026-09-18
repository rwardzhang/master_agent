# 每日日志审计与回标工作流

本文定义 `wecar-fc-tool-labeler` 处理**每天日志数据 → 错误数据识别 → 合理裁决 → 仅基于错误数据生成新训练数据**的标准流程。

## 一、适用输入

适用场景：
- 用户给一份当天/某天的线上日志导出文件（通常是 CLS 导出的 `.json` / `.jsonl`）
- 日志中包含 `tool_select messages: ... -> raw='...'` 这类记录
- 用户希望基于 `工具职能说明.md` 找出错误数据，并回标成新的训练样本

## 二、标准交付物

一次完整工作最终只交付 2 类文件：

1. **错误数据明细**
   - 只保留 `verdict=错误` 的样本
   - 推荐 CSV 或 JSONL，至少包含：
     - `case_id`
     - `query`
     - `上下文历史消息`
     - `original_answer`
     - `corrected_answer`
     - `reason`

2. **新的训练数据**
   - 只基于错误数据中的 `corrected_answer / final_train_answer` 生成新的 JSONL
   - 再转为可训练格式（顶层仅 `messages`）

说明：
- `extract_tool_select_logs.py` 产出的抽取结果属于内部中间件，不作为最终交付物
- `reviewed.csv` 属于内部回标控制表，不作为最终面向用户的主产物

## 三、逐条裁决口径

### 1. `verdict` 只用三类

- `正确`
- `错误`
- `可接受但建议优化`

### 2. 三类 verdict 的处理方式

#### `正确`
- 日志原答案与规则一致
- 可以记录在内部 reviewed.csv 中
- **不进入最终交付给用户的错误数据明细**
- 默认 `use_for_training = no`

#### `错误`
- 工具选择、参数提取、上下文继承、边界判断等存在明显问题
- `final_train_answer` 改成最终裁决结果
- **进入最终交付给用户的错误数据明细**
- 若可直接入训，则 `use_for_training = yes`

#### `可接受但建议优化`
- 仅作为内部审计参考
- 默认不进入最终交付物
- 默认 `use_for_training = no`
- 只有用户明确要求“把可优化样本也回灌训练”时，才单独放开

## 四、哪些 case 不进训练

以下情况默认 `use_for_training = no`：

1. **`verdict != 错误`**
   - `正确` 与 `可接受但建议优化` 默认不进入这条工作流的最终训练数据

2. **需继续澄清**
   - 当前上下文不足，无法唯一判断目标对象
   - 例如候选 POI 不唯一、列表序号缺失、指代未解开

3. **schema 无法表达**
   - 当前工具 schema 装不下判定结果
   - 例如中间结构信息缺失且无法合理压缩

4. **原日志本身不完整**
   - `messages` 缺失、role 序列异常、assistant 空字符串、think 泄漏

5. **仍存在人工分歧**
   - 即使查完 `工具职能说明.md` 与训练先例，仍无法形成唯一裁决

## 五、训练答案的生成原则

### 1. 永远不改 `user`
- `user` 必须保留原始日志中的真实输入与上下文
- 只允许改 `assistant`

### 2. `final_train_answer` 优先级高于 `md_answer`
- `md_answer` 是按规则推导出的标准答案
- `final_train_answer` 是最终用于训练的答案
- 大多数情况下两者相同；只有“日志可接受但训练应更规范”时才不同

### 3. 训练目标追求稳定，不追求保留线上噪声
可以在**不篡改 user 的前提下**对 assistant 做规范化：
- 补全更稳定的检索词
- 统一枚举值
- 修正可表达的参数位
- 统一 `unknown|-`

## 六、推荐的审计与回标流程

### Step 1：先抽日志
运行：

```bash
python3 ~/.workbuddy/skills/wecar-fc-tool-labeler/scripts/extract_tool_select_logs.py raw_export.json -o extracted_cases.jsonl --csv extracted_cases.csv
```

### Step 2：逐条对照 `工具职能说明.md`
- 先定域
- 再查上下文承接
- 再判断工具边界
- 最后核参数提取

### Step 3：只产出错误数据明细
建议内部审计表至少有这些列：

```text
case_id,verdict,original_answer,md_answer,final_train_answer,use_for_training,reason
```

但最终对用户只交付 `verdict=错误` 的子集，推荐列为：

```text
case_id,query,context,original_answer,corrected_answer,reason
```

其中：
- `corrected_answer` 可直接等于 `final_train_answer`
- `use_for_training` 仅对错误样本标 `yes/no`

### Step 4：只基于错误样本生成回标训练数据
运行：

```bash
python3 ~/.workbuddy/skills/wecar-fc-tool-labeler/scripts/build_relabel_train.py \
  extracted_cases.jsonl \
  reviewed.csv \
  -o relabeled_from_errors.jsonl \
  --verdict-only 错误
```

### Step 5：过质量门禁并转可训练格式
```bash
python3 ~/.workbuddy/skills/wecar-fc-tool-labeler/scripts/audit_labels.py relabeled_from_errors.jsonl --csv relabeled_errors.csv
python3 ~/.workbuddy/skills/wecar-fc-tool-labeler/scripts/to_trainable.py relabeled_from_errors.jsonl -o relabeled_from_errors.trainable.jsonl
```

## 七、推荐的 reviewed.csv 列定义

```csv
case_id,verdict,original_answer,md_answer,final_train_answer,use_for_training,reason
1,正确,navigation|深圳北站|-,navigation|深圳北站|-,navigation|深圳北站|-,no,原答案与规则一致，不进入本工作流最终产物
2,错误,unknown|-,web_search|-,web_search|-,yes,日期查询在信息查询域应走 web_search
3,可接受但建议优化,search_place|好玩的|上海市,search_place|好玩的地方|上海市,search_place|好玩的地方|上海市,no,仅内部参考，不进入最终错误样本集
4,错误,navigation|某地|-,【需澄清】,,no,候选目的地不唯一，不能直接入训练
```

## 八、输出判断规则总结

- **最终只交付两类产物**：`错误数据明细` + `基于错误数据生成的新训练数据`
- **正确 / 可接受但建议优化**：可以保留在内部 reviewed.csv，但不作为最终主交付物
- **错误数据明细**：回答“哪些日志是错的、应改成什么、为什么”
- **训练数据结果**：回答“这些错误样本最终拿什么答案去训练”
