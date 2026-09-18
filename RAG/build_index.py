"""
离线索引构建脚本
输入：data/mini_program_v2.csv
产出：index/faiss.index, index/meta.jsonl, index/bm25.pkl, index/config.json

设计思路：
1. 每条产品有多个 QueryExample（换行分隔），把每一条 example 作为一个独立的检索单元（doc），
   这样"打开猫眼看电影"这类query能精准命中 example，召回效果最好。
2. 每个 doc 的文本 = QueryExample + 场景描述 + 小程序名 + 页面名（拼接，语义更完整）。
3. 同一产品的多个 doc 会共享同一份 payload（AppID / PagePath 等），检索后按产品去重即可。
4. 向量索引用 FAISS（L2 归一化后做内积 = 余弦相似度），关键词索引用 BM25。
"""

import os
import json
import pickle
import re

import numpy as np
import pandas as pd
import jieba
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
import faiss

# ============ 路径配置 ============
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(BASE_DIR, "data", "mini_program_v2.csv")
INDEX_DIR = os.path.join(BASE_DIR, "index")
FAISS_PATH = os.path.join(INDEX_DIR, "faiss.index")
META_PATH = os.path.join(INDEX_DIR, "meta.jsonl")
BM25_PATH = os.path.join(INDEX_DIR, "bm25.pkl")
CONFIG_PATH = os.path.join(INDEX_DIR, "config.json")

# ============ 模型配置 ============
# 中文小型 embedding 模型，首次会自动从 HuggingFace 下载 ~100MB
# 如需更强模型可换成 BAAI/bge-large-zh-v1.5
EMBED_MODEL_NAME = "BAAI/bge-small-zh-v1.5"
EMBED_DIM = 512  # bge-small-zh 输出维度


# ============ 数据处理 ============
def load_csv(csv_path: str) -> pd.DataFrame:
    """读取 CSV，只保留需要的列，剔除空行"""
    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str).fillna("")
    keep_cols = [
        "SceneCategory", "SceneDescription", "MiniProgramName", "PageName",
        "QueryExample", "IntentCategory", "AppID", "PagePath", "NeedParamExtract",
    ]
    df = df[keep_cols]
    # 必填字段过滤
    df = df[(df["MiniProgramName"] != "") & (df["AppID"] != "")].reset_index(drop=True)
    print(f"[load_csv] 有效产品数：{len(df)}")
    return df


def split_query_examples(raw: str):
    """QueryExample 字段是多行文本，按换行拆分，过滤空行"""
    if not raw:
        return []
    parts = re.split(r"[\r\n]+", raw)
    return [p.strip() for p in parts if p.strip()]


def build_docs(df: pd.DataFrame):
    """
    将每条产品的每个 QueryExample 展开为一个独立 doc。
    返回 docs: List[Dict]，包含 text（用于 embedding & bm25）和 payload。
    """
    docs = []
    for prod_id, row in df.iterrows():
        examples = split_query_examples(row["QueryExample"])
        # 即使没有 example，也保留一条 fallback doc（用描述兜底）
        if not examples:
            examples = [row["SceneDescription"] or row["PageName"] or row["MiniProgramName"]]

        payload_base = {
            "product_id": int(prod_id),
            "scene_category": row["SceneCategory"],
            "scene_description": row["SceneDescription"],
            "mini_program_name": row["MiniProgramName"],
            "page_name": row["PageName"],
            "intent_category": row["IntentCategory"],
            "app_id": row["AppID"],
            "page_path": row["PagePath"],
            "need_param_extract": row["NeedParamExtract"],
        }

        for ex in examples:
            # 拼接文本：example 是核心，附加小程序名/页面名/场景描述做语义增强
            text = (
                f"{ex} | 小程序:{row['MiniProgramName']} | 页面:{row['PageName']} "
                f"| 场景:{row['SceneCategory']} | 描述:{row['SceneDescription']}"
            )
            docs.append({
                "text": text,
                "matched_example": ex,
                **payload_base,
            })

    print(f"[build_docs] 展开后 doc 数：{len(docs)}")
    return docs


# ============ 向量索引 ============
def build_faiss_index(docs, model: SentenceTransformer):
    """对每个 doc 的 text 做 embedding，构建 FAISS 内积索引（余弦相似度）"""
    texts = [d["text"] for d in docs]
    print(f"[faiss] 开始 embedding，共 {len(texts)} 条 ...")
    embs = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,  # L2 归一化，配合 IndexFlatIP 即余弦相似度
        convert_to_numpy=True,
    ).astype("float32")

    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embs)
    print(f"[faiss] 索引构建完成，dim={dim}, ntotal={index.ntotal}")
    return index, dim


# ============ BM25 索引 ============
def tokenize_zh(text: str):
    """中文分词，去掉纯符号 token"""
    tokens = jieba.lcut(text)
    return [t for t in tokens if t.strip() and not re.fullmatch(r"[\W_]+", t)]


def build_bm25(docs):
    from rank_bm25 import BM25Okapi
    print("[bm25] 分词中 ...")
    corpus_tokens = [tokenize_zh(d["text"]) for d in tqdm(docs)]
    bm25 = BM25Okapi(corpus_tokens)
    print("[bm25] 索引构建完成")
    return bm25, corpus_tokens


# ============ 保存 ============
def save_all(index, dim, docs, bm25, corpus_tokens):
    os.makedirs(INDEX_DIR, exist_ok=True)

    faiss.write_index(index, FAISS_PATH)
    print(f"[save] faiss -> {FAISS_PATH}")

    with open(META_PATH, "w", encoding="utf-8") as f:
        for d in docs:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"[save] meta -> {META_PATH}（{len(docs)} 条）")

    with open(BM25_PATH, "wb") as f:
        pickle.dump({"bm25": bm25, "corpus_tokens": corpus_tokens}, f)
    print(f"[save] bm25 -> {BM25_PATH}")

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "embed_model": EMBED_MODEL_NAME,
            "embed_dim": dim,
            "num_docs": len(docs),
        }, f, ensure_ascii=False, indent=2)
    print(f"[save] config -> {CONFIG_PATH}")


def main():
    df = load_csv(CSV_PATH)
    docs = build_docs(df)

    print(f"[model] 加载 embedding 模型：{EMBED_MODEL_NAME}")
    model = SentenceTransformer(EMBED_MODEL_NAME)

    index, dim = build_faiss_index(docs, model)
    bm25, corpus_tokens = build_bm25(docs)
    save_all(index, dim, docs, bm25, corpus_tokens)
    print("\n✅ 索引构建全部完成。")


if __name__ == "__main__":
    main()
