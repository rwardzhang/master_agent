#!/usr/bin/env python3
"""生成可直接训练的最终格式（LLaMA-Factory sharegpt / OpenAI messages）。

只做三件事，messages 内文本一字不改：
  1) 剥掉 _meta（训练侧不读，对齐 08.20 已跑通版本里 35298 条无 _meta 的形态）
  2) 剔除无效样本：assistant.content 为空（会产生全 -100 label，白跑 step）
  3) 剔除结构异常样本：role 序列不是 system/user/assistant、其他 role 为空

输出：
  <out>.jsonl              可训练主文件（顶层键仅 messages）
  <out>.dropped.jsonl      被剔除的样本（带剔除原因，供人工回补）
  <out>.dataset_info.json  dataset_info 片段
"""
import argparse
import json
import os
from collections import Counter

EXPECT_ROLES = ("system", "user", "assistant")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--keep-meta", action="store_true",
                    help="保留 _meta（默认剥掉）")
    ap.add_argument("--keep-empty", action="store_true",
                    help="保留 assistant 为空的样本（默认剔除）")
    args = ap.parse_args()

    kept, dropped = [], []
    for i, line in enumerate(open(args.src, encoding="utf-8"), 1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            dropped.append({"line": i, "reason": f"JSON 解析失败: {e}", "raw": line[:200]})
            continue

        ms = d.get("messages")
        if not ms:
            dropped.append({"line": i, "reason": "缺少 messages 字段", "raw": line[:200]})
            continue

        roles = tuple(m.get("role") for m in ms)
        if roles != EXPECT_ROLES:
            dropped.append({"line": i, "reason": f"role 序列异常: {roles}", "messages": ms})
            continue

        if not ms[2].get("content", "").strip() and not args.keep_empty:
            dropped.append({
                "line": i,
                "reason": "assistant.content 为空（无学习目标，训练时产生全 -100 label）",
                "last_user": ms[1]["content"].strip().split("\n")[-1][:120],
                "messages": ms,
            })
            continue

        if not ms[0].get("content", "").strip() or not ms[1].get("content", "").strip():
            dropped.append({"line": i, "reason": "system 或 user 为空", "messages": ms})
            continue

        kept.append({"messages": ms} if not args.keep_meta else d)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as w:
        for r in kept:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")

    drop_path = args.out.replace(".jsonl", ".dropped.jsonl")
    with open(drop_path, "w", encoding="utf-8") as w:
        for r in dropped:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")

    ds_name = os.path.splitext(os.path.basename(args.out))[0]
    info = {ds_name: {
        "file_name": os.path.abspath(args.out),
        "formatting": "sharegpt",
        "columns": {"messages": "messages"},
        "tags": {"role_tag": "role", "content_tag": "content", "user_tag": "user",
                 "assistant_tag": "assistant", "system_tag": "system"},
    }}
    info_path = args.out.replace(".jsonl", ".dataset_info.json")
    with open(info_path, "w", encoding="utf-8") as w:
        json.dump(info, w, ensure_ascii=False, indent=2)

    print(f"保留 {len(kept)} 条 -> {args.out}")
    print(f"剔除 {len(dropped)} 条 -> {drop_path}")
    for k, v in Counter(r["reason"].split("（")[0] for r in dropped).most_common():
        print(f"    {v:>4}  {k}")
    print(f"dataset_info 片段 -> {info_path}")

    print("\n=== 校验（只读）===")
    print(f"  顶层键: {set(tuple(r.keys()) for r in kept)}")
    print(f"  role 序列: {dict(Counter(tuple(m['role'] for m in r['messages']) for r in kept))}")
    print(f"  空 content: {sum(1 for r in kept if any(not m['content'].strip() for m in r['messages']))}")
    print(f"  assistant 前后空白: {sum(1 for r in kept if r['messages'][2]['content'] != r['messages'][2]['content'].strip())}")
    print(f"  think 标签: {sum(1 for r in kept if '<think>' in r['messages'][2]['content'] or '</think>' in r['messages'][2]['content'])}")
    L = sorted(sum(len(m["content"]) for m in r["messages"]) for r in kept)
    print(f"  总字符 min/P50/P90/P99/max: {L[0]}/{L[len(L)//2]}/{L[int(len(L)*.9)]}/{L[int(len(L)*.99)]}/{L[-1]}")
    print(f"  估算 token（/1.6）max ≈ {int(L[-1]/1.6)}  -> cutoff_len 建议 ≥ {1 << max(11, int(L[-1]/1.6 - 1).bit_length())}")


if __name__ == "__main__":
    main()
