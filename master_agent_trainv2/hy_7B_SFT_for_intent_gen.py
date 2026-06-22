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


intent_class_map = {'chat':'chat',
                    'news':'news',
                    'music':'music',
                    'food':'food',
                    'luckin':'luckin',
                    'car_control':'car_control',
                    'travel_plan':'travel_plan',
                    'podcast':'podcast',
                    'miniprogram':'miniprogram',
                    'video':'video',
                    'meituan':'meituan',
                    'puscene':'puscene',
                    'maoyan':'maoyan',
                    'tc_travel':'tc_travel',
                    'sights':'sights',
                    'starbucks':'starbucks',
                    'health':'health'
                    }
class_intent_map = {value: key for key, value in intent_class_map.items()}


def get_intent_prompt1(query) -> str:
  system_prompt = '''你是一个车载智能助手，负责准确识别用户语音指令的真实意图。请从以下类别中选择最匹配的一项：[
    {
      "agent_name": "luckin",
      "description": "你是一个专业的瑞幸点单助手，支持完整的点单流程，如：瑞幸咖啡"
    },
    {
      "agent_name": "chat",
      "description": "你是一个闲聊助手，不支持任何车辆控制功能，支持闲聊和天气查询，旅游规划和推荐，运动生活，人物介绍，网站查询，实时消息查询等."
    },
    {
      "agent_name": "news",
      "description": "你是一个专业的新闻资讯助手，提供热点、分类、地区、健康等多维度新闻服务，支持早晚报获取和个性化推荐。"
    },
    {
      "agent_name": "music",
      "description": "你是一个专业的音乐助手，具备强大的音乐搜索、推荐、问答、播放能力。你的核心功能是通过自然语言处理精准识别用户的音乐相关需求，不处理QQ音乐相关的需求。"
    },
    {
      "agent_name": "food",
      "description": "你是一个美食推荐助手，负责执行美食搜索、餐厅推荐、美食推荐相关指令"
    },
    {
      "agent_name": "car_control",
      "description": "你是一个车载控制助手，负责执行空调、车窗、座椅、多媒体等车辆功能指令"
    },
    {
      "agent_name": "podcast",
      "description": "你是一个专业的播客生成助手，具备强大的播客生成能力。你的核心功能是通过自然语言处理精准识别用户的播客需求"
    },
    {
      "agent_name": "miniprogram",
      "description": "微信小程序分发助手，支持在小程序中帮助用户：查询机票|航站楼|登机口|出发时间等信息、查询股票、小红书搜索、大众点评搜索、短剧、视频、有声书、游戏、购票、日程会议、订购机票车票等各种内容"
    },
    {
      "agent_name": "travel_plan",
      "description": "你是一个非常善于进行旅游规划、出游推荐、地图导航的AI助手，输入示例：规划武汉一日游、春天有什么好玩的去处、导航去东湖绿道、导航去第一个"
    },
    {
      "agent_name": "video",
      "description": "你是一个专业的视频智能助手，能够根据用户需求提供视频推荐、影视搜索、短剧搜索、视频问答等服务"
    },
    {
      "agent_name": "meituan",
      "description": "你是一个专业的美团点单助手，支持完整的点单流程，支持在美团小程序内的一切点单流程 如：外卖点餐、商超配送、买药、奶茶外送"
    },
    {
      "agent_name": "puscene",
      "description": "你是资深的取号订座助手，帮助用户通过语音完成取号订座"
    },
    {
      "agent_name": "maoyan",
      "description": "你是一个专业的电影助手，在猫眼电影小程序，能够根据用户需求帮助用户购买电影票，明确购买意图，如：我要买电影票"
    },
    {
      "agent_name": "tc_travel",
      "description": "你是一个专业的同程旅酒店预订助手，能够根据用户需求打开同程小程序帮助用户预定酒店、飞机票、火车票、购买景点门票等"
    },
    {
      "agent_name": "sights",
      "description": "你是一个专业的景点助手，能够根据用户需求提供景点推荐服务"
    },
    {
      "agent_name": "starbucks",
      "description": "你是一个专业的星巴克点单助手，支持完整的点单流程，如：星巴克、星咖啡、星冰乐"
    },
    {
      "agent_name": "health",
      "description": "你是一位专业的日常健康科普问答助手，你可以根据客户提问的问题，查询腾讯医典，并根据已知内容给出专业的回复。"
    }
  ]
      要求：  
          - 输出必须是上述类别agent_name之一，不得添加解释、标点或换行  
          - 若用户请求涉及多个意图，选择最核心或最先提及的意图  
          - 只用输出一个符合要求的类别名称  
          - 若无法明确归类到这几类，则输出"chat"
  '''
  # return system_prompt + "\n【用户问题】:" + query
  return system_prompt

#from,query,intent,entity,history
def get_sft_data(file_path, file_name, column_names, save_name, sample = False, prompt_type=1):
  origin_info_dict_list = get_origin_file(os.path.join(file_path, file_name), column_names, sample=sample)
  save_list = []
  skipped_count = 0

  for info_dict in origin_info_dict_list:
    query = info_dict['query']
    intent= info_dict['intent']
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
    for v in intent_class_map.values() :
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

        json_line = {"instruction":"识别语句的意图","system":sys_prompt,"input":query, "output":intent_class_map[intent],"rejected":v,"history":formatted_history}
        # 将单个对象包装在数组中
        json_array = [json_line]
        save_list.append(json_array[0])
  print("total cnt of data is :", len(save_list))
  with open(os.path.join(file_path, save_name), 'w', encoding='utf-8') as file:
    for item in save_list:
      file.write(json.dumps(item, ensure_ascii=False) + '\n')



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
  train_save_name = 'intent_train_v1_hy_gen_0617.jsonl'
  test_name = 'intent_test_v1.csv'
  test_save_name = 'intent_test_v1_hy_gen.jsonl'

  if args.task_type == 'data':
    print("-----------------------------------------------process data-----------------------------------------------------------------------")
    get_sft_data(file_path, train_name, column_names, train_save_name, sample = False, prompt_type=prompt_type)
    print("已跳过测试集处理，所有数据都用于训练集")