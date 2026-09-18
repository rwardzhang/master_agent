#!/usr/bin/env python3
"""把人工/模型审过的 reviewed.csv 合并回抽取样本，生成新的训练数据。

reviewed.csv 最少需要这些列：
- case_id
- verdict
- final_train_answer
- use_for_training
- reason

输入 extracted_cases.jsonl 必须由 extract_tool_select_logs.py 产出，至少包含：
- case_id
- system
- user
- original_answer
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List


def load_extracted(path: Path) -> Dict[int, Dict[str, Any]]:
    rows: Dict[int, Dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            rows[int(obj["case_id"])] = obj
    return rows


def load_reviewed(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def truthy(s: str) -> bool:
    return str(s).strip().lower() in {"1", "y", "yes", "true", "是"}


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="根据 reviewed.csv 生成回标训练 jsonl")
    ap.add_argument("extracted", help="extract_tool_select_logs.py 产出的 jsonl")
    ap.add_argument("reviewed", help="reviewed.csv，需包含 case_id/final_train_answer/use_for_training")
    ap.add_argument("-o", "--out", required=True, help="输出 jsonl")
    ap.add_argument(
        "--verdict-only",
        default="",
        help="只保留指定 verdict（逗号分隔，如 错误,可接受但建议优化）；留空表示不过滤",
    )
    ap.add_argument("--keep-meta", action="store_true", help="保留 _meta 方便追溯")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    extracted = load_extracted(Path(args.extracted).expanduser().resolve())
    reviewed_rows = load_reviewed(Path(args.reviewed).expanduser().resolve())
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    skipped_path = out_path.with_suffix(".skipped.jsonl")
    allowed_verdicts = {
        part.strip() for part in str(args.verdict_only).split(",") if part.strip()
    }

    kept: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []

    for row in reviewed_rows:
        case_id_raw = (row.get("case_id") or "").strip()
        if not case_id_raw:
            skipped.append({"reason": "缺少 case_id", "row": row})
            continue

        case_id = int(case_id_raw)
        sample = extracted.get(case_id)
        if not sample:
            skipped.append({"reason": f"case_id 不存在: {case_id}", "row": row})
            continue

        final_answer = (row.get("final_train_answer") or "").strip()
        use_for_training = truthy(row.get("use_for_training", ""))
        reason = (row.get("reason") or "").strip()
        verdict = (row.get("verdict") or "").strip()

        if allowed_verdicts and verdict not in allowed_verdicts:
            skipped.append({
                "case_id": case_id,
                "reason": f"verdict 不在过滤集合中: {verdict}",
                "verdict": verdict,
                "original_answer": sample.get("original_answer", ""),
                "final_train_answer": final_answer,
            })
            continue

        if not use_for_training:
            skipped.append({
                "case_id": case_id,
                "reason": "use_for_training != yes",
                "verdict": verdict,
                "original_answer": sample.get("original_answer", ""),
                "final_train_answer": final_answer,
            })
            continue

        if not final_answer:
            skipped.append({
                "case_id": case_id,
                "reason": "final_train_answer 为空",
                "verdict": verdict,
                "original_answer": sample.get("original_answer", ""),
            })
            continue

        messages = [
            {"role": "system", "content": sample["system"]},
            {"role": "user", "content": sample["user"]},
            {"role": "assistant", "content": final_answer},
        ]
        record: Dict[str, Any] = {"messages": messages}
        if args.keep_meta:
            record["_meta"] = {
                "case_id": case_id,
                "domain": sample.get("domain", ""),
                "query": sample.get("query", ""),
                "original_answer": sample.get("original_answer", ""),
                "verdict": verdict,
                "reason": reason,
            }
        kept.append(record)

    with out_path.open("w", encoding="utf-8") as f:
        for row in kept:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    with skipped_path.open("w", encoding="utf-8") as f:
        for row in skipped:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if allowed_verdicts:
        print(f"按 verdict 过滤: {','.join(sorted(allowed_verdicts))}")
    print(f"生成训练样本 {len(kept)} 条 -> {out_path}")
    print(f"跳过 {len(skipped)} 条 -> {skipped_path}")


if __name__ == "__main__":
    main()
