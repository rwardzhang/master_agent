"""
把 starbucks_expand.txt 转成训练集 jsonl 格式（label=starbucks）
- 复用原 coffee_train.jsonl 里的 system prompt（保证一致）
- 跟原训练集做 user 级去重，避免重复样本
- 输出：starbucks_expand.jsonl
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).parent
SRC_TXT = ROOT / "starbucks_expand.txt"
SRC_JSONL = ROOT / "coffee_train.jsonl"
OUT_JSONL = ROOT / "starbucks_expand.jsonl"


def load_queries(p: Path) -> list[str]:
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # 去掉中文标点污染
        s = re.sub(r"\s+", " ", s)
        out.append(s)
    return out


def main() -> None:
    # 1. 拿 system prompt（跟现有训练集保持完全一致）
    rows = [json.loads(l) for l in SRC_JSONL.read_text(encoding="utf-8").splitlines()]
    sys_prompt = next(
        m["content"] for r in rows for m in r["messages"] if m["role"] == "system"
    )

    # 2. 已有 user 集合（去重）
    seen: set[str] = set()
    for r in rows:
        for m in r["messages"]:
            if m["role"] == "user":
                seen.add(m["content"].strip())

    # 3. 拓展 query
    queries = load_queries(SRC_TXT)

    new_rows: list[dict] = []
    dup = 0
    for q in queries:
        if q in seen:
            dup += 1
            continue
        seen.add(q)
        new_rows.append(
            {
                "messages": [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": "starbucks"},
                ]
            }
        )

    # 4. 写出
    with OUT_JSONL.open("w", encoding="utf-8") as f:
        for r in new_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"原 query 数: {len(queries)}")
    print(f"与现有训练集重复: {dup}")
    print(f"写入新样本: {len(new_rows)} -> {OUT_JSONL}")
    print("\n合并方式:")
    print(f"  cat {SRC_JSONL.name} {OUT_JSONL.name} > coffee_train.merged.jsonl")


if __name__ == "__main__":
    main()
