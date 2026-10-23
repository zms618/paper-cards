# -*- coding: utf-8 -*-
"""重匹配剩余未命中卡片。

根因：卡片标题来自 PDF 抽取，含断词连字符（SIMI-LARITIES / COLLABORA-TION /
TA-BLE），被切碎成两个残词，overlap 系数被拉低。
做法：对每条候选同时用「连字符→空格」和「连字符→删除」两种分词，取较高分。
"""
import json, os, re, html as H, collections, sys

ROOT = r'D:\Desktop\study\github_proj\paper-cards'
os.chdir(ROOT)
EN = os.path.join(ROOT, 'enrich')
sys.path.insert(0, EN)
import enrich_urls as U

STOP = set('a an the of for on in with and to via from by is are as at using towards toward '
           'beyond can do does what when why how not all any more most new'.split())


def tokl(t, join_hy=False):
    t = H.unescape(t or '')
    t = re.sub(r'\$[^$]*\$', ' ', t)
    if join_hy:
        t = re.sub(r'(?<=[A-Za-z0-9])[-‐‑–](?=[A-Za-z0-9])', '', t)
    t = t.lower()
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return [w for w in t.split() if len(w) > 2 and w not in STOP]


def build(records):
    """records: [(title, payload)] -> (entries, inv)"""
    entries, inv = [], collections.defaultdict(list)
    for title, v in records:
        la, lb = tokl(title), tokl(title, True)
        if len(la) < 2 and len(lb) < 2:
            continue
        sa, sb = set(la), set(lb)
        entries.append((la, sa, lb, sb, v))
        for w in sa | sb:
            inv[w].append(len(entries) - 1)
    return entries, inv


def score(card_title, ent):
    la, sa, lb, sb, _v = ent
    ca, cb = set(tokl(card_title)), set(tokl(card_title, True))
    vals = []
    for c, e in ((ca, sa), (cb, sb), (ca, sb), (cb, sa)):
        if c and e:
            vals.append(len(c & e) / float(min(len(c), len(e))))
    return max(vals) if vals else 0.0


def best(card_title, entries, inv):
    c = set(tokl(card_title)) | set(tokl(card_title, True))
    if len(c) < 3:
        return 0.0, None
    cnt = collections.Counter()
    for w in c:
        for i in inv.get(w, ()):
            cnt[i] += 1
    bs, be = 0.0, None
    for i, _n in cnt.most_common(30):
        s = score(card_title, entries[i])
        if s > bs:
            bs, be = s, entries[i]
    return bs, be


# ---------- 索引 ----------
recs_all = []
for loader in (lambda: U.load_cvf('CVPR2026', 'cvpr2026'),
               lambda: U.load_cvf('CVPR2025', 'cvpr2025'),
               lambda: U.load_cvf('ICCV2025', 'iccv2025'),
               U.load_neurips, U.load_pmlr):
    for nt, v in loader().items():
        recs_all.append((v.get('title') or nt, v))

pcl = json.load(open(os.path.join(EN, 'iclr2026_pcl.json'), encoding='utf-8'))
for x in pcl:
    t = (x.get('title') or '').strip()
    pid = x.get('openreview_forum') or x.get('id')
    if not t or not pid:
        continue
    recs_all.append((t, {
        'url': 'https://openreview.net/forum?id=%s' % pid,
        'pdf': 'https://openreview.net/pdf?id=%s' % pid,
        'src': 'iclr2026-pcl',
        'status': (x.get('status') or '').strip(),
    }))

entries, inv = build(recs_all)
print('索引条目', len(entries))

# ---------- 卡片 ----------
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
miss = [c for c in cards if c['key'] not in urls]

added = 0
low = 0
for c in miss:
    s, e = best(c['title'], entries, inv)
    if not e:
        low += 1
        continue
    _la, _sa, _lb, _sb, v = e
    if any(b in (v.get('status') or '').lower() for b in ('reject', 'withdraw')):
        low += 1
        continue
    ct = tokl(c['title'])
    et = tokl(v.get('title') or ' '.join(_lb), True)
    pre = len(ct) >= 5 and len(et) >= 5 and ct[:5] == et[:5]
    if s >= 0.95 or (s >= 0.85 and pre) or s >= 0.97:
        rec = {'url': v['url'], 'pdf': v['pdf'],
               'src': (v.get('src') or '') + '+v2', 'match': round(s, 3)}
        if v.get('title'):
            rec['title'] = v['title']
        urls[c['key']] = rec
        added += 1
    else:
        low += 1

json.dump(urls, open(upath, 'w', encoding='utf-8'), ensure_ascii=False)
print('miss %d  ->  补上 %d，仍缺 %d' % (len(miss), added, len(cards) - len(urls)))
print('覆盖 %d/%d = %.1f%%' % (len(urls), len(cards), 100.0 * len(urls) / len(cards)))
