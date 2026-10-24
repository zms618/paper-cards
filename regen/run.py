"""卡片 v3（速读卡）批量重生成器。

流程：读 v1 卡片 -> 找到 PDF（linkmap 官方链接或本地 pdf 目录）-> pymupdf 抽文本
      -> 调 OpenAI 兼容端点（vLLM / Ollama / 任意 API）-> validate -> 落盘

用法（本地 vLLM 示例）：
    python regen/run.py --limit 20 --base-url http://127.0.0.1:8000/v1 --model Qwen3-VL-32B-Instruct
    python regen/run.py --confs cvpr2025,iclr2026 --limit 200 --workers 2 --resume
    python regen/run.py --slugs "cvpr2026/Thinking in Uncertainty.pdf" --dry

输出：
    regen/out/<conf>/<slug>.json      通过的卡片（v1 全字段 + v3 字段，v=3）
    regen/rejected/<conf>/<slug>.json 未通过校验的，附 _errors
"""
import argparse
import glob
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from regen.validate import check  # noqa: E402

PROMPT = open(os.path.join(ROOT, 'regen', 'PROMPT.md'), encoding='utf-8').read()
MAX_CHARS = 45000          # 送进模型的正文上限（约 12k token）
WANT_SECTIONS = ('abstract', 'introduction', 'method', 'approach', 'experiment',
                 'result', 'conclusion', 'analysis', 'ablation')


def pdf_text(pdf_path, max_chars=MAX_CHARS):
    """抽文本并做轻量裁剪：优先保留摘要/引言/方法/实验/结论段"""
    import pymupdf
    doc = pymupdf.open(pdf_path)
    pages = [p.get_text() for p in doc]
    full = '\n'.join(pages)
    if len(full) <= max_chars:
        return full
    # 头尾拼接：前面 60%（摘要/引言/方法）+ 后面 40%（实验/结论）
    head = int(max_chars * 0.6)
    return full[:head] + '\n\n[...中间省略...]\n\n' + full[-(max_chars - head):]


def find_pdf(card, linkmap, pdf_dirs):
    key = card['key']
    for d in pdf_dirs:
        p = os.path.join(d, card['path'])
        if os.path.exists(p):
            return p
    url = (linkmap.get(key) or {}).get('pdf')
    if url:
        return url
    return None


def call_llm(text, base_url, model, api_key, timeout=600):
    import urllib.request
    payload = {
        'model': model,
        'messages': [{'role': 'user', 'content': PROMPT.replace('<<<PAPER_TEXT>>>', text)}],
        'temperature': 0.3,
        'max_tokens': 5200,
    }
    req = urllib.request.Request(
        base_url.rstrip('/') + '/chat/completions',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Bearer ' + (api_key or 'none')})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read())
    raw = d['choices'][0]['message']['content']
    m = re.search(r'\{.*\}', raw, re.S)
    if not m:
        raise ValueError('模型没有返回 JSON: ' + raw[:200])
    return json.loads(m.group(0))


def one(card_path, args, linkmap):
    card = json.load(open(card_path, encoding='utf-8'))
    out = os.path.join(args.out, card['conf'], os.path.basename(card_path))
    rej = os.path.join(args.rejected, card['conf'], os.path.basename(card_path))
    if args.resume and (os.path.exists(out) or os.path.exists(rej)):
        return 'skip', os.path.basename(card_path)

    pdf = find_pdf(card, linkmap, args.pdf_dirs)
    if not pdf:
        return 'nopdf', card['key']
    try:
        if pdf.startswith('http'):
            import tempfile
            import urllib.request
            tmp = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
            urllib.request.urlretrieve(pdf, tmp.name)
            text = pdf_text(tmp.name)
            os.unlink(tmp.name)
        else:
            text = pdf_text(pdf)
    except Exception as e:
        return 'pdferr', f'{card["key"]}: {e}'

    if args.dry:
        print(f'[dry] {card["key"]} text={len(text)} chars')
        return 'dry', card['key']

    try:
        v3 = call_llm(text, args.base_url, args.model, args.api_key)
    except Exception as e:
        return 'llmerr', f'{card["key"]}: {e}'

    merged = dict(card)
    V3_KEYS = ('tldr', 'task', 'motivation', 'idea', 'method_overview', 'designs',
               'setup', 'results_table', 'nums', 'findings', 'insights', 'limits',
               'why_me', 'related')
    merged.update({k: v3.get(k, '' if k not in ('motivation', 'method_overview', 'designs',
                                                'nums', 'findings', 'insights', 'limits',
                                                'related', 'results_table') else [])
                   for k in V3_KEYS})
    # 统一类型，避免模型偷懒把数组写成字符串
    for k in ('motivation', 'method_overview', 'designs', 'nums', 'findings',
              'insights', 'limits', 'related'):
        if isinstance(merged.get(k), str):
            merged[k] = [merged[k]] if merged[k].strip() else []
    if not isinstance(merged.get('results_table'), dict):
        merged['results_table'] = {'cols': [], 'rows': [], 'note': ''}
    merged['v'] = 3
    merged['model'] = args.model
    errs = check(merged)
    if errs:
        merged['_errors'] = errs
        os.makedirs(os.path.dirname(rej), exist_ok=True)
        json.dump(merged, open(rej, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        return 'rejected', f'{card["key"]}: {errs[:2]}'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(merged, open(out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    return 'ok', card['key']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--confs', default='cvpr2025,cvpr2026,iccv2025,iclr2026,icml2025,neurips2025')
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--workers', type=int, default=1, help='vLLM 单卡建议 2-4')
    ap.add_argument('--base-url', default='http://127.0.0.1:8000/v1')
    ap.add_argument('--model', default='Qwen3-VL-32B-Instruct')
    ap.add_argument('--api-key', default='')
    ap.add_argument('--pdf-dirs', nargs='*', default=['data'])
    ap.add_argument('--out', default=os.path.join(ROOT, 'regen', 'out'))
    ap.add_argument('--rejected', default=os.path.join(ROOT, 'regen', 'rejected'))
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--dry', action='store_true')
    args = ap.parse_args()

    linkmap = {}
    lm = os.path.join(ROOT, 'enrich', 'linkmap.json')
    if os.path.exists(lm):
        linkmap = json.load(open(lm, encoding='utf-8'))

    files = []
    for conf in args.confs.split(','):
        files.extend(sorted(glob.glob(os.path.join(ROOT, 'data', conf, '*.json'))))
    done = set()
    for p in glob.glob(os.path.join(args.out, '*', '*.json')) + glob.glob(os.path.join(args.rejected, '*', '*.json')):
        done.add((os.path.basename(os.path.dirname(p)), os.path.basename(p)))
    files = [f for f in files if (os.path.basename(os.path.dirname(f)), os.path.basename(f)) not in done]
    if args.limit:
        files = files[:args.limit]
    print(f'待处理 {len(files)} 篇，端点 {args.base_url}，并发 {args.workers}')

    t0 = time.time()
    stat = {}
    with ThreadPoolExecutor(args.workers) as ex:
        for i, (r, info) in enumerate(ex.map(lambda f: one(f, args, linkmap), files), 1):
            stat[r] = stat.get(r, 0) + 1
            if r not in ('ok', 'skip'):
                print(f'  [{r}] {info}')
            if i % 20 == 0:
                print(f'  ... {i}/{len(files)}  {stat}  {time.time()-t0:.0f}s')
    print('完成', stat, f'{time.time()-t0:.0f}s')


if __name__ == '__main__':
    main()
