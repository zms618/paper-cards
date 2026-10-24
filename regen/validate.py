"""卡片校验器 —— 按 regen/SPEC.md 检查 v3（速读卡），兼容 v2 老卡。

用法：
    python regen/validate.py "regen/out/*/*.json"
    python regen/validate.py "data/cvpr2026/*.json" --sample 50
    python regen/validate.py regen/demo/lead.v3.json -v
"""
import argparse
import glob
import json
import re
import sys

# ---- 字符串字段：(最小, 最大) ----
STR_LIMITS = {
    'tldr': (90, 300),
    'task': (20, 70),
    'idea': (40, 160),
    'setup': (60, 320),
    'why_me': (0, 150),        # 允许空
}
# ---- 列表字段：(最少条, 最多条, 单条最短, 单条最长) ----
LIST_LIMITS = {
    'motivation': (2, 5, 20, 200),
    'method_overview': (2, 5, 20, 220),
    'designs': (2, 5, 30, 320),
    'findings': (2, 5, 15, 200),
    'insights': (2, 4, 15, 200),
    'limits': (2, 5, 15, 200),
    'related': (2, 3, 15, 240),   # h + note 合计
}
JUDGE_WORDS = ['有限', '不足', '一般', '较差', '存疑', '偏弱', '较弱']
NO_METHOD_IN = ('task', 'motivation')


def _method_names(title):
    """标题里的全大写缩写（≥3 字母）当作方法名，如 LEAD / SCFR / LLaVA"""
    return {w.upper() for w in re.findall(r'\b[A-Za-z][A-Za-z0-9\-]{2,}\b', title or '')
            if sum(ch.isupper() for ch in w) >= 2}


def _dd_items(seq):
    """把 [{"h":..,"d":..}] 或 [{"h":..,"note":..}] 统一成 [(h, body)]"""
    out = []
    for x in seq or []:
        if isinstance(x, dict):
            body = x.get('d') or x.get('note') or ''
            out.append((str(x.get('h') or ''), str(body)))
        else:
            out.append(('', str(x)))
    return out


