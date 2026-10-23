# -*- coding: utf-8 -*-
"""用 papercopilot 的 ICLR 2026 全量清单补齐论坛链接 + 代码仓库。

数据源：papercopilot/paperlists 的 iclr/iclr2026.json（19,814 条提交，
含 id / title / site / github / project / status）。
产出：更新 urls.json（iclr2026 链接）与 code.json（github 字段）。
"""
import json, os, re, html as H, collections

ROOT = r'D:\Desktop\study\github_proj\paper-cards'
os.chdir(ROOT)
EN = os.path.join(ROOT, 'enrich')

STOP = set('a an the of for on in with and to via from by is are as at using towards toward '
           'beyond can do does what when why how not all any more most new'.split())


def tokl(t):
    t = H.unescape(t or '').lower()
    t = re.sub(r'\$[^$]*\$', ' ', t)
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return [w for w in t.split() if len(w) > 2 and w not in STOP]


# ---------- 载入 papercopilot ----------
raw = json.load(open(os.path.join(EN, 'iclr2026_pcl.json'), encoding='utf-8'))
print('pcl entries', len(raw))

entries, inv = [], collections.defaultdict(list)
for x in raw:
    title = (x.get('title') or '').strip()
    pid = (x.get('openreview_forum') or x.get('id') or '').strip()
    if not title or not pid:
        continue
    tl = tokl(title)
    if len(tl) < 2:
        continue
    # 撤回的排后面，同标题时优先取正式发表版本
    withdrawn = (x.get('status') or '').lower().startswith('withdraw')
    v = {
        'title': title,
        'url': 'https://openreview.net/forum?id=%s' % pid,
        'pdf': 'https://openreview.net/pdf?id=%s' % pid,
        'src': 'iclr2026-pcl',
        'github': (x.get('github') or '').strip(),
        'project': (x.get('project') or '').strip(),
        'status': (x.get('status') or '').strip(),
        'withdrawn': withdrawn,
    }
    entries.append((tl, set(tl), v))
    for w in set(tl):
        inv[w].append(len(entries) - 1)

# ---------- 载入卡片 ----------
cards = []
for conf in sorted(os.listdir('data')):
    d = os.path.join('data', conf)
    if not os.path.isdir(d):
        continue
    for fn in os.listdir(d):
        if fn.endswith('.json'):
            cards.append(json.load(open(os.path.join(d, fn), encoding='utf-8')))

upath = os.path.join(EN, 'urls.json')
urls = json.load(open(upath, encoding='utf-8'))
before = len(urls)

cpath = os.path.join(EN, 'code.json')
code = json.load(open(cpath, encoding='utf-8')) if os.path.exists(cpath) else {}

GH_RE = re.compile(r'^https?://(www\.)?(github|gitlab|huggingface)\.co', re.I)


def norm_repo(u):
    u = (u or '').strip().rstrip('/')
    m = re.match(r'^https?://(?:www\.)?github\.com/([^/]+)/([^/#?]+)', u, re.I)
    if not m:
        return u
    return 'https://github.com/%s/%s' % (m.group(1), m.group(2))


added_url = added_code = 0
matched = 0
for c in cards:
    if not c['key'].startswith('iclr2026/'):
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
        etl, ets, v = entries[i]
        s = len(ts & ets) / float(min(len(ts), len(ets)))
        # 同分时非撤回优先
        if s > best_s + 1e-9 or (abs(s - best_s) < 1e-9 and best_i >= 0 and entries[best_i][2]['withdrawn'] and not v['withdrawn']):
            best_s, best_i = s, i
    if best_i < 0:
        continue
    etl, ets, v = entries[best_i]
    pre = len(tl) >= 5 and len(etl) >= 5 and tl[:5] == etl[:5]
    if not (best_s >= 0.95 or (best_s >= 0.85 and pre) or best_s >= 0.86):
        continue
    matched += 1
    if c['key'] not in urls:
        rec = {'title': v['title'], 'url': v['url'], 'pdf': v['pdf'],
               'src': v['src'], 'match': round(best_s, 3)}
        if v['project']:
            rec['project'] = v['project']
        urls[c['key']] = rec
        added_url += 1
    g = v['github']
    if g and GH_RE.match(g):
        g = norm_repo(g)
        old = code.get(c['key'])
        if not old or not old.get('code'):
            code[c['key']] = {'code': g, 'src': 'iclr-pcl'}
            added_code += 1

json.dump(urls, open(upath, 'w', encoding='utf-8'), ensure_ascii=False)
json.dump(code, open(cpath, 'w', encoding='utf-8'), ensure_ascii=False)
print('ICLR 卡片匹配上 %d 条' % matched)
print('urls %d -> %d (+%d)' % (before, len(urls), added_url))
print('code 新增 %d 条' % added_code)
tot = sum(1 for c in cards)
print('总覆盖率 %d/%d = %.1f%%' % (len(urls), tot, 100.0 * len(urls) / tot))
