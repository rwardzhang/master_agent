"""
交互式 Demo：加载一次索引，反复输入 query 检索。
用法：python run_demo.py
输入 q / quit / exit 退出。
"""

from rag_search import MiniProgramRAG, _pretty_print


def main():
    rag = MiniProgramRAG()
    print("\n========== 小程序直达 RAG 检索 Demo ==========")
    print(" 输入自然语言 query，回车检索；输入 q / quit / exit 退出\n")
    while True:
        try:
            q = input(">>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not q:
            continue
        if q.lower() in {"q", "quit", "exit"}:
            break
        try:
            hits = rag.search(q, top_k=5)
            _pretty_print(hits)
            print()
        except Exception as e:
            print(f"[Error] {e}")


if __name__ == "__main__":
    main()
