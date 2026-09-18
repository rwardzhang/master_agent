#!/usr/bin/env python3
"""从 CLS 导出的原始日志中抽取 tool_select 样本。

输入支持：
- 行级 JSON / JSONL
- 每行一个对象，且对象里包含 message 字段

目标：
- 把原始日志里 `tool_select messages: ... -> raw='...' -> tool=... args=...` 的记录抽成结构化样本
- 供后续逐条审计、回标、生成训练数据使用
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

PATTERN = re.compile(r"tool_select messages: (\[.*\]) -> raw='(.*?)' -> tool=([^ ]+) args=(.*)$")
DOMAIN_RE = re.compile(r"你是一个(.+?)工具选择助手")


def iter_json_lines(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"第 {line_no} 行 JSON 解析失败: {e}") from e


def extract_last_user(context_text: str) -> str:
    lines = [x.strip() for x in context_text.split("\n") if x.strip()]
    for x in reversed(lines):
        if x.startswith("user:"):
            return x[5:].strip()
    return lines[-1] if lines else "-"


def extract_case(obj: Dict[str, Any], case_id: int) -> Optional[Dict[str, Any]]:
    message = obj.get("message", "")
    match = PATTERN.search(message)
    if not match:
        return None

    messages_literal, raw_answer, tool_name, args_str = match.groups()
    messages = ast.literal_eval(messages_literal)
    if not isinstance(messages, list) or len(messages) < 2:
        return None

    system_content = messages[0].get("content", "")
    user_content = messages[1].get("content", "")

    domain_match = DOMAIN_RE.search(system_content)
    domain = domain_match.group(1) if domain_match else "-"

    location = "-"
    if "【当前位置】" in user_content:
        location = user_content.split("【当前位置】", 1)[1].split("\n", 1)[0].strip() or "-"

    context = ""
    if "【上下文对话信息】" in user_content:
        context = user_content.split("【上下文对话信息】", 1)[1].strip()

    return {
        "case_id": case_id,
        "timestamp": obj.get("__TIMESTAMP__") or obj.get("timestamp", ""),
        "trace_id": obj.get("trace_id", ""),
        "domain": domain,
        "location": location,
        "query": extract_last_user(context),
        "original_answer": raw_answer,
        "tool_name": tool_name,
        "args": args_str,
        "system": system_content,
        "user": user_content,
        "context": context,
        "source_message": message,
    }


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: List[Dict[str, Any]]) -> None:
    fieldnames = [
        "case_id",
        "timestamp",
        "trace_id",
        "domain",
        "location",
        "query",
        "original_answer",
        "tool_name",
        "args",
        "context",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="抽取 CLS 导出日志中的 tool_select 样本")
    ap.add_argument("src", help="原始导出日志 .json/.jsonl")
    ap.add_argument("-o", "--out", required=True, help="输出抽取后的 jsonl 文件")
    ap.add_argument("--csv", help="可选：同时输出 csv")
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    src = Path(args.src).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for obj in iter_json_lines(src):
        case = extract_case(obj, len(rows) + 1)
        if case is not None:
            rows.append(case)

    write_jsonl(out, rows)
    if args.csv:
        write_csv(Path(args.csv).expanduser().resolve(), rows)

    print(f"抽取完成，共 {len(rows)} 条 -> {out}")
    if args.csv:
        print(f"CSV -> {Path(args.csv).expanduser().resolve()}")


if __name__ == "__main__":
    main()
