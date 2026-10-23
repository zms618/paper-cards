# -*- coding: utf-8 -*-
"""残差兜底：清掉指向被拒/撤稿标题的匹配，剩余卡片逐条走 OpenReview 搜索。

约束：并发 6 + 429 退避，避免再进惩罚期。
"""
import json, os, re, time, html as H, threading, urllib.parse

ROOT = r'D:\Desktop\study\github_proj\paper-cards'
os.chdir(ROOT)
EN = os.path.join(ROOT, 'enrich')
import sys
sys.path.insert(0, EN)
import enrich_urls as U

THREADS = 6
BAD = ('reject', 'withdraw')

# ---------- 载入 papercopilot 做状态过滤 ----------
raw = json.load(open(os.path.join(EN, 'iclr2026_pcl.json'), encoding='utf-8'))
byid = {(x.get('openreview_forum') or x.get('id')): x for x in raw}

upath = os.path.join(EN, 'urls.json')
urls = json.load(open(upath, encoding='utf-8'))

dropped = 0
for k, v in list(urls.items()):
    if v.get('src') != 'iclr2026-pcl':
        continue
    m = re.search(r'id=([A-Za-z0-9_\-]+)', v['url'])
    st = (byid.get(m.group(1), {}).get('status') or '') if m else ''
    if any(b in st.lower() for b in BAD):
        del urls[k]
        dropped += 1
print('剔除指向被拒/撤稿的匹配:', dropped)

# ---------- 载入卡片 ----------
cards = []
for conf in sorted(os.listdir('data')):
    d = os.path.join('data', conf)
    if not os.path.isdir(d):
        continue
    for fn in os.listdir(d):
        if fn.endswith('.json'):
            cards.append(json.load(open(os.path.join(d, fn), encoding='utf-8')))

miss = [c for c in cards if c['key'] not in urls]
print('待兜底', len(miss))


def tokl(t):
    t = H.unescape(t or '').lower()
    t = re.sub(r'\$[^$]*\$', ' ', t)
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return [w for w in t.split() if len(w) > 2]


def or_search(title):
    """返回 (forum_id, title, pdf) 或 None。"""
    tl = tokl(title)
    if len(tl) < 3:
        return None
    q = ' '.join(tl[:12])
    url = 'https://api2.openreview.net/notes/search?term=%s&limit=8' % urllib.parse.quote(q)
    for attempt in range(4):
        try:
            js = json.loads(U.fetch(url, tries=1, timeout=40))
            break
        except Exception as ex:
            code = getattr(ex, 'code', None)
            if code == 429:
                time.sleep(8 * (attempt + 1))
                continue
            return None
    else:
        return None
    best, best_s = None, 0.0
    ts = set(tl)
    for n in js.get('notes', []):
        c = n.get('content', {})
        t = c.get('title')
        t = t.get('value') if isinstance(t, dict) else t
        if not t:
            continue
        et = set(tokl(t))
        if not et:
            continue
        s = len(ts & et) / float(min(len(ts), len(et)))
        if s > best_s:
            best_s, best = s, n
    if best and best_s >= 0.9:
        f = best.get('forum') or best.get('id')
        return ('https://openreview.net/forum?id=%s' % f,
                'https://openreview.net/pdf?id=%s' % f, round(best_s, 3))
    return None


lock = threading.Lock()
added = [0]
errs = [0]
idx = [0]


def worker():
    while True:
        with lock:
            if idx[0] >= len(miss):
                return
            i = idx[0]
            idx[0] += 1
        c = miss[i]
        try:
            r = or_search(c['title'])
        except Exception:
            r = None
            with lock:
                errs[0] += 1
        if r:
            with lock:
                urls[c['key']] = {'url': r[0], 'pdf': r[1],
                                  'src': 'openreview-search', 'match': r[2]}
                added[0] += 1


t0 = time.time()
ths = [threading.Thread(target=worker, daemon=True) for _ in range(THREADS)]
for t in ths:
    t.start()
for t in ths:
    t.join()

json.dump(urls, open(upath, 'w', encoding='utf-8'), ensure_ascii=False)
print('兜底补上 %d 条（错误 %d），耗时 %.0fs' % (added[0], errs[0], time.time() - t0))
print('覆盖 %d/%d = %.1f%%' % (len(urls), len(cards), 100.0 * len(urls) / len(cards)))
