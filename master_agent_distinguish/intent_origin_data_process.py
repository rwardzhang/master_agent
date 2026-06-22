import os
import random
import pandas as pd
from sklearn.model_selection import train_test_split


def get_origin_file(file_name, sheet_name=None, sample_cnt = 0):
  # 读取Excel文件的所有sheet
  # 如果sheet_name为None，则读取所有sheet；否则读取指定的sheet
  if sheet_name is None:
    # 读取所有sheet
    all_sheets = pd.read_excel(file_name, sheet_name=None, engine='openpyxl')
    print(f"找到 {len(all_sheets)} 个sheet: {list(all_sheets.keys())}")
    
    # 合并所有sheet的数据
    all_dfs = []
    for sheet_name, df in all_sheets.items():
      print(f"正在处理sheet: {sheet_name}, 行数: {len(df)}")
      all_dfs.append(df)
    
    # 合并所有DataFrame
    df = pd.concat(all_dfs, ignore_index=True)
    print(f"合并后总行数: {len(df)}")
  else:
    # 读取指定的sheet
    df = pd.read_excel(file_name, sheet_name=sheet_name, engine='openpyxl')
    print(f"读取sheet: {sheet_name}, 行数: {len(df)}")

  processed_list = []
  for index, row in df.iterrows():
    query = str(row['query']).replace('nan', '').strip()
    output = str(row['output']).replace('nan', '').strip()
    
    # 跳过空数据
    if not query or not output:
      continue
    
    temp_dict = {}
    temp_dict['query'] = query
    temp_dict['output'] = output
    processed_list.append(temp_dict)
  
  # 如果指定了采样数量且小于总数据量，则进行随机采样
  if sample_cnt > 0 and sample_cnt < len(processed_list):
    random.shuffle(processed_list)
    processed_list = random.sample(processed_list, sample_cnt)
  else:
    random.shuffle(processed_list)
  
  print('processed_list:', len(processed_list))

  processed_df = pd.DataFrame(processed_list)
  print(processed_df.head(5))

  return processed_df


def train_and_test(df, test_size, file_path, train_name, test_name):
  if test_size == 0:
    # 当test_size为0时，整个数据集作为训练集，测试集为空
    train_df = df
    test_df = pd.DataFrame(columns=df.columns)
    print('所有数据都作为训练集，测试集为空')
    print('train_df', len(train_df))
    print(train_df.head(5))
    print('test_df', len(test_df))
  else:
    train_df, test_df = train_test_split(df, test_size=test_size, random_state=42)
    print('train_df', len(train_df))
    print(train_df.head(5))
    print('test_df', len(test_df))
    print(test_df.head(5))

  train_df.to_csv(os.path.join(file_path,train_name), index=False)
  test_df.to_csv(os.path.join(file_path,test_name), index=False)



if __name__ == "__main__":

  file_path='./'
  # 设置为None以读取所有sheet，或指定具体的sheet名称
  sheet_name = None  # 读取所有sheet并合并
  # sheet_name = '简单意图'  # 如果只想读取特定sheet，取消注释并修改名称

  #   file_name = 'intent_origin_data_v0.xlsx'
  #   file_name = 'intent_origin_data_v1.xlsx'
  #   file_name = 'intent_origin_data_v2.xlsx'
  file_name = 'master_distinguish_0514.xlsx'
  df = get_origin_file(os.path.join(file_path,file_name), sheet_name, sample_cnt = 6000)

  train_name = 'intent_train_v1.csv'
  test_name = 'intent_test_v1.csv'
  train_and_test(df, 0, file_path, train_name, test_name)


  # file_path='/apdcephfs_nj6/share_4274659/sunnyqiao/trl_sft/data/function_hy'
  # sheet_name = 'Sheet1'

  # file_name = 'zhengquan_tools_origin_data_v2.xlsx'
  # df = get_origin_file(os.path.join(file_path,file_name), sheet_name, sample_cnt = 1000)

  # train_name = 'zhengquan_tools_origin_data_train_v2.csv'
  # test_name = 'zhengquan_tools_origin_data_test_v2.csv'
  # train_and_test(df, 0.1, file_path, train_name, test_name)