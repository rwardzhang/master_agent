import os
import random
import json
import re
import pandas as pd
from sklearn.model_selection import train_test_split


def get_origin_file(file_name, sheet_name, sample_cnt = 0):
  # 读取Excel文件的单个sheet
  df = pd.read_excel(file_name, sheet_name=sheet_name, engine='openpyxl')


  origin_dict = {}
  has_history = 'history' in df.columns  # 检查是否有history列
  
  for index, row in df.iterrows():
    f = str(row['from']).replace('nan', '')
    # 如果from为空，填充默认值
    if not f or f.strip() == '':
      f = 'user'  # 可以根据需要修改默认值
    
    q = str(row['query']).replace('nan', '')
    intent = str(row['intent']).replace('nan', '')
    entity = str(row['entity']).replace('nan', '')
    
    # 如果有history列，也读取它
    if has_history:
      history = str(row['history']).replace('nan', '')
      if intent in origin_dict:
        origin_dict[intent].append((f, q, entity, history))
      else:
        origin_dict[intent] = [(f, q, entity, history)]
    else:
      if intent in origin_dict:
        origin_dict[intent].append((f, q, entity))
      else:
        origin_dict[intent] = [(f, q, entity)]

  processed_list = []
  for intent, v_list in origin_dict.items():
    random.shuffle(v_list)
    if sample_cnt<len(v_list):
      sample_v_list = random.sample(v_list, sample_cnt)
    else:
      sample_v_list = v_list
    print(intent, len(v_list), len(sample_v_list))

    for item in sample_v_list:
      temp_dict = {}
      if has_history:
        f, q, e, h = item
        temp_dict['from'] = f
        temp_dict['query'] = q
        temp_dict['intent'] = intent
        temp_dict['entity'] = e
        # 将history转换为数组格式的字符串
        if h and h.strip():
          # 使用换行符\n作为分隔符来分割历史对话
          history_list = [item.strip() for item in h.split('\n') if item.strip()]
          temp_dict['history'] = str(history_list)
        else:
          temp_dict['history'] = '[]'
      else:
        f, q, e = item
        temp_dict['from'] = f
        temp_dict['query'] = q
        temp_dict['intent'] = intent
        temp_dict['entity'] = e
      processed_list.append(temp_dict)
      
  random.shuffle(processed_list)
  random.shuffle(processed_list)
  print('processed_list:', len(processed_list))

  processed_df = pd.DataFrame(processed_list)
  print(processed_df.head(5))
  grouped = processed_df.groupby('intent').size()
  print(grouped)

  return processed_df


def get_array_intent_file(file_name, sheet_name, sample_cnt=0):
  """处理数组格式intent的sheet，转换为标准DataFrame格式"""
  df = pd.read_excel(file_name, sheet_name=sheet_name, engine='openpyxl')
  
  processed_list = []
  
  for index, row in df.iterrows():
    try:
      # 获取query字段
      query = str(row['query']).replace('nan', '').strip() if 'query' in df.columns else ''
      intent_str = str(row['intent']).replace('nan', '').strip()
      
      if not query or not intent_str:
        continue
      
      # 尝试解析intent为数组
      try:
        # 处理转义的引号
        intent_str_fixed = intent_str.replace('\\"', '"')
        # 修复缺少逗号的情况：在 " " 之间添加逗号（值后面跟着键）
        intent_str_fixed = intent_str_fixed.replace('" "', '", "')
        # 修复 } 和 { 之间缺少逗号的情况
        intent_str_fixed = intent_str_fixed.replace('} {', '}, {')
        intent_array = json.loads(intent_str_fixed)
        if not isinstance(intent_array, list) or len(intent_array) == 0:
          continue
        # 保留原始的数组格式作为intent
        intent_output = intent_str_fixed
      except Exception as parse_err:
        print(f"警告：无法解析intent为数组: {intent_str}, 错误: {parse_err}")
        continue
      
      # 获取其他字段
      f = str(row.get('from', '')).replace('nan', '').strip() if 'from' in df.columns else 'user'
      entity = str(row.get('entity', '')).replace('nan', '').strip() if 'entity' in df.columns else ''
      
      # 构建与其他sheet一致的格式
      temp_dict = {
        'from': f if f else 'user',
        'query': query,
        'intent': intent_output,
        'entity': entity
      }
      
      processed_list.append(temp_dict)
    except Exception as e:
      print(f"处理行 {index} 时出错: {e}")
      continue
  
  # 采样
  if sample_cnt > 0 and sample_cnt < len(processed_list):
    processed_list = random.sample(processed_list, sample_cnt)
  
  random.shuffle(processed_list)
  print(f'数组意图数据处理完成: {len(processed_list)} 条')
  
  # 转换为DataFrame
  complex_df = pd.DataFrame(processed_list)
  return complex_df


def train_and_test(df, test_size, file_path, train_name, test_name):
  train_df, test_df = train_test_split(df, test_size=test_size, random_state=42)
  print('train_df', len(train_df))
  grouped = train_df.groupby('intent').size()
  print(grouped)

  print('test_df', len(test_df))
  grouped = test_df.groupby('intent').size()
  print(grouped)

  train_df.to_csv(os.path.join(file_path,train_name), index=False)
  test_df.to_csv(os.path.join(file_path,test_name), index=False)



if __name__ == "__main__":

  file_path='./'
  file_name = '../master_agent_trainv2/master_agent_5.xlsx'
  
  # 获取Excel文件中的所有sheet名称
  excel_file = pd.ExcelFile(os.path.join(file_path, file_name), engine='openpyxl')
  all_sheet_names = excel_file.sheet_names
  
  print("=" * 80)
  print(f"发现 {len(all_sheet_names)} 个sheet: {all_sheet_names}")
  print("=" * 80)
  
  # 存储所有sheet的DataFrame
  all_dfs = []
  
  # 遍历处理所有sheet
  for idx, sheet_name in enumerate(all_sheet_names, 1):
    print("\n" + "=" * 80)
    print(f"处理第 {idx} 个sheet: {sheet_name}")
    print("=" * 80)
    try:
      # 检查是否为数组格式intent的sheet
      if sheet_name == '复杂意图训练':
        df = get_array_intent_file(os.path.join(file_path, file_name), sheet_name, sample_cnt=6000)
        all_dfs.append(df)
        print(f"成功处理sheet '{sheet_name}', 数据量: {len(df)}")
      else:
        df = get_origin_file(os.path.join(file_path, file_name), sheet_name, sample_cnt=6000)
        all_dfs.append(df)
        print(f"成功处理sheet '{sheet_name}', 数据量: {len(df)}")
    except Exception as e:
      print(f"处理sheet '{sheet_name}' 时出错: {e}")
      print(f"跳过该sheet，继续处理下一个")
      continue
  
  # 合并所有DataFrame
  if len(all_dfs) > 0:
    print("\n" + "=" * 80)
    print(f"合并所有 {len(all_dfs)} 个sheet的数据")
    print("=" * 80)
    combined_df = pd.concat(all_dfs, ignore_index=True)
    print(f"合并后总数据量: {len(combined_df)}")
    print(combined_df.head(10))
    
    # 生成训练和测试文件
    train_name = 'intent_train_v1.csv'
    test_name = 'intent_test_v1.csv'
    train_and_test(combined_df, 0.1, file_path, train_name, test_name)
  else:
    print("\n" + "=" * 80)
    print("错误：没有成功处理任何sheet")
    print("=" * 80)
