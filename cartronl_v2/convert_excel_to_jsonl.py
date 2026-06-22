#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
将car_control.xlsx文件转换为nlu_v6.jsonl格式的脚本
"""

import pandas as pd
import json
import os

# 定义角色和输出要求的模板
PROMPT_TEMPLATE = """# 角色
你是一个专业的座舱车控助手，能够根据用户的输入，输出对应的车控指令，支持简单意图识别、场景识别和连续指令识别。


# 输出要求：严格按照Json格式输出
1.简单意图别示例：
输入：打开三排左空调除霜模式
输出：[{{"domain": "car_control", "intent": "ac_control", "slots": {{"ac_mode": "除霜模式", "ac_area": "三排左"}}}}]

2.场景识别示例：
输入：好想睡
输出：[{{"domain":"car_control","intent":"seat_position_control","slots":{{"seat_position":"全部","seat_area":"靠背","seat_adjustment_action":"向后"}}}},{{"domain":"car_control","intent":"car_window_control","slots":{{"window_position":"全部","window_action_percent":"0"}}}},{{"domain":"car_control","intent":"ac_control","slots":{{"ac_mode":"外循环","ac_area":"全部"}}}},{{"domain":"car_control","intent":"sound_channel_off","slots":{{"sound_channel":"音乐"}}}}]

3.连续指令识别：
输入：关闭车窗打开座椅加热打开座椅按摩打开空调温度调至28度
输出：[{{"domain":"car_control","intent":"car_window_control","slots":{{"window_position":"全部","window_action_percent":"0"}}}},{{"domain":"car_control","intent":"seat_heating_control","slots":{{"action":"打开","seat_heating_mode":"适中","seat_position":"全部"}}}},{{"domain":"car_control","intent":"seat_massage_control","slots":{{"action":"打开","sa_area":"全部"}}}},{{"domain":"car_control","intent":"ac_control","slots":{{"ac_temperature_number":"28"}}}}] 
注意：输入的query是：{query}"""


def read_excel_file(excel_path):
    """
    读取Excel文件
    
    Args:
        excel_path: Excel文件路径
        
    Returns:
        DataFrame对象
    """
    print(f"正在读取Excel文件: {excel_path}")
    
    # 尝试读取Excel文件，可能有多个sheet
    try:
        # 先尝试读取第一个sheet
        df = pd.read_excel(excel_path, sheet_name=0)
        print(f"成功读取Excel文件，共 {len(df)} 行数据")
        print(f"列名: {df.columns.tolist()}")
        return df
    except Exception as e:
        print(f"读取Excel文件失败: {e}")
        return None


def convert_to_jsonl_format(df, output_path):
    """
    将DataFrame转换为JSON数组格式
    
    Args:
        df: pandas DataFrame对象
        output_path: 输出文件路径
    """
    print(f"\n开始转换数据...")
    
    # 打印前几行数据以便检查
    print("\n前5行数据预览:")
    print(df.head())
    
    # 根据实际的列名进行调整，这里假设有'query'和'output'列
    # 如果列名不同，需要根据实际情况修改
    
    converted_count = 0
    result_array = []  # 用于存储所有的JSON对象
    
    for idx, row in df.iterrows():
        try:
            # 假设Excel中有query和output两列
            # 需要根据实际的Excel结构调整列名
            
            # 尝试不同的可能列名
            query = None
            output = None
            
            # 查找query列
            for col in ['示例意图语料', 'query', 'Query', 'QUERY', '问题', '输入', 'input', 'text']:
                if col in df.columns:
                    query = row[col]
                    break
            
            # 查找output列
            for col in ['完整的执行指令 (JSON)', 'output', 'Output', 'OUTPUT', '输出', '结果', 'result', 'label']:
                if col in df.columns:
                    output = row[col]
                    break
            
            if query is None or output is None or pd.isna(query) or pd.isna(output):
                continue
            
            # 构建input字段
            input_text = PROMPT_TEMPLATE.format(query=str(query).strip())
            
            # 处理output字段
            # 如果output已经是JSON字符串，直接使用；否则需要解析
            if isinstance(output, str):
                # 尝试解析JSON
                try:
                    output_obj = json.loads(output)
                    # 如果output_obj不是列表，将其包装成列表
                    if not isinstance(output_obj, list):
                        output_obj = [output_obj]
                    output_str = json.dumps(output_obj, ensure_ascii=False)
                except:
                    # 如果不是有效的JSON，直接使用原字符串
                    output_str = output
            else:
                output_str = str(output)
            
            # 构建最终的JSON对象，按照新的格式要求
            json_obj = {
                "instruction": "",
                "input": input_text,
                "system": "",
                "output": output_str,
                "history": []
            }
            
            # 添加到结果数组
            result_array.append(json_obj)
            converted_count += 1
            
        except Exception as e:
            print(f"处理第 {idx} 行时出错: {e}")
            continue
    
    # 将整个数组写入文件
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result_array, f, ensure_ascii=False, indent=4)
    
    print(f"\n转换完成！共转换 {converted_count} 条数据")
    print(f"输出文件: {output_path}")


def main():
    """主函数"""
    # 文件路径
    excel_path = "/Users/rwardzhang/PycharmProjects/master_agent_qc/cartronl_v2/car_control.xlsx"
    output_path = "/Users/rwardzhang/PycharmProjects/master_agent_qc/cartronl_v2/car_control_converted.jsonl"
    
    # 检查Excel文件是否存在
    if not os.path.exists(excel_path):
        print(f"错误：Excel文件不存在: {excel_path}")
        return
    
    # 读取Excel文件
    df = read_excel_file(excel_path)
    
    if df is None:
        print("读取Excel文件失败，程序退出")
        return
    
    # 转换为jsonl格式
    convert_to_jsonl_format(df, output_path)


if __name__ == "__main__":
    main()
