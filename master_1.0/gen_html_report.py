#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 predictions.jsonl 生成带混淆矩阵热力图的自包含 HTML 评测报告。"""
import json, html, argparse
from pathlib import Path
from collections import Counter, defaultdict


def load_preds(path):
    rows = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', default='eval_output/predictions.jsonl')
    ap.add_argument('--out', default='eval_output/eval_report.html')
    args = ap.parse_args()

    rows = load_preds(args.input)
    n = len(rows)
    correct = sum(r['correct'] for r in rows)
    acc = correct / n if n else 0.0

    # 标签集合（gold 优先，pred 里的越界单独归入 __invalid__）
    gold_labels = sorted({r['gold'] for r in rows})
    labels = list(gold_labels)
    has_invalid = any(r['pred'] == '__invalid__' for r in rows)
    pred_labels = labels + (['__invalid__'] if has_invalid else [])

    # 混淆矩阵：行=gold，列=pred
    cm = defaultdict(lambda: Counter())
    for r in rows:
        cm[r['gold']][r['pred']] += 1

    # 每标签 P/R/F1/support
    stats = {}
    for lab in labels:
        tp = cm[lab][lab]
        support = sum(cm[lab].values())
        pred_total = sum(cm[g][lab] for g in labels)  # 被预测为 lab 的总数
        prec = tp / pred_total if pred_total else 0.0
        rec = tp / support if support else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        stats[lab] = dict(precision=prec, recall=rec, f1=f1, support=support, tp=tp)

    macro_p = sum(s['precision'] for s in stats.values()) / len(labels)
    macro_r = sum(s['recall'] for s in stats.values()) / len(labels)
    macro_f1 = sum(s['f1'] for s in stats.values()) / len(labels)

    # 混淆对（非对角，Top）
    confusion_pairs = []
    for g in labels:
        for p in pred_labels:
            if g != p and cm[g][p] > 0:
                confusion_pairs.append((g, p, cm[g][p]))
    confusion_pairs.sort(key=lambda x: -x[2])
    top_pairs = confusion_pairs[:20]

    # 错误样例（每类混淆抓几条）
    error_samples = [r for r in rows if not r['correct']][:40]

    # ---------- 构建 HTML ----------
    def esc(s):
        return html.escape(str(s))

    # 指标卡片
    cards = f'''
    <div class="cards">
      <div class="card"><div class="lab">样本总数</div><div class="num">{n}</div></div>
      <div class="card"><div class="lab">整体准确率</div><div class="num acc">{acc*100:.2f}%</div><div class="sub">{correct}/{n}</div></div>
      <div class="card"><div class="lab">Macro-Precision</div><div class="num">{macro_p:.4f}</div></div>
      <div class="card"><div class="lab">Macro-Recall</div><div class="num">{macro_r:.4f}</div></div>
      <div class="card"><div class="lab">Macro-F1</div><div class="num f1">{macro_f1:.4f}</div></div>
    </div>'''

    # 混淆矩阵热力图（行=真实，列=预测），按行归一化上色
    def cell_color(g, p, v):
        support = stats[g]['support'] if g in stats else 0
        ratio = v / support if support else 0
        if v == 0:
            return 'background:transparent;color:#3a4150;'
        if g == p:
            # 对角：绿色系（正确）
            a = 0.15 + 0.85 * ratio
            return f'background:rgba(63,185,80,{a:.3f});color:#e6edf3;font-weight:600;'
        else:
            # 错误：橙红系
            a = 0.12 + 0.88 * min(1.0, ratio * 3)
            return f'background:rgba(240,90,60,{a:.3f});color:#e6edf3;'

    header_cells = ''.join(f'<th class="rot"><div>{esc(p)}</div></th>' for p in pred_labels)
    matrix_rows = ''
    for g in labels:
        cells = ''
        for p in pred_labels:
            v = cm[g][p]
            style = cell_color(g, p, v)
            txt = str(v) if v else ''
            cells += f'<td style="{style}" title="真实 {esc(g)} → 预测 {esc(p)}: {v}">{txt}</td>'
        matrix_rows += f'<tr><th class="rowlab">{esc(g)}</th>{cells}</tr>'

    matrix_html = f'''
    <div class="matrix-wrap">
      <table class="matrix">
        <thead><tr><th class="corner">真实\\预测</th>{header_cells}</tr></thead>
        <tbody>{matrix_rows}</tbody>
      </table>
    </div>'''

    # 各标签指标表 + 条形图
    def bar(v, cls):
        return f'<div class="barbg"><div class="bar {cls}" style="width:{v*100:.1f}%"></div><span class="barval">{v:.3f}</span></div>'

    stat_rows = ''
    for lab in sorted(labels, key=lambda x: stats[x]['f1']):
        s = stats[lab]
        weak = 'weak' if s['f1'] < 0.85 else ''
        stat_rows += f'''<tr class="{weak}">
          <td class="lname">{esc(lab)}</td>
          <td>{s['support']}</td>
          <td>{bar(s['precision'],'p')}</td>
          <td>{bar(s['recall'],'r')}</td>
          <td>{bar(s['f1'],'f')}</td>
        </tr>'''

    # Top 混淆对
    max_pair = top_pairs[0][2] if top_pairs else 1
    pair_rows = ''
    for g, p, v in top_pairs:
        w = v / max_pair * 100
        pair_rows += f'''<tr>
          <td class="lname">{esc(g)}</td>
          <td class="arrow">→</td>
          <td class="lname pred">{esc(p)}</td>
          <td class="pairbar"><div class="barbg"><div class="bar c" style="width:{w:.1f}%"></div><span class="barval">{v}</span></div></td>
        </tr>'''

    # 错误样例表
    err_rows = ''
    for r in error_samples:
        err_rows += f'''<tr>
          <td>{r['idx']}</td>
          <td class="lname">{esc(r['gold'])}</td>
          <td class="lname pred">{esc(r['pred'])}</td>
          <td class="q">{esc(r['user'])}</td>
        </tr>'''

    total_errors = n - correct

    doc = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>意图分类模型评测报告</title>
