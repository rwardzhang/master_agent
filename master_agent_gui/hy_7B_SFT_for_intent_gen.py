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
def get_origin_file(file_name, column_names, sample=False) -> List[Dict]:
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


intent_class_map = {'coffee': 'coffee',
                    'unknown': 'unknown',
                    'milk_tea':'milk_tea',
                    'burger':'burger'
                    }
class_intent_map = {value: key for key, value in intent_class_map.items()}


def get_intent_prompt1(query) -> str:
    system_prompt = '''你是一个专业的多智能体意图分类助手，你的核心功能是通过自然语言处理精准识别用户意图是以下哪种意图种类：
    
    {
      "agent_name": "coffee",
      "description": "你是一个专业的点单助手，支持完整的点单流程，仅支持帮助用户购买咖啡如：瑞幸咖啡等"
    }，
    {
      "agent_name": "milk_tea",
      "description": "你是一个专业的奶茶点单助手，支持完整的点单流程，仅支持帮助用户购买奶茶如：奶茶,购买奶茶等"
    }，
    {
      "agent_name": "burger",
      "description": "你是一个专业的汉堡点单助手，支持完整的点单流程，仅支持帮助用户购买汉堡如：汉堡,购买汉堡等"
    },
    {
      "agent_name": "unknown",
      "description": "当用户的输入不属于上述任何一类时，输出此类别。包括但不限于：闲聊、问候、无关话题、模糊表达等"
    }
    
    要求：  
        - 输出必须是上述agent_name之一，不得添加解释、标点或换行  
        - 若用户请求涉及多个意图，选择最核心或最先提及的意图  
        - 只用输出一个符合要求的类别名称  
        - 若无法明确归类到这几类，则输出"unknown" 
  '''
    # return system_prompt + "\n【用户问题】:" + query
    return system_prompt


# from,query,intent,entity,history
def get_sft_data(file_path, file_name, column_names, save_name, sample=False, prompt_type=1):
    origin_info_dict_list = get_origin_file(os.path.join(file_path, file_name), column_names, sample=sample)
    save_list = []
    skipped_count = 0

    for info_dict in origin_info_dict_list:
        query = info_dict['query']
        intent = info_dict['intent']
        # entity = info_dict['entity']
        history = info_dict.get('history', [])

        # history已经在get_origin_file中处理过了，这里直接使用
        if not isinstance(history, list):
            history = []

        # 跳过空的intent或不在映射表中的intent
        if not intent or intent not in intent_class_map:
            skipped_count += 1
            continue

        sys_prompt = get_intent_prompt1(query)

        # json_line = {"instruction":"识别语句的意图","system":sys_prompt,"input":query, "output":intent_class_map[intent],"history":[]}
        for v in intent_class_map.values():
            if v != intent_class_map[intent]:
                # 处理history格式：
                # - 0轮：[]
                # - 1轮：[["用户输入", "助手回复"]]
                # - 2轮及以上：[["用户1", "回复1"], ["用户2", "回复2"]]
                formatted_history = []
                if history and isinstance(history, list):
                    # 过滤掉空值
                    history_items = [str(item).strip() for item in history if item and str(item).strip()]

                    if len(history_items) == 0:
                        # 0轮历史
                        formatted_history = []
                    elif len(history_items) >= 2:
                        # 1轮及以上：统一转换为二维数组
                        # 每两个元素组成一轮对话 [用户输入, 助手回复]
                        formatted_history = []
                        for i in range(0, len(history_items) - 1, 2):
                            if i + 1 < len(history_items):
                                formatted_history.append([history_items[i], history_items[i + 1]])
                    else:
                        # 如果只有1个元素，视为无效历史
                        formatted_history = []

                json_line = {"instruction": "识别语句的意图", "system": sys_prompt, "input": query,
                             "output": intent_class_map[intent], "rejected": v, "history": formatted_history}
                # 将单个对象包装在数组中
                json_array = [json_line]
                save_list.append(json_array[0])
    print("total cnt of data is :", len(save_list))
    with open(os.path.join(file_path, save_name), 'w', encoding='utf-8') as file:
        for item in save_list:
            file.write(json.dumps(item, ensure_ascii=False) + '\n')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Config Arguments', allow_abbrev=False)
    group = parser.add_argument_group(title='data args')
    parser.add_argument('--task_type', type=str, default='data', help='file_dir of the data')
    # parser.add_argument('--task_type',type=str,default='eval',help='file_dir of the data')
    args = parser.parse_args()

    file_path = './'
    column_names = ['from', 'query', 'intent', 'entity', 'history']

    prompt_type = 1
    train_name = 'intent_train_v1.csv'
    train_save_name = 'intent_train_v1_hy_gen_category519.jsonl'

    if args.task_type == 'data':
        print(
            "-----------------------------------------------process data-----------------------------------------------------------------------")
        get_sft_data(file_path, train_name, column_names, train_save_name, sample=False, prompt_type=prompt_type)