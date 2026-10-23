# -*- coding: utf-8 -*-
"""为 paper-cards 的 21332 张卡片批量补齐论文 URL。

数据源（优先级从高到低）：
  1. OpenReview API 搜索（ICLR/ICML/NeurIPS 有 forum 页，CVPR/ICCV 也收录但指向 CVF）
  2. CVF Open Access 官方索引（CVPR2025 / ICCV2025 / CVPR2026）——openaccess 页 + DOI
  3. NeurIPS proceedings 官方索引（vol38-main-conference）
  4. PMLR 官方索引（ICML 2025 = v267）
  5. arXiv API（兜底，按标题精确匹配）

输出：
  enrich/urls.json   {key: {"url":..., "pdf":..., "src":...}}
  enrich/report.txt  覆盖率报告
"""
import json, os, re, sys, html as htmllib
import urllib.request, urllib.parse, urllib.error

ROOT = r'D:\Desktop\study\github_proj\paper-cards'
ENR = os.path.join(ROOT, 'enrich')
PROXY = 'http://127.0.0.1:7897'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
os.makedirs(ENR, exist_ok=True)

_opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))
_opener.addheaders = [('User-Agent', UA), ('Accept-Language', 'en-US,en;q=0.9')]


def fetch(url, tries=4, timeout=60):
    last = None
    for i in range(tries):
        try:
            with _opener.open(url, timeout=timeout) as r:
                return r.read()
        except Exception as e:
            last = e
            import time
            time.sleep(1.5 * (i + 1))
    raise last


def norm_title(t):
    t = htmllib.unescape(t or '').lower()
    t = re.sub(r'&[a-z]+;', ' ', t)
    t = re.sub(r'[^a-z0-9]+', '', t)
    return t


# ---------------- 索引抓取 ----------------
def cached(name, url):
    p = os.path.join(ENR, name)
    if os.path.exists(p) and os.path.getsize(p) > 1000:
        return open(p, 'rb').read()
    raw = fetch(url)
    open(p, 'wb').write(raw)
    return raw


def load_cvf(year_url, tag):
    """CVF 索引 -> [(norm_title, url, pdf)]"""
    raw = cached('cvf_%s.html' % tag,
                 'https://openaccess.thecvf.com/%s?day=all' % tag).decode('utf-8', 'ignore')
    out = {}
    for m in re.finditer(r'<a href="(/content/[^"]+_paper\.html)">(.*?)</a>', raw, re.S):
        u, t = m.group(1), re.sub('<[^>]+>', '', m.group(2))
        out[norm_title(t)] = {
            'title': re.sub(r'\s+', ' ', htmllib.unescape(t)).strip(),
            'url': 'https://openaccess.thecvf.com' + u,
            'pdf': 'https://openaccess.thecvf.com' + u.replace('/html/', '/papers/').replace('_paper.html', '_paper.pdf'),
            'src': tag,
        }
    return out


def load_neurips():
    raw = cached('nips2025_main.html',
                 'https://proceedings.neurips.cc/paper_files/paper/2025/vol38-main-conference'
                 ).decode('utf-8', 'ignore')
    out = {}
    for m in re.finditer(r'<a title="paper title" href="([^"]+)">(.*?)</a>', raw, re.S):
        u, t = m.group(1), re.sub('<[^>]+>', '', m.group(2))
        full = 'https://proceedings.neurips.cc' + u
        out[norm_title(t)] = {'title': re.sub(r'\s+', ' ', htmllib.unescape(t)).strip(),
                              'url': full, 'pdf': full.replace('-Abstract-', '-Paper-').replace('.html', '.pdf'),
                              'src': 'neurips2025'}
    return out


def load_pmlr():
    raw = cached('mlr_v267.html', 'https://proceedings.mlr.press/v267/').decode('utf-8', 'ignore')
    out = {}
    for blk in raw.split('<div class="paper">')[1:]:
        mt = re.search(r'<p class="title">(.*?)</p>', blk, re.S)
        if not mt:
            continue
        title = re.sub('<[^>]+>', '', mt.group(1)).strip()
        mu = re.search(r'href="(https://proceedings\.mlr\.press/v267/[^"]+\.html)"', blk)
        mpdf = re.search(r'href="(https://raw\.githubusercontent\.com/mlresearch/v267/[^"]+\.pdf)"', blk)
        mor = re.search(r'href="(https://openreview\.net/forum\?id=[^"]+)"', blk)
        if not mu:
            continue
        out[norm_title(title)] = {
            'title': title,
            'url': mor.group(1) if mor else mu.group(1),
            'pdf': mpdf.group(1) if mpdf else mu.group(1),
            'src': 'icml2025',
        }
    return out


