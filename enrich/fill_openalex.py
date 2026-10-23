# -*- coding: utf-8 -*-
"""残差兜底（OpenAlex）：对仍未命中的卡片按标题检索，DOI 转论文页/arXiv 链接。

只接受标题相似度 >= 0.9 的结果，避免张冠李戴。
"""
import json, os, re, time, html as H, collections, urllib.parse, urllib.request

ROOT = r'D:\Desktop\study\github_proj\paper-cards'
os.chdir(ROOT)
EN = os.path.join(ROOT, 'enrich')
PROXY = 'http://127.0.0.1:7897'
UA = 'paper-cards/1.0 (mailto:241027149@fzu.edu.cn)'

opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))

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


def q_clean(t):
    """检索词：拼回断词，去标点。"""
    t = H.unescape(t or '')
    t = re.sub(r'\$[^$]*\$', ' ', t)
    t = re.sub(r'(?<=[A-Za-z0-9])[-‐‑–](?=[A-Za-z0-9])', '', t)
    t = re.sub(r'[^A-Za-z0-9 ]+', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def sim(a, b):
    ca, cb = set(tokl(a)), set(tokl(b))
    ja, jb = set(tokl(a, True)), set(tokl(b, True))
    best = 0.0
    for x, y in ((ca, cb), (ja, jb), (ca, jb), (ja, cb)):
        if x and y:
            best = max(best, len(x & y) / float(min(len(x), len(y))))
    return best


def oa_search(title):
    q = q_clean(title)
    if len(q) < 8:
        return None
    if len(q.split()) > 18:
        q = ' '.join(q.split()[:18])
    url = ('https://api.openalex.org/works?filter=title.search:%s'
           '&per_page=3&select=id,title,doi,publication_year,best_oa_location,primary_location'
           % urllib.parse.quote(q))
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            with opener.open(req, timeout=45) as r:
                d = json.loads(r.read().decode('utf-8'))
            break
        except Exception:
            time.sleep(3 * (attempt + 1))
    else:
        return None
    best, best_s = None, 0.0
    for w in d.get('results', []):
        t = w.get('title') or ''
        s = sim(title, t)
        if s > best_s:
            best_s, best = s, w
    if not best or best_s < 0.9:
        return None
    doi = (best.get('doi') or '')
    url = ''
    pdf = ''
    if doi:
        m = re.match(r'https?://doi\.org/10\.48550/[Aa]r?[Xx]iv\.(.+)$', doi)
        if m:
            aid = m.group(1)
            url = 'https://arxiv.org/abs/%s' % aid
            pdf = 'https://arxiv.org/pdf/%s' % aid
        else:
            url = doi
    if not url:
        pl = best.get('primary_location') or {}
        url = pl.get('landing_page_url') or ''
    if not pdf:
        bl = best.get('best_oa_location') or {}
        pdf = bl.get('pdf_url') or ''
    if not url:
        return None
    return url, pdf, round(best_s, 3), best.get('title') or ''


urls = json.load(open(os.path.join(EN, 'urls.json'), encoding='utf-8'))
cards = []
for conf in sorted(os.listdir('data')):
    d = os.path.join('data', conf)
    if not os.path.isdir(d):
        continue
    for fn in os.listdir(d):
        if fn.endswith('.json'):
            cards.append(json.load(open(os.path.join(d, fn), encoding='utf-8')))

miss = [c for c in cards if c['key'] not in urls]
print('待查', len(miss), flush=True)

added = 0
t0 = time.time()
for i, c in enumerate(miss):
    r = oa_search(c['title'])
    if r:
        url, pdf, s, t = r
        urls[c['key']] = {'url': url, 'pdf': pdf, 'src': 'openalex',
                          'match': s, 'title': t}
        added += 1
    if i % 30 == 0:
        print('  %d/%d  命中 %d  %.0fs' % (i, len(miss), added, time.time() - t0), flush=True)
    time.sleep(0.15)

json.dump(urls, open(os.path.join(EN, 'urls.json'), 'w', encoding='utf-8'),
          ensure_ascii=False)
print('补上 %d 条，耗时 %.0fs' % (added, time.time() - t0))
print('覆盖 %d/%d = %.1f%%' % (len(urls), len(cards), 100.0 * len(urls) / len(cards)))