<style>
:root {{ color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif; background:#0d1117; color:#e6edf3; }}
.wrap {{ max-width:1280px; margin:0 auto; padding:32px 24px 64px; }}
h1 {{ margin:0 0 6px; font-size:26px; }}
h2 {{ margin:36px 0 14px; font-size:19px; border-left:4px solid #3fb950; padding-left:10px; }}
.muted {{ color:#8b949e; font-size:13px; margin:0 0 4px; }}
.cards {{ display:grid; grid-template-columns:repeat(5,1fr); gap:14px; margin:22px 0; }}
.card {{ background:#161b22; border:1px solid #30363d; border-radius:12px; padding:16px; text-align:center; }}
.card .lab {{ color:#8b949e; font-size:12px; }}
.card .num {{ font-size:26px; font-weight:700; margin-top:8px; }}
.card .num.acc {{ color:#3fb950; }}
.card .num.f1 {{ color:#58a6ff; }}
.card .sub {{ color:#8b949e; font-size:11px; margin-top:2px; }}
table {{ border-collapse:collapse; background:#161b22; }}
.matrix-wrap {{ overflow-x:auto; border:1px solid #30363d; border-radius:12px; padding:8px; }}
.matrix {{ font-size:12px; }}
.matrix th, .matrix td {{ border:1px solid #22272e; padding:0; text-align:center; }}
.matrix td {{ width:38px; height:34px; }}
.matrix .corner {{ background:#1f2630; color:#8b949e; font-size:11px; padding:4px 6px; white-space:nowrap; position:sticky; left:0; z-index:2; }}
.matrix .rowlab {{ background:#1f2630; color:#c9d1d9; padding:0 8px; text-align:right; white-space:nowrap; position:sticky; left:0; z-index:1; font-weight:600; }}
.matrix th.rot {{ background:#1f2630; height:96px; vertical-align:bottom; padding-bottom:6px; }}
.matrix th.rot div {{ writing-mode:vertical-rl; transform:rotate(180deg); margin:0 auto; color:#c9d1d9; font-weight:600; white-space:nowrap; }}
.legend {{ display:flex; gap:18px; align-items:center; margin:10px 2px 0; font-size:12px; color:#8b949e; }}
.legend .sw {{ display:inline-block; width:14px; height:14px; border-radius:3px; margin-right:5px; vertical-align:-2px; }}
.tbl {{ width:100%; border:1px solid #30363d; border-radius:12px; overflow:hidden; }}
.tbl th, .tbl td {{ border-bottom:1px solid #22272e; padding:9px 12px; font-size:13px; text-align:left; vertical-align:middle; }}
.tbl th {{ background:#1f2630; color:#c9d1d9; }}
.tbl tr.weak {{ background:rgba(240,90,60,0.06); }}
.lname {{ font-family: ui-monospace, Menlo, monospace; color:#58a6ff; }}
.lname.pred {{ color:#f0883e; }}
.barbg {{ position:relative; background:#22272e; border-radius:6px; height:20px; min-width:150px; }}
.bar {{ height:100%; border-radius:6px; }}
.bar.p {{ background:#58a6ff; }}
.bar.r {{ background:#bc8cff; }}
.bar.f {{ background:#3fb950; }}
.bar.c {{ background:#f0883e; }}
.barval {{ position:absolute; right:8px; top:0; line-height:20px; font-size:11px; color:#e6edf3; }}
.arrow {{ color:#8b949e; text-align:center; }}
.q {{ color:#c9d1d9; }}
.two {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; align-items:start; }}
@media(max-width:900px){{ .cards{{grid-template-columns:repeat(2,1fr);}} .two{{grid-template-columns:1fr;}} }}
</style>
</head>
<body>
<div class="wrap">
  <h1>意图分类模型评测报告</h1>
  <p class="muted">模型：zc-intent&nbsp;·&nbsp;测试集：test.jsonl&nbsp;·&nbsp;{n} 条&nbsp;·&nbsp;{len(labels)} 个标签</p>
  {cards}

  <h2>混淆矩阵热力图</h2>
  <p class="muted">行 = 真实标签，列 = 预测标签。对角线（绿色）为正确，非对角（橙红）为混淆，颜色深浅按该行占比。</p>
  {matrix_html}
  <div class="legend">
    <span><span class="sw" style="background:rgba(63,185,80,0.8)"></span>正确（对角）</span>
    <span><span class="sw" style="background:rgba(240,90,60,0.8)"></span>混淆（错误）</span>
    <span>__invalid__ = 模型未输出合法标签</span>
  </div>

  <h2>各标签指标（按 F1 升序，&lt;0.85 高亮）</h2>
  <table class="tbl">
    <thead><tr><th>标签</th><th>样本数</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead>
    <tbody>{stat_rows}</tbody>
  </table>

  <div class="two">
    <div>
      <h2>Top 混淆对</h2>
      <table class="tbl">
        <thead><tr><th>真实</th><th></th><th>预测</th><th>数量</th></tr></thead>
        <tbody>{pair_rows}</tbody>
      </table>
    </div>
    <div>
      <h2>错误样例（前 40 / 共 {total_errors} 条）</h2>
      <table class="tbl">
        <thead><tr><th>#</th><th>真实</th><th>预测</th><th>query</th></tr></thead>
        <tbody>{err_rows}</tbody>
      </table>
    </div>
  </div>
</div>
</body>
</html>'''

    out = Path(args.out)
    out.write_text(doc, encoding='utf-8')
    print(f'total={n} acc={acc*100:.2f}% macroF1={macro_f1:.4f}')
    print(f'saved: {out}')


if __name__ == '__main__':
    main()
