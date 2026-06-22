import os
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "max_split_size_mb:100"
import json
import argparse
import pandas as pd
from typing import List, Dict
import random
os.environ["TOKENIZERS_PARALLELISM"] = "false"  # 或者 "true
import transformers
transformers.logging.set_verbosity_error()

#####################get data########################################################################################################
def get_origin_file(file_name, column_names, sample = False) -> List[Dict]:
  # 读取CSV文件
  result_list = []
  df = pd.read_csv(file_name)
  if sample:
    df = df.sample(n=50, replace=False)
  # 按行遍历数据
  for index, row in df.iterrows():
    result = {}
    for name in column_names:
      result[name] = str(row[name]).replace('nan', '')
    result_list.append(result)
  return result_list


intent_class_map = {'order':'order',
                    'chat':'chat',
                    'news':'news',
                    'music':'music',
                    'car_control':'car_control',
                    'travel_plan':'travel_plan',
                    'podcast':'podcast'
                    }
class_intent_map = {value: key for key, value in intent_class_map.items()}


def get_intent_prompt1() -> str:
  system_prompt = """
你是一个智能车载助手的意图分类专家。请仔细分析用户查询，判断是简单意图、复杂意图还是模糊意图。

一、意图定义：

1. **简单意图（输出0）**：
   - 用户需求明确且单一，只包含一个具体的动作或请求
   - 可以直接识别出对应的功能模块（如音乐、导航、新闻等）
   - 不需要推理或场景理解就能明确执行什么操作
   
2. **复杂意图（输出1）**：
   - 包含多个明确的动作或请求，需要拆解为多个子任务
   - 通常包含"然后"、"再"、"和"等连接词
   - 每个子动作都是明确的，可以直接执行
   
3. **模糊意图（输出1）**：
   - 用户需求不明确，没有指定具体要做什么动作
   - 只描述了情绪状态、需求状态或期望效果（如"累了"、"提提神"、"浪漫氛围"）
   - 需要推理或场景理解才能确定应该执行哪些具体操作
   - 可能需要综合多个功能来满足用户的隐含需求

二、示例分类：
**简单意图（输出0）**：
- "我要看体育新闻" 、"我要听音乐" 、"我想去山海关" 、"推荐附近好吃的美食" 、"根据武汉生成播客"、"播放周杰伦的歌" 、"查询今天天气" 
**复杂意图（输出1）**：
- "帮我点一杯咖啡，再帮我播放音乐" 、"查询最近的奶茶店然后打开饿了么下单"、"查询今日汇率，播放财经资讯"、"打开车窗打开空调"、"导航到商场电影院，帮我看看现在有什么电影再看看今天的天气"
**模糊意图（输出1）**：
- "我累了"、"我困了" 、"给我提提神" 、"给我浪漫的氛围"、"生成孩子过生日的场景"、"结婚纪念日的模式" 、"生成通勤场景" 

三、判断优先级：
  1. 首先判断是否为模糊意图
  2. 然后判断是否为复杂意图
  3. 最后归为简单意图
  
四、输出要求：
- 简单意图：输出 0
- 复杂意图：输出 1
- 模糊意图：输出 1
- 只输出数字0或1，不要包含任何其他字符、解释或换行
"""
  return system_prompt

#from,query,intent,entity
def get_sft_data(file_path, file_name, column_names, save_name, sample = False, prompt_type=1):
  origin_info_dict_list = get_origin_file(os.path.join(file_path, file_name), column_names, sample=sample)
  save_list = []

  for info_dict in origin_info_dict_list:
    query = info_dict['query']
    output = info_dict['output']

    sys_prompt = get_intent_prompt1()

    json_line = {"instruction":"识别语句的意图","system":sys_prompt,"input":query, "output":output,"history":[]}
    json_str = json.dumps(json_line, ensure_ascii=False)
    save_list.append(json_str)

  print("total cnt of data is :", len(save_list))
  with open(os.path.join(file_path, save_name), 'w') as file:
    for s in save_list:
      file.write(s + '\n')



if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Config Arguments',allow_abbrev=False)
  group = parser.add_argument_group(title='data args')
  parser.add_argument('--task_type',type=str,default='data',help='file_dir of the data')
  # parser.add_argument('--task_type',type=str,default='eval',help='file_dir of the data')
  args = parser.parse_args()

  file_path='./'
  column_names = ['query','output']

  prompt_type = 1
  train_name = 'intent_train_v1.csv'
  train_save_name = 'intent_train_v1_hy_gen_distingish_0514.jsonl'
  test_name = 'intent_test_v1.csv'
  test_save_name = 'intent_test_v1_hy_gen_qf.jsonl'

  if args.task_type == 'data':
    print("-----------------------------------------------process data-----------------------------------------------------------------------")
    get_sft_data(file_path, train_name, column_names, train_save_name, sample = False, prompt_type=prompt_type)
    get_sft_data(file_path, test_name, column_names, test_save_name, sample = False, prompt_type=prompt_type)