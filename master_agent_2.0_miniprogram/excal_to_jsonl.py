# -*- coding: utf-8 -*-
"""小程序归属二分类语料：xlsx -> train.jsonl

xlsx 结构（gen_小程序二分类语料.py 产出）：
  sheet "1" / "0"：表头 query | label | subtype | group
  sheet "分布统计"：统计用，转换时跳过

jsonl 字段（DPO/SFT 兼容格式）：
  instruction / system / input / output / rejected / history

用法：
  python3 excal_to_jsonl.py                                  # 默认输入输出
  python3 excal_to_jsonl.py -i 语料.xlsx -o train.jsonl      # 指定路径
  python3 excal_to_jsonl.py --no-shuffle --keep-meta         # 保持原序 / 保留 subtype+group
"""
import argparse
import json
import random
import sys
from pathlib import Path

from openpyxl import load_workbook

HERE = Path(__file__).resolve().parent
DEFAULT_XLSX = HERE / "miniprogram_0918.xlsx"
DEFAULT_JSONL = HERE / "train.jsonl"

INSTRUCTION = "判断用户指令是否明确指向车机已上架的小程序"
SYSTEM = (
    "你是车机小程序意图判别器。判断用户指令是否明确指向车机已上架的小程序"
    "（明确点名小程序或其常见简称即为是）。是则输出1，否则输出0。只输出数字。"
)

VALID_LABELS = {"0", "1"}
SKIP_SHEETS = {"分布统计"}


def read_rows(xlsx_path: Path):
    """读取所有语料 sheet，返回 [(query, label, subtype, group)]。"""
    wb = load_workbook(xlsx_path, read_only=True, data_only=True)
    rows, skipped = [], 0
    for ws in wb.worksheets:
        if ws.title in SKIP_SHEETS:
            continue
        header = None
        for raw in ws.iter_rows(values_only=True):
            if header is None:
                header = [str(c).strip() if c is not None else "" for c in raw]
                if "query" not in header or "label" not in header:
                    print(f"[warn] sheet {ws.title!r} 无 query/label 表头，跳过", file=sys.stderr)
                    header = None
                    break
                idx = {name: header.index(name) for name in header if name}
                continue

            def cell(name):
                i = idx.get(name)
                return raw[i] if i is not None and i < len(raw) else None

            query = (str(cell("query")).strip() if cell("query") is not None else "")
            label_raw = cell("label")
            label = str(label_raw).strip() if label_raw is not None else ""
            if not query or label not in VALID_LABELS:
                skipped += 1
                continue
            subtype = cell("subtype")
            group = cell("group")
            rows.append((query, label,
                         str(subtype).strip() if subtype is not None else "",
                         str(group).strip() if group is not None else ""))
    wb.close()
    if skipped:
        print(f"[warn] 跳过 {skipped} 行（query 为空或 label 非 0/1）", file=sys.stderr)
    return rows


def dedup(rows):
    """按 query 去重；同一 query 标签冲突时告警并保留首次出现。"""
    seen, out, conflicts = {}, [], 0
    for query, label, subtype, group in rows:
        if query in seen:
            if seen[query] != label:
                conflicts += 1
                print(f"[warn] 标签冲突，保留首次: {query} ({seen[query]} vs {label})", file=sys.stderr)
            continue
        seen[query] = label
        out.append((query, label, subtype, group))
    if len(out) != len(rows):
        print(f"[info] 去重 {len(rows) - len(out)} 条（含冲突 {conflicts} 条）")
    return out


def to_record(query, label, subtype, group, keep_meta=False):
    rec = {
        "instruction": INSTRUCTION,
        "system": SYSTEM,
        "input": query,
        "output": label,
        "rejected": "0" if label == "1" else "1",
        "history": [],
    }
    if keep_meta:
        rec["_meta"] = {"subtype": subtype, "group": group}
    return rec


def main():
    ap = argparse.ArgumentParser(description="xlsx 语料转 train.jsonl")
    ap.add_argument("-i", "--input", default=str(DEFAULT_XLSX), help="输入 xlsx 路径")
    ap.add_argument("-o", "--output", default=str(DEFAULT_JSONL), help="输出 jsonl 路径")
    ap.add_argument("--seed", type=int, default=20260918, help="打乱随机种子")
    ap.add_argument("--no-shuffle", action="store_true", help="保持 xlsx 原始顺序")
    ap.add_argument("--keep-meta", action="store_true", help="额外写出 subtype/group 到 _meta")
    args = ap.parse_args()

    xlsx_path = Path(args.input).expanduser().resolve()
    out_path = Path(args.output).expanduser().resolve()
    if not xlsx_path.is_file():
        sys.exit(f"[error] 输入文件不存在: {xlsx_path}")

    rows = dedup(read_rows(xlsx_path))
    if not rows:
        sys.exit("[error] 未读到任何有效数据")

    if not args.no_shuffle:
        random.seed(args.seed)
        random.shuffle(rows)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as w:
        for query, label, subtype, group in rows:
            rec = to_record(query, label, subtype, group, keep_meta=args.keep_meta)
            w.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp_path.replace(out_path)

    pos = sum(1 for r in rows if r[1] == "1")
    print(f"[done] {xlsx_path.name} -> {out_path}")
    print(f"       共 {len(rows)} 条：label=1 {pos} 条，label=0 {len(rows) - pos} 条"
          f"（{'原序' if args.no_shuffle else f'已打乱 seed={args.seed}'}）")


if __name__ == "__main__":
    main()
