# -*- coding: utf-8 -*-
"""补齐 ICLR 2026（及其它残留）的论文 URL —— OpenReview 搜索，8 并发。"""
import json, os, re, sys, time, threading, queue as Queue
import urllib.parse

ENR = r'D:\Desktop\study\github_proj\paper-cards\enrich'
os.chdir(os.path.dirname(ENR))
sys.path.insert(0, ENR)
import enrich_urls as U

THREADS = 24
STOP = set('a an the of for on in with and to via from by is are as at using towards toward '
           'beyond can do does what when why how not all any more most new'.split())


def tokl(t):
    t = (t or '').lower()
    t = re.sub(r'\$[^$]*\$', ' ', t)
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return [w for w in t.split() if len(w) > 2 and w not in STOP]


def pick(note, title):
    c = note.get('content', {})

    def g(k):
        v = c.get(k, {})
        return v.get('value') if isinstance(v, dict) else v

    nt = g('title') or ''
    a, b = tokl(nt), tokl(title)
    if not b:
        return None
    ov = len(set(a) & set(b))
    if not ov:
        return None
    score = ov / float(min(len(a), len(b)))
    if score < 0.85:
        return None
    fid = note.get('forum') or note.get('id')
    pdf = g('pdf') or ''
    html_u = g('html') or ''
    return {'url': html_u or ('https://openreview.net/forum?id=%s' % fid),
            'pdf': pdf, 'src': 'openreview', 'match': round(score, 3)}


def search(title):
    q = ' '.join(re.findall(r'[A-Za-z0-9\-]+', title)[:12])
    if not q:
        return None
    url = 'https://api2.openreview.net/notes/search?term=%s&limit=5' % urllib.parse.quote(q)
    try:
        raw = U.fetch(url, tries=1, timeout=40).decode('utf-8', 'ignore')
        d = json.loads(raw)
    except Exception:
        return None
    best = None
    for n in d.get('notes', []):
        r = pick(n, title)
        if r and (best is None or r['match'] > best['match']):
            best = r
    return best


def main():
    p = os.path.join(ENR, 'urls.json')
    urls = json.load(open(p, encoding='utf-8'))
    cards = []
    for conf in sorted(os.listdir('data')):
        d = os.path.join('data', conf)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith('.json'):
                cards.append(json.load(open(os.path.join(d, fn), encoding='utf-8')))
    todo = [c for c in cards if c['key'] not in urls]
    print('missing %d / %d  threads=%d' % (len(todo), len(cards), THREADS), flush=True)

    q = Queue.Queue()
    for c in todo:
        q.put(c)
    lock = threading.Lock()
    done = [0]
    t0 = time.time()

    def worker():
        while True:
            try:
                c = q.get_nowait()
            except Queue.Empty:
                return
            r = search(c['title'])
            with lock:
                done[0] += 1
                if r:
                    urls[c['key']] = r
                n = done[0]
                if n % 100 == 0:
                    el = time.time() - t0
                    json.dump(urls, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
                    print('%d/%d  %.0fs  resolved=%d  eta=%.0fmin'
                          % (n, len(todo), el, len(urls),
                             (len(todo) - n) * el / n / 60), flush=True)
            q.task_done()

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(THREADS)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    json.dump(urls, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
    print('DONE resolved %d / %d' % (len(urls), len(cards)), flush=True)


if __name__ == '__main__':
    main()
