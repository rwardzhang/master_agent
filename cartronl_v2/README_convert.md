# Excel到JSONL格式转换脚本

## 功能说明

本脚本用于将 `car_control.xlsx` 文件转换为 `nlu_v6.jsonl` 格式的训练数据。

## 文件说明

- **输入文件**: `car_control.xlsx`
  - 包含4列：`Domain`, `Intent`, `示例意图语料`, `完整的执行指令 (JSON)`
  - 共14006行数据

- **输出文件**: `car_control_converted.jsonl`
  - JSONL格式（每行一个JSON对象）
  - 每个JSON对象包含两个字段：
    - `input`: 包含角色描述、输出要求示例和用户query
    - `output`: JSON数组格式的车控指令

## 使用方法

### 1. 确保安装依赖

```bash
pip install pandas openpyxl
```

### 2. 运行转换脚本

```bash
python3 convert_excel_to_jsonl.py
```

### 3. 查看转换结果

转换完成后，会在同目录下生成 `car_control_converted.jsonl` 文件。

## 输出格式示例

```json
{
  "input": "# 角色\n你是一个专业的座舱车控助手...\n注意：输入的query是：氛围灯换个颜色",
  "output": "[{\"domain\": \"car_control\", \"intent\": \"atlights_control\", \"slots\": {}}]"
}
```

## 转换统计

- 原始Excel数据：14006行
- 成功转换：14006条
- 转换成功率：100%

## 注意事项

1. 脚本会自动将单个JSON对象包装成数组格式，以符合nlu_v6.jsonl的格式要求
2. 输出文件使用UTF-8编码，确保中文字符正确显示
3. 每行JSON数据都经过格式验证，确保可以正常解析
