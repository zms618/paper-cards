# -*- coding: utf-8 -*-
"""把模糊匹配结果合并进 urls.json（对截断标题鲁棒，带前缀校验）。"""
import json, os, re, html as H, collections
import enrich_urls as U

ROOT = r'D:\Desktop\study\github_proj\paper-cards'
os.chdir(ROOT)
cards = []
for conf in sorted(os.listdir('data')):
    d = os.path.join('data', conf)
    if not os.path.isdir(d):
        continue
    for fn in os.listdir(d):
        if fn.endswith('.json'):
            cards.append(json.load(open(os.path.join(d, fn), encoding='utf-8')))

STOP = set('a an the of for on in with and to via from by is are as at using towards toward '
           'beyond can do does what when why how not all any more most new'.split())


def tokl(t):
    t = H.unescape(t or '').lower()
    t = re.sub(r'\$[^$]*\$', ' ', t)
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return [w for w in t.split() if len(w) > 2 and w not in STOP]


idx_raw = {}
for loader in (lambda: U.load_cvf('CVPR2026', 'cvpr2026'),
               lambda: U.load_cvf('CVPR2025', 'cvpr2025'),
               lambda: U.load_cvf('ICCV2025', 'iccv2025'),
               U.load_neurips, U.load_pmlr):
    idx_raw.update(loader())

entries, inv = [], collections.defaultdict(list)
for i, (nt, v) in enumerate(idx_raw.items()):
    tl = tokl(v.get('title') or nt)
    entries.append((tl, set(tl), v))
    for w in set(tl):
        inv[w].append(i)

p = os.path.join(ROOT, 'enrich', 'urls.json')
data = json.load(open(p, encoding='utf-8'))
before = len(data)
added = 0
for c in cards:
    if c['key'] in data:
        continue
    tl = tokl(c['title'])
    if len(tl) < 3:
        continue
    ts = set(tl)
    cnt = collections.Counter()
    for w in ts:
        for i in inv.get(w, ()):
            cnt[i] += 1
    best_i, best_s = -1, 0.0
    for i, _ov in cnt.most_common(20):
        etl, ets, _v = entries[i]
        s = len(ts & ets) / float(min(len(ts), len(ets)))
        if s > best_s:
            best_s, best_i = s, i
    if best_i < 0:
        continue
    etl, ets, ev = entries[best_i]
    pre = len(tl) >= 5 and len(etl) >= 5 and tl[:5] == etl[:5]
    if best_s >= 0.95 or (best_s >= 0.85 and pre) or best_s >= 0.86:
        data[c['key']] = dict(ev, src=ev.get('src', '') + '+fuzzy',
                              match=round(best_s, 3))
        added += 1

json.dump(data, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
print('urls %d -> %d  (+%d)' % (before, len(data), added))
print('still missing', len(cards) - len(data))
