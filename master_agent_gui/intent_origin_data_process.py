import os
import random
import pandas as pd
from sklearn.model_selection import train_test_split


def get_origin_file(file_name, sheet_name, sample_cnt = 0):
  # 读取Excel文件的单个sheet（忽略样式避免格式错误）
  df = pd.read_excel(file_name, sheet_name=sheet_name, engine='openpyxl', engine_kwargs={'data_only': True})

  print(f"Sheet '{sheet_name}' 形状: {df.shape}")
  print(f"列名: {df.columns.tolist()}")

  origin_dict = {}
  has_history = 'history' in df.columns  # 检查是否有history列
  
  for index, row in df.iterrows():
    # 正确处理NaN值
    f = row['from'] if pd.notna(row['from']) else 'user'
    f = str(f).strip() if f else 'user'
    
    q = row['query'] if pd.notna(row['query']) else ''
    q = str(q).strip()
    
    intent = row['intent'] if pd.notna(row['intent']) else ''
    intent = str(intent).strip()
    
    entity = row['entity'] if pd.notna(row['entity']) else ''
    entity = str(entity).strip()
    
    # 跳过空的intent或query
    if not intent or not q:
      continue
    
    # 如果有history列，也读取它
    if has_history:
      history = row['history'] if pd.notna(row['history']) else ''
      history = str(history).strip()
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
    # 修复采样逻辑
    if sample_cnt > 0 and sample_cnt < len(v_list):
      sample_v_list = random.sample(v_list, sample_cnt)
    else:
      sample_v_list = v_list
    print(f"{intent}: 原始{len(v_list)}条, 采样{len(sample_v_list)}条")

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
  print('处理完成，总数据量:', len(processed_list))
  
  if len(processed_list) == 0:
    print("警告：没有有效数据！")
    return pd.DataFrame()

  processed_df = pd.DataFrame(processed_list)
  print("数据预览:")
  print(processed_df.head(5))
  grouped = processed_df.groupby('intent').size()
  print("各intent数据分布:")
  print(grouped)

  return processed_df




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
  file_name = 'gui_914.xlsx'
  
  # 获取Excel文件中的所有sheet名称curl -X POST "http://21.175.63.185:8187/v1/chat/completions" \
  #   -H "Content-Type: application/json" \
  #   -H "Authorization: Bearer 7auGXNATFSKl7dF" \
  #   -H "Wsid: 12146" \
  #   --connect-timeout 30 \
  #   --max-time 60 \
  #   -d '{
  #     "query_id": "470324c4a8bd4aa4b42f5d8ddfe922b2",
  #     "model": "master_scenariox_gui_category_model",
  #     "stream": false,
  #     "messages": [
  #       {
  #         "role": "system",
  #         "content": "你是一个专业的多智能体意图分类助手，你的核心功能是通过自然语言处理精准识别用户意图是以下哪种意图种类：\n\n{\n  \"agent_name\": \"coffee\",\n  \"description\": \"你是一个专业的点单助手，支持完整的点单流程，仅支持帮助用户购买咖啡如：瑞幸咖啡等\"\n},\n{\n  \"agent_name\": \"milk_tea\",\n  \"description\": \"你是一个专业的奶茶点单助手，支持完整的点单流程，仅支持帮助用户购买奶茶如：奶茶,购买奶茶等\"\n},\n{\n  \"agent_name\": \"burger\",\n  \"description\": \"你是一个专业的汉堡点单助手，支持完整的点单流程，仅支持帮助用户购买汉堡如：汉堡,购买汉堡等\"\n},\n{\n  \"agent_name\": \"unknown\",\n  \"description\": \"当用户请求不属于上述任何一类时，输出此类别。包括：闲聊、问候、无关话题、模糊表达等\"\n}\n\n要求：\n- 输出必须是上述agent_name之一，不得添加解释、标点或换行\n- 若用户请求涉及多个意图，选择最核心或最先提及的意图\n- 只用输出一个符合要求的类别名称\n- 若无法明确归类到这几类，则输出\"unknown\""
  #       },
  #       {
  #         "role": "user",
  #         "content": "帮我推荐几个适合预算不高的博物馆"
  #       }
  #     ],
  #     "temperature": 0.1,
  #     "top_p": 1.0,
  #     "max_tokens": 2048,
  #     "wsid": "12146",
  #     "openai_infer": true
  #   }'
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

    # 全部作为训练集，不生成测试集
    train_name = 'intent_train_v1.csv'
    combined_df.to_csv(os.path.join(file_path, train_name), index=False)
    print(f"已保存训练集到 {os.path.join(file_path, train_name)}, 共 {len(combined_df)} 条数据")
    grouped = combined_df.groupby('intent').size()
    print("各intent数据分布:")
    print(grouped)
  else:
    print("\n" + "=" * 80)
    print("错误：没有成功处理任何sheet")
    print("=" * 80)


  # file_path='/apdcephfs_nj6/share_4274659/sunnyqiao/trl_sft/data/function_hy'
  # sheet_name = 'Sheet1'

  # file_name = 'zhengquan_tools_origin_data_v2.xlsx'
  # df = get_origin_file(os.path.join(file_path,file_name), sheet_name, sample_cnt = 1000)

  # train_name = 'zhengquan_tools_origin_data_train_v2.csv'
  # test_name = 'zhengquan_tools_origin_data_test_v2.csv'
  # train_and_test(df, 0.1, file_path, train_name, test_name)
