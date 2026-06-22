import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:100"
import json
import argparse
import pandas as pd
from typing import List, Dict
import random
import ast
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # 或者 "true
try:
    import transformers
    transformers.logging.set_verbosity_error()
except ImportError:
    pass

#####################get data########################################################################################################
def get_origin_file(file_name, column_names, sample = False) -> List[Dict]:
  # 读取CSV文件
  result_list = []
  df = pd.read_csv(file_name)
  if sample:
    df = df.sample(n=50, replace=False)
  
  # 获取CSV文件中实际存在的列
  csv_columns = df.columns.tolist()
  
  # 按行遍历数据
  for index, row in df.iterrows():
    result = {}
    for name in column_names:
      if name == 'history':
        # 特殊处理history字段，确保格式为数组
        # 检查CSV中是否存在history列
        if 'history' not in csv_columns:
          # 如果CSV中没有history列，设置为空数组
          result[name] = []
        else:
          history_str = str(row[name]).replace('nan', '')
          history = []
          if history_str and history_str.strip():
            try:
              # 尝试解析字符串形式的列表
              parsed_history = ast.literal_eval(history_str)
              if isinstance(parsed_history, list):
                # 确保每个元素都是字符串格式，并按换行符进一步分割
                history = []
                for item in parsed_history:
                  if item is not None:
                    item_str = str(item)
                    # 按换行符分割每个元素
                    if '\\n' in item_str:
                      history.extend([h.strip() for h in item_str.split('\\n') if h.strip()])
                    else:
                      history.append(item_str)
              else:
                history = []
            except:
              # 如果解析失败，尝试按分隔符分割
              if '|' in history_str:
                history = []
                for h in history_str.split('|'):
                  h = h.strip()
                  if h:
                    # 按换行符进一步分割
                    if '\\n' in h:
                      history.extend([sub_h.strip() for sub_h in h.split('\\n') if sub_h.strip()])
                    else:
                      history.append(h)
              elif '\\n' in history_str:
                # 按换行符分割
                history = [str(h.strip()) for h in history_str.split('\\n') if h.strip()]
              else:
                # 如果没有分隔符，将整个字符串作为一个历史条目
                history = [str(history_str.strip())]
          result[name] = history
      else:
        # 检查列是否存在
        if name in csv_columns:
          result[name] = str(row[name]).replace('nan', '')
        else:
          result[name] = ''
    result_list.append(result)
  return result_list


intent_class_map = {'order':'order',
                    'chat':'chat',
                    'news':'news',
                    'music':'music',
                    'food':'food',
                    'car_control':'car_control',
                    'travel_plan':'travel_plan',
                    'podcast':'podcast',
                    'wmpf_miniprogram_agent':'wmpf_miniprogram_agent'
                    }
class_intent_map = {value: key for key, value in intent_class_map.items()}


def get_intent_prompt1(query) -> str:
  system_prompt = '''你是一个车载智能助手，负责准确识别用户语音指令的真实意图。  
请从以下9个类别中选择最匹配的一项或多项：  
wmpf_miniprogram_agent（小程序，短剧，视频，有声书，应用，会议日程，订票取号）、order（点咖啡）、news（新闻）、music（音乐）、food（美食推荐）、car_control（车控）、podcast（生成播客，生成博客）、travel_plan（出行规划）、chat（闲聊）  
要求：  
- [
          {"query": "子意图1的文本", "intent": "子意图1的类别"},
          {"query": "子意图2的文本", "intent": "子意图2的类别"}（选填）
      ]
  示例1:
  输入：打开空调然后再帮我打开哔哩哔哩
  输出：[{"query": "打开空调", "intent": "car_control"}, {"query": "帮我打开哔哩哔哩", "intent": "wmpf_miniprogram_agent"}]
  示例2:
  输入：帮我打开哔哩哔哩
  输出：[{"query": "帮我打开哔哩哔哩", "intent": "wmpf_miniprogram_agent"}]
'''
  # return system_prompt + "\\n【用户问题】::\" + query
  return system_prompt



