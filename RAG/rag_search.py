"""
在线检索：混合 (FAISS 向量) + BM25 关键词，按加权分数融合后去重返回 topN 产品。

用法：
    from RAG.rag_search import MiniProgramRAG
    rag = MiniProgramRAG()
    hits = rag.search("打开猫眼看电影", top_k=5)

或 CLI:
    python rag_search.py "打开猫眼看电影"
"""

import os
import json
import pickle
import sys
from typing import List, Dict

import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.path.join(BASE_DIR, "index")
FAISS_PATH = os.path.join(INDEX_DIR, "faiss.index")
META_PATH = os.path.join(INDEX_DIR, "meta.jsonl")
BM25_PATH = os.path.join(INDEX_DIR, "bm25.pkl")
CONFIG_PATH = os.path.join(INDEX_DIR, "config.json")


def _minmax(arr: np.ndarray) -> np.ndarray:
    """min-max 归一化到 [0,1]，用于把向量分数和 BM25 分数拉到同一量纲"""
    if len(arr) == 0:
        return arr
    lo, hi = float(arr.min()), float(arr.max())
    if hi - lo < 1e-9:
        return np.zeros_like(arr, dtype="float32")
    return ((arr - lo) / (hi - lo)).astype("float32")


class MiniProgramRAG:
    def __init__(self,
                 vec_weight: float = 0.6,
                 bm25_weight: float = 0.4,
                 recall_pool: int = 50):
        """
        :param vec_weight:   向量分数权重
        :param bm25_weight:  BM25 分数权重
        :param recall_pool:  每路召回条数（融合前的候选池大小）
        """
        self.vec_weight = vec_weight
        self.bm25_weight = bm25_weight
        self.recall_pool = recall_pool

        # 加载配置
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        # 加载 embedding 模型
        print(f"[RAG] 加载 embedding 模型：{self.config['embed_model']}")
        self.model = SentenceTransformer(self.config["embed_model"])

        # 加载 faiss
        self.index = faiss.read_index(FAISS_PATH)
        print(f"[RAG] faiss ntotal={self.index.ntotal}")

        # 加载 meta
        self.docs: List[Dict] = []
        with open(META_PATH, "r", encoding="utf-8") as f:
            for line in f:
                self.docs.append(json.loads(line))

        # 加载 bm25
        with open(BM25_PATH, "rb") as f:
            bm25_pack = pickle.load(f)
        self.bm25 = bm25_pack["bm25"]

    # ---------- 检索 ----------
    def _vector_search(self, query: str, k: int):
        emb = self.model.encode(
            [query], normalize_embeddings=True, convert_to_numpy=True
        ).astype("float32")
        scores, idxs = self.index.search(emb, k)
        return idxs[0], scores[0]

    def _bm25_search(self, query: str, k: int):
        from build_index import tokenize_zh  # 复用同一分词
        tokens = tokenize_zh(query)
        scores = self.bm25.get_scores(tokens)  # shape=(N,)
        top_idx = np.argsort(scores)[::-1][:k]
        return top_idx, scores[top_idx]

    def search(self, query: str, top_k: int = 5) -> List[Dict]:
        """返回 topK 个去重后的产品命中，按融合分数降序"""
        # 两路召回
        vec_idx, vec_scores = self._vector_search(query, self.recall_pool)
        bm25_idx, bm25_scores = self._bm25_search(query, self.recall_pool)

        # 归一化
        vec_scores = _minmax(np.asarray(vec_scores, dtype="float32"))
        bm25_scores = _minmax(np.asarray(bm25_scores, dtype="float32"))

        # 融合分数：doc_id -> fused_score
        fused: Dict[int, Dict] = {}
        for i, s in zip(vec_idx, vec_scores):
            if i < 0:
                continue
            fused.setdefault(int(i), {"vec": 0.0, "bm25": 0.0})["vec"] = float(s)
        for i, s in zip(bm25_idx, bm25_scores):
            fused.setdefault(int(i), {"vec": 0.0, "bm25": 0.0})["bm25"] = float(s)

        scored_docs = []
        for doc_id, sc in fused.items():
            fused_score = self.vec_weight * sc["vec"] + self.bm25_weight * sc["bm25"]
            d = self.docs[doc_id]
            scored_docs.append({
                "doc_id": doc_id,
                "fused_score": fused_score,
                "vec_score": sc["vec"],
                "bm25_score": sc["bm25"],
                **d,
            })
        scored_docs.sort(key=lambda x: x["fused_score"], reverse=True)

        # 按 product_id 去重，保留每个产品分数最高的那条 doc
        seen = set()
        results = []
        for d in scored_docs:
            pid = d["product_id"]
            if pid in seen:
                continue
            seen.add(pid)
            results.append({
                "score": round(d["fused_score"], 4),
                "vec_score": round(d["vec_score"], 4),
                "bm25_score": round(d["bm25_score"], 4),
                "mini_program_name": d["mini_program_name"],
                "page_name": d["page_name"],
                "scene_category": d["scene_category"],
                "scene_description": d["scene_description"],
                "intent_category": d["intent_category"],
                "app_id": d["app_id"],
                "page_path": d["page_path"],
                "need_param_extract": d["need_param_extract"],
                "matched_example": d["matched_example"],
            })
            if len(results) >= top_k:
                break
        return results


def _pretty_print(hits):
    for i, h in enumerate(hits, 1):
        print(f"\n#{i} score={h['score']}  (vec={h['vec_score']}, bm25={h['bm25_score']})")
        print(f"  小程序: {h['mini_program_name']}   页面: {h['page_name']}   场景: {h['scene_category']}")
        print(f"  AppID : {h['app_id']}")
        print(f"  Path  : {h['page_path']}")
        print(f"  意图  : {h['intent_category']}   需参数抽取: {h['need_param_extract']}")
        print(f"  命中示例: {h['matched_example']}")


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "打开猫眼看电影"
    rag = MiniProgramRAG()
    print(f"\nQuery: {q}")
    hits = rag.search(q, top_k=5)
    _pretty_print(hits)
