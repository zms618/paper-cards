"""卡片 v2 校验器 —— 严格按 regen/SPEC.md 的字段长度与内容规则检查。

用法：
    python regen/validate.py regen/demo/*.json
    python regen/validate.py data/cvpr2026/*.json --sample 50
"""
import argparse
import glob
import json
import re
import sys

# 字段 -> (最小长度, 最大长度)；None 表示不限
LIMITS = {
    'task': (20, 60),
    'problem': (60, 160),
    'idea': (40, 120),
    'how': (120, 300),
    'setup': (60, 220),
    'limits': (60, 240),
    'why_me': (0, 120),
}
JUDGE_WORDS = ['有限', '不足', '一般', '较差', '存疑', '但', '然而', '偏弱', '较弱']
NO_METHOD_IN = {'task', 'problem'}


def _method_names(title):
    """标题里的大写缩写（≥3 字母）当作方法名，如 LEAD / SCFR / TG-WSPIS"""
    return {w.upper() for w in re.findall(r'\b[A-Za-z][A-Za-z0-9\-]{2,}\b', title or '')
            if sum(ch.isupper() for ch in w) >= 2}


def check(card):
    errs = []
    for k, (lo, hi) in LIMITS.items():
        v = (card.get(k) or '')
        if k == 'why_me' and not v:
            continue
        if not v:
            errs.append(f'缺字段 {k}')
            continue
        if not isinstance(v, str):
            errs.append(f'{k} 不是字符串')
            continue
        n = len(v.strip())
        if n < lo:
            errs.append(f'{k} 太短 {n}<{lo}')
        if n > hi:
            errs.append(f'{k} 太长 {n}>{hi}')

    nums = card.get('nums') or []
    if not isinstance(nums, list) or not (2 <= len(nums) <= 4):
        errs.append(f'nums 需 2-4 条，当前 {len(nums)}')
    for i, x in enumerate(nums):
        if not re.search(r'\d', str(x)):
            errs.append(f'nums[{i}] 不含数字')
        if len(str(x)) > 70:
            errs.append(f'nums[{i}] 超过 70 字')

    for k in NO_METHOD_IN:
        v = card.get(k) or ''
        for jw in JUDGE_WORDS:
            if jw in v:
                errs.append(f'{k} 含评价词「{jw}」')

    names = _method_names(card.get('title'))
    task = card.get('task') or ''
    hit = [w for w in names if re.search(r'\b' + re.escape(w) + r'\b', task, re.I)]
    if hit:
        errs.append(f'task 出现方法名 {hit}')

    blob = ' '.join([card.get(k) or '' for k in ('task', 'problem', 'idea', 'how', 'setup', 'limits')]
                    + [str(x) for x in nums])
    if len(re.findall(r'\d', blob)) < 3:
        errs.append('全文数字少于 3 个')

    return errs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--sample', type=int, default=0, help='只抽查前 N 个文件')
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
        errs = check(card)
        if errs:
            bad += 1
            print(f'[FAIL] {f}')
            for e in errs:
                print(f'       - {e}')
        else:
            ok += 1
    print(f'\n通过 {ok} / 失败 {bad} / 共 {len(files)}')
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