def check(card, verbose=False):
    errs = []
    v = card.get('v') or 1
    if v < 3:
        errs.append(f'不是 v3 卡（v={v}），本校验器只验 v3')

    # 1) 字符串字段
    for k, (lo, hi) in STR_LIMITS.items():
        s = card.get(k)
        if s is None:
            errs.append(f'缺字段 {k}')
            continue
        if not isinstance(s, str):
            errs.append(f'{k} 不是字符串')
            continue
        s = s.strip()
        if k == 'why_me' and not s:
            continue
        n = len(s)
        if n < lo:
            errs.append(f'{k} 太短 {n}<{lo}')
        if n > hi:
            errs.append(f'{k} 太长 {n}>{hi}')

    # 2) 列表字段
    for k, (lo, hi, dmin, dmax) in LIST_LIMITS.items():
        seq = card.get(k)
        if not isinstance(seq, list):
            errs.append(f'{k} 应为数组')
            continue
        if not (lo <= len(seq) <= hi):
            errs.append(f'{k} 条数 {len(seq)} 不在 {lo}-{hi}')
        for i, (h, d) in enumerate(_dd_items(seq)):
            total = len(h) + len(d)
            if k in ('findings', 'insights', 'limits'):
                total = len(d or h)
            if total < dmin:
                errs.append(f'{k}[{i}] 太短 {total}<{dmin}')
            if total > dmax:
                errs.append(f'{k}[{i}] 太长 {total}>{dmax}')
            if k in ('motivation', 'method_overview', 'designs', 'related'):
                if not h:
                    errs.append(f'{k}[{i}] 缺 h')

    # 3) 结果表
    rt = card.get('results_table') or {}
    cols = rt.get('cols') if isinstance(rt, dict) else None
    rows = rt.get('rows') if isinstance(rt, dict) else None
    if not cols or not isinstance(cols, list):
        errs.append('results_table.cols 缺失')
    elif len(cols) < 3:
        errs.append(f'results_table 列数 {len(cols)}<3')
    if not rows or not isinstance(rows, list):
        errs.append('results_table.rows 缺失')
    else:
        if not (2 <= len(rows) <= 10):
            errs.append(f'results_table 行数 {len(rows)} 不在 2-10')
        bad_len = [i for i, r in enumerate(rows) if not isinstance(r, list) or len(r) != len(cols or [])]
        if bad_len:
            errs.append(f'results_table 第 {bad_len[:3]} 行列数与 cols 不符')
        with_num = sum(1 for r in rows if isinstance(r, list) and re.search(r'\d', ' '.join(map(str, r))))
        if with_num < max(2, len(rows) // 2):
            errs.append(f'results_table 含数字行仅 {with_num}/{len(rows)}')

    # 4) nums
    nums = card.get('nums') or []
    if not isinstance(nums, list) or not (2 <= len(nums) <= 5):
        errs.append(f'nums 需 2-5 条，当前 {len(nums)}')
    for i, x in enumerate(nums):
        if not re.search(r'\d', str(x)):
            errs.append(f'nums[{i}] 不含数字')
        if len(str(x)) > 80:
            errs.append(f'nums[{i}] 超过 80 字')

    # 5) task / motivation 禁方法名
    names = _method_names(card.get('title'))
    task = card.get('task') or ''
    hit = [w for w in names if re.search(r'\b' + re.escape(w) + r'\b', task, re.I)]
    if hit:
        errs.append(f'task 出现方法名 {hit}')
    blk = ' '.join([h + d for h, d in _dd_items(card.get('motivation'))])
    hit2 = [w for w in names if len(w) > 3 and re.search(r'\b' + re.escape(w) + r'\b', blk, re.I)]
    if hit2:
        errs.append(f'motivation 出现方法名 {hit2}')

    # 6) task / tldr 禁判决词
    for k in ('task', 'tldr'):
        s = card.get(k) or ''
        for jw in JUDGE_WORDS:
            if jw in s:
                errs.append(f'{k} 含评价词「{jw}」')

    # 7) 数字总量
    blob = ' '.join([card.get(k) or '' for k in ('tldr', 'task', 'idea', 'setup')]
                    + [str(x) for x in nums]
                    + [str(x) for x in (card.get('findings') or [])]
                    + [str(c) for c in (cols or [])]
                    + [' '.join(map(str, r)) for r in (rows or []) if isinstance(r, list)])
    ndig = len(re.findall(r'\d', blob))
    if ndig < 20:
        errs.append(f'全卡数字过少（{ndig} 个字符）')

    if verbose:
        print(f'  tldr={len(card.get("tldr") or "")} task={len(card.get("task") or "")} '
              f'table={len(rows or [])}x{len(cols or [])} nums={len(nums)} '
              f'findings={len(card.get("findings") or [])} digits={ndig}')
    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--sample', type=int, default=0, help='只抽查前 N 个文件')
    ap.add_argument('-v', '--verbose', action='store_true')
    args = ap.parse_args()

    files = []
    for p in args.paths:
        files.extend(sorted(glob.glob(p)))
    if args.sample:
        files = files[:args.sample]

    ok = bad = 0
    for f in files:
        try:
            card = json.load(open(f, encoding='utf-8'))
        except Exception as e:
            print(f'[ERR ] {f}: JSON 解析失败 {e}')
            bad += 1
            continue
        errs = check(card, args.verbose)
        if errs:
            bad += 1
            print(f'[FAIL] {f}')
            for e in errs:
                print(f'       - {e}')
        else:
            ok += 1
            if args.verbose:
                print(f'[ OK ] {f}')
    print(f'\n通过 {ok} / 失败 {bad} / 共 {len(files)}')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