def openreview_search(title, limit=5):
    q = ' '.join(re.findall(r'[A-Za-z0-9\-]+', title)[:12])
    url = 'https://api2.openreview.net/notes/search?term=%s&limit=%d&source=forum' % (urllib.parse.quote(q), limit)
    try:
        d = json.loads(fetch(url, tries=3, timeout=45))
    except Exception:
        return None
    nt = norm_title(title)
    for n in d.get('notes', []):
        c = n.get('content', {})
        ct = c.get('title', {})
        ct = ct.get('value') if isinstance(ct, dict) else ct
        if norm_title(ct) == nt:
            fid = n.get('forum') or n.get('id')
            pdf = c.get('pdf', {})
            pdf = pdf.get('value') if isinstance(pdf, dict) else pdf
            html_u = c.get('html', {})
            html_u = html_u.get('value') if isinstance(html_u, dict) else html_u
            return {'url': html_u or ('https://openreview.net/forum?id=' + fid),
                    'pdf': pdf or '', 'src': 'openreview'}
    return None


def arxiv_search(title):
    t = re.sub(r'[^\w\s\-]', ' ', title)
    t = ' '.join(t.split()[:14])
    q = 'ti:"%s"' % t
    url = 'http://export.arxiv.org/api/query?search_query=%s&max_results=5' % urllib.parse.quote(q)
    try:
        raw = fetch(url, tries=3, timeout=45).decode('utf-8', 'ignore')
    except Exception:
        return None
    nt = norm_title(title)
    for m in re.finditer(r'<entry>(.*?)</entry>', raw, re.S):
        e = m.group(1)
        mt = re.search(r'<title>(.*?)</title>', e, re.S)
        mi = re.search(r'<id>(.*?)</id>', e)
        if not mt or not mi:
            continue
        if norm_title(mt.group(1)) == nt:
            u = mi.group(1).replace('http://', 'https://')
            u = re.sub(r'v\d+$', '', u)
            return {'url': u, 'pdf': u.replace('/abs/', '/pdf/'), 'src': 'arxiv'}
    return None


def main():
    cards = []
    ddir = os.path.join(ROOT, 'data')
    for conf in sorted(os.listdir(ddir)):
        cd = os.path.join(ddir, conf)
        if not os.path.isdir(cd):
            continue
        for fn in os.listdir(cd):
            if not fn.endswith('.json'):
                continue
            j = json.load(open(os.path.join(cd, fn), encoding='utf-8'))
            cards.append(j)
    print('cards', len(cards), flush=True)

    print('building indexes...', flush=True)
    idx = {}
    idx.update(load_cvf('CVPR2026', 'cvpr2026'))
    print('  cvpr2026', len(idx), flush=True)
    n0 = len(idx)
    idx.update(load_cvf('CVPR2025', 'cvpr2025'))
    print('  +cvpr2025 ->', len(idx), flush=True)
    idx.update(load_cvf('ICCV2025', 'iccv2025'))
    print('  +iccv2025 ->', len(idx), flush=True)
    idx.update(load_neurips())
    print('  +neurips2025 ->', len(idx), flush=True)
    idx.update(load_pmlr())
    print('  +icml2025 ->', len(idx), flush=True)

    res, miss = {}, []
    for c in cards:
        nt = norm_title(c['title'])
        hit = idx.get(nt)
        if hit:
            res[c['key']] = dict(hit)
        else:
            miss.append(c)
    print('index hit %d / miss %d' % (len(res), len(miss)), flush=True)

    # 阶段 2：OpenReview
    still = []
    for i, c in enumerate(miss):
        hit = openreview_search(c['title'])
        if hit:
            res[c['key']] = hit
        else:
            still.append(c)
        if i % 50 == 0:
            print('  openreview %d/%d  hit=%d' % (i, len(miss), len(res)), flush=True)
            json.dump(res, open(os.path.join(ENR, 'urls.json'), 'w', encoding='utf-8'),
                      ensure_ascii=False)
    print('after openreview: hit %d / still %d' % (len(res), len(still)), flush=True)
    json.dump(res, open(os.path.join(ENR, 'urls.json'), 'w', encoding='utf-8'), ensure_ascii=False)

    # 阶段 3：arXiv
    still2 = []
    for i, c in enumerate(still):
        hit = arxiv_search(c['title'])
        if hit:
            res[c['key']] = hit
        else:
            still2.append(c)
        if i % 50 == 0:
            print('  arxiv %d/%d  hit=%d' % (i, len(still), len(res)), flush=True)
            json.dump(res, open(os.path.join(ENR, 'urls.json'), 'w', encoding='utf-8'),
                      ensure_ascii=False)
    json.dump(res, open(os.path.join(ENR, 'urls.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    print('FINAL hit %d / miss %d' % (len(res), len(still2)), flush=True)

    # 报告
    lines = ['total %d, resolved %d, missing %d' % (len(cards), len(res), len(still2)), '']
    per = {}
    for c in cards:
        d = per.setdefault(c['conf'], [0, 0])
        d[1] += 1
        if c['key'] in res:
            d[0] += 1
    for k in sorted(per):
        lines.append('%-12s %5d / %5d  (%.1f%%)' % (k, per[k][0], per[k][1], 100.0 * per[k][0] / per[k][1]))
    lines.append('')
    lines.append('--- missing ---')
    for c in still2:
        lines.append('%s | %s' % (c['conf'], c['title'][:110]))
    open(os.path.join(ENR, 'report.txt'), 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n'.join(lines[:14]))


if __name__ == '__main__':
    main()