#from,query,intent,entity,history
def get_sft_data(file_path, file_name, column_names, save_name, sample = False, prompt_type=1):
  origin_info_dict_list = get_origin_file(os.path.join(file_path, file_name), column_names, sample=sample)
  save_list = []
  skipped_count = 0

  for info_dict in origin_info_dict_list:
    query = info_dict['query']
    intent_raw = info_dict['intent']
    # entity = info_dict['entity']
    history = info_dict.get('history', [])
    
    # history已经在get_origin_file中处理过了，这里直接使用
    if not isinstance(history, list):
      history = []
    
    if not intent_raw:
      skipped_count += 1
      continue
    
    # 检查是否为数组格式的intent
    intent_str = str(intent_raw).strip()
    is_array_intent = False
    intent_output = None
    
    if intent_str.startswith('[') and intent_str.endswith(']'):
      try:
        # 修复缺少逗号的情况
        intent_str_fixed = intent_str.replace('" "', '", "').replace('} {', '}, {')
        # 尝试解析为JSON数组
        intent_array = json.loads(intent_str_fixed)
        if isinstance(intent_array, list) and len(intent_array) > 0:
          # 验证数组中至少有一个有效的intent
          has_valid_intent = False
          for item in intent_array:
            if isinstance(item, dict) and 'intent' in item:
              intent_val = item['intent'].strip()
              if intent_val in intent_class_map:
                has_valid_intent = True
                break
          
          if has_valid_intent:
            # 保留完整的数组格式作为output（重新序列化以确保格式正确）
            is_array_intent = True
            intent_output = json.dumps(intent_array, ensure_ascii=False)
      except Exception as e:
        # 如果解析失败，跳过这条数据
        print(f"警告：无法解析intent数组: {intent_str[:100]}, 错误: {e}")
        skipped_count += 1
        continue
    else:
      # 单一intent格式
      if intent_raw in intent_class_map:
        intent_output = intent_class_map[intent_raw]
      else:
        skipped_count += 1
        continue
    
    # 如果没有有效的intent，跳过
    if intent_output is None:
      skipped_count += 1
      continue

    sys_prompt = get_intent_prompt1(query)

    # 生成训练数据
    if is_array_intent:
      # 对于数组格式的intent，提取output中已有的intent类型
      used_intents = set()
      try:
        intent_array = json.loads(intent_output)
        for item in intent_array:
          if isinstance(item, dict) and 'intent' in item:
            intent_val = item['intent'].strip()
            if intent_val in intent_class_map:
              used_intents.add(intent_class_map[intent_val])
      except:
        pass
      
      # 生成rejected样本，排除已使用的intent类型
      for v in intent_class_map.values():
        if v not in used_intents:
          # 处理history格式
          formatted_history = []
          if history and isinstance(history, list):
            history_items = [str(item).strip() for item in history if item and str(item).strip()]
            if len(history_items) >= 2:
              for i in range(0, len(history_items) - 1, 2):
                if i + 1 < len(history_items):
                  formatted_history.append([history_items[i], history_items[i + 1]])
          
          json_line = {"instruction":"识别语句的意图","system":sys_prompt,"input":query, "output":intent_output,"rejected":v,"history":formatted_history}
          save_list.append(json_line)
    else:
      # 对于单一intent格式，为每个其他intent生成rejected样本
      for v in intent_class_map.values():
        if v != intent_output:
          # 处理history格式
          formatted_history = []
          if history and isinstance(history, list):
            history_items = [str(item).strip() for item in history if item and str(item).strip()]
            if len(history_items) >= 2:
              for i in range(0, len(history_items) - 1, 2):
                if i + 1 < len(history_items):
                  formatted_history.append([history_items[i], history_items[i + 1]])
          
          json_line = {"instruction":"识别语句的意图","system":sys_prompt,"input":query, "output":intent_output,"rejected":v,"history":formatted_history}
          save_list.append(json_line)
  
  print("total cnt of data is :", len(save_list))
  print("skipped cnt of data is :", skipped_count)
  with open(os.path.join(file_path, save_name), 'w', encoding='utf-8') as file:
    file.write('[\n')
    for i, item in enumerate(save_list):
      file.write(json.dumps(item, ensure_ascii=False))
      if i < len(save_list) - 1:
        file.write(',\n')
      else:
        file.write('\n')
    file.write(']')



if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Config Arguments',allow_abbrev=False)
  group = parser.add_argument_group(title='data args')
  parser.add_argument('--task_type',type=str,default='data',help='file_dir of the data')
  # parser.add_argument('--task_type',type=str,default='eval',help='file_dir of the data')
  args = parser.parse_args()

  file_path='./'
  column_names = ['from','query','intent','entity','history']

  prompt_type = 1
  train_name = 'intent_train_v1.csv'
  train_save_name = 'intent_train_v1_hy_gen.jsonl'
  test_name = 'intent_test_v1.csv'
  test_save_name = 'intent_test_v1_hy_gen.jsonl'

  if args.task_type == 'data':
    print("-----------------------------------------------process data-----------------------------------------------------------------------")
    get_sft_data(file_path, train_name, column_names, train_save_name, sample = False, prompt_type=prompt_type)
    get_sft_data(file_path, test_name, column_names, test_save_name, sample = False, prompt_type=prompt_type)
