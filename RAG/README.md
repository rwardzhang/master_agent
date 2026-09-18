# 小程序直达 RAG

基于 `data/mini_program_v2.csv`（394 条小程序页面产品清单）构建的离线 RAG，输入一句自然语言 query，返回最匹配的小程序页面（含 `AppID / PagePath` 等直达信息）。

## 技术方案

- **数据展开**：每条产品的 `QueryExample`（多行）被拆分为多个独立 doc，附加 `MiniProgramName / PageName / SceneCategory / SceneDescription` 做语义增强。
- **向量检索**：`BAAI/bge-small-zh-v1.5` 编码 + FAISS 内积索引（余弦相似度）。
- **关键词检索**：jieba 分词 + BM25。
- **融合排序**：两路各取 `recall_pool=50`，min-max 归一化后 `0.6*vec + 0.4*bm25` 加权，按 `product_id` 去重返回 topK。

## 目录结构

```
RAG/
├── data/mini_program_v2.csv     # 产品清单原始数据
├── build_index.py               # 离线：构建 FAISS + BM25 索引
├── rag_search.py                # 在线：混合检索 API + CLI
├── run_demo.py                  # 交互式 Demo
├── requirements.txt
└── index/                       # 构建产出：faiss.index / meta.jsonl / bm25.pkl / config.json
```

## 使用

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 构建索引（一次性，几分钟）

```bash
python build_index.py
```

首次会自动从 HuggingFace 下载 `bge-small-zh-v1.5`（~100MB）。

### 3. 检索

**CLI 单次查询：**
```bash
python rag_search.py "打开猫眼看电影"
```

**交互式 demo：**
```bash
python run_demo.py
```

**作为库调用：**
```python
from rag_search import MiniProgramRAG
rag = MiniProgramRAG()
hits = rag.search("附近有什么话剧表演", top_k=5)
for h in hits:
    print(h["mini_program_name"], h["page_name"], h["app_id"], h["page_path"])
```

## 返回字段

每条命中包含：`score / vec_score / bm25_score / mini_program_name / page_name / scene_category / scene_description / intent_category / app_id / page_path / need_param_extract / matched_example`。

## 可调参数

在 `MiniProgramRAG(vec_weight=0.6, bm25_weight=0.4, recall_pool=50)` 构造函数里可以调向量/BM25 权重，以及每路召回池大小。
