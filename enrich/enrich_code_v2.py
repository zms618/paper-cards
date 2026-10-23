# -*- coding: utf-8 -*-
"""代码仓库挖掘 v2 —— 分层策略，避免 GitHub 搜索限额拖死全局。

第一层：CVF 详情页（CVPR/ICCV）+ arXiv PDF 首页 —— 直接来源，全量跑
第二层：GitHub 仓库搜索 —— 仅对综合评分 >= 6.5 的论文兜底（限额 30/min）
第三层：其余标记 not found，站点显示"未公开"

断点续跑：code.json 已有记录跳过。
"""
import json, os, re, sys, time, subprocess, threading, queue as Queue
import urllib.request, urllib.parse

ROOT = r'D:\Desktop\study\github_proj\paper-cards'
ENR = os.path.join(ROOT, 'enrich')
PROXY = 'http://127.0.0.1:7897'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36'
THREADS = 16
GH_MIN_SCORE = 6.5

CODE_HOSTS = re.compile(
    r'https?://(?:www\.)?(github\.com|gitlab\.com|huggingface\.co/spaces|bitbucket\.org|codeocean\.com)/[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+',
    re.I)
BAD_SEG = {'features', 'topics', 'about', 'pricing', 'search', 'login', 'join', 'sponsors',
           'marketplace', 'explore', 'collections', 'events', 'readme', 'security',
           'site', 'apps', 'settings', 'notifications', 'new', 'orgs', 'users', 'blog',
           'contact', 'trending', 'enterprise', 'mobile', 'issues', 'pulls',
           'discussions', 'solutions', 'resources', 'customer-stories'}
BAD_REPO = {'pytorch/pytorch', 'tensorflow/tensorflow', 'facebookresearch/detectron2',
            'open-mmlab/mmdetection', 'opencv/opencv', 'huggingface/transformers',
            'scikit-learn/scikit-learn', 'numpy/numpy', 'microsoft/vscode',
            'comfyanonymous/comfyui', 'ultralytics/ultralytics'}

_tl = threading.local()


def opener():
    o = getattr(_tl, 'o', None)
    if o is None:
        o = urllib.request.build_opener(urllib.request.ProxyHandler({'http': PROXY, 'https': PROXY}))
        o.addheaders = [('User-Agent', UA), ('Accept-Language', 'en-US,en;q=0.9')]
        _tl.o = o
    return o


def fetch(url, tries=1, timeout=25):
    last = None
    for i in range(tries):
        try:
            with opener().open(url, timeout=timeout) as r:
                return r.read()
        except Exception as ex:
            last = ex
            time.sleep(0.5)
    raise last


def clean_code_links(text):
    out = []
    for m in CODE_HOSTS.finditer(text or ''):
        u = m.group(0).rstrip('.,);\'"<>')
        u = re.sub(r'[/#?]$', '', u)
        parts = u.split('://', 1)[-1].split('/')
        if len(parts) < 3:
            continue
        owner, repo = parts[1], parts[2]
        if owner.lower() in BAD_SEG or repo.lower() in BAD_SEG:
            continue
        if repo.endswith('.git'):
            repo = repo[:-4]
        if not repo or repo.startswith('.'):
            continue
        low = (owner + '/' + repo).lower()
        if low in BAD_REPO:
            continue
        canon = 'https://' + parts[0].lower() + '/' + owner + '/' + repo
        if canon not in out:
            out.append(canon)
    return out


_gh_lock = threading.Lock()
_gh_calls = []
_gh_exhausted = [False]


def gh_search(title):
    if _gh_exhausted[0]:
        return []
    q = re.sub(r'[^\w\s\-]', ' ', title)
    q = ' '.join(q.split()[:10])
    if len(q) < 6:
        return []
    url = 'https://api.github.com/search/repositories?q=%s&per_page=5&sort=stars' % urllib.parse.quote(q)
    with _gh_lock:
        now = time.time()
        _gh_calls[:] = [t for t in _gh_calls if now - t < 60]
        if len(_gh_calls) >= 26:
            wait = 60 - (now - _gh_calls[0]) + 0.5
        else:
            wait = 0
            _gh_calls.append(now)
    if wait > 0:
        time.sleep(wait)
    try:
        r = subprocess.run(['gh', 'api', url], capture_output=True, timeout=25)
        if r.returncode == 0 and r.stdout.strip():
            d = json.loads(r.stdout)
            return [it['html_url'] for it in d.get('items', [])]
        err = (r.stderr or b'').decode('utf-8', 'ignore').lower()
        if 'rate limit' in err and 'secondary' in err:
            _gh_exhausted[0] = True
    except Exception:
        pass
    return []


def resolve(key, info, score):
    title = os.path.splitext(os.path.basename(key))[0]
    url = info.get('url', '')
    # 第一层 A：CVF 详情页
    if 'thecvf.com' in url:
        try:
            h = fetch(url).decode('utf-8', 'ignore')
            f = clean_code_links(h)
            if f:
                return {'code': f[:3], 'src': 'cvf'}
        except Exception:
            pass
    # 第一层 B：arXiv abs 页
    if 'arxiv.org' in url:
        try:
            h = fetch(url).decode('utf-8', 'ignore')
            f = clean_code_links(h)
            if f:
                return {'code': f[:3], 'src': 'arxiv'}
        except Exception:
            pass
    # 第二层：GitHub 搜索（仅高分）
    if score is not None and score >= GH_MIN_SCORE:
        cand = gh_search(title)
        tw = set(w.lower() for w in re.findall(r'[A-Za-z0-9]{4,}', title))
        for c in cand:
            rn = c.rstrip('/').split('/')[-1].lower()
            if rn and (rn in tw or any(rn in w or w in rn for w in tw if len(w) > 4)):
                return {'code': [c], 'src': 'gh-search'}
    return {'code': [], 'src': ''}


def main():
    urls = json.load(open(os.path.join(ENR, 'urls.json'), encoding='utf-8'))
    outp = os.path.join(ENR, 'code.json')
    result = json.load(open(outp, encoding='utf-8')) if os.path.exists(outp) else {}

    scores = {}
    for conf in os.listdir(os.path.join(ROOT, 'data')):
        d = os.path.join(ROOT, 'data', conf)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if not fn.endswith('.json'):
                continue
            try:
                c = json.load(open(os.path.join(d, fn), encoding='utf-8'))
                sc = (c.get('scores') or {}).get('overall')
                scores[c.get('key') or (conf + '/' + fn)] = sc if isinstance(sc, (int, float)) else None
            except Exception:
                pass

    todo = [k for k in urls if k not in result]
    # 先跑有直接来源的（CVF / arXiv），再跑需要 GitHub 搜索的
    direct = [k for k in todo if 'thecvf.com' in urls[k].get('url', '') or 'arxiv.org' in urls[k].get('url', '')]
    rest = [k for k in todo if k not in set(direct)]
    order = direct + rest
    print('todo %d (direct %d, gh-fallback %d) threads=%d' % (len(order), len(direct), len(rest), THREADS), flush=True)

    q = Queue.Queue()
    for k in order:
        q.put(k)
    lock = threading.Lock()
    done = [0]
    t0 = time.time()

    def worker():
        while True:
            try:
                k = q.get_nowait()
            except Queue.Empty:
                return
            try:
                r = resolve(k, urls[k], scores.get(k))
            except Exception:
                r = {'code': [], 'src': 'err'}
            with lock:
                result[k] = r
                done[0] += 1
                n = done[0]
                if n % 100 == 0:
                    el = time.time() - t0
                    json.dump(result, open(outp, 'w', encoding='utf-8'), ensure_ascii=False)
                    wc = sum(1 for v in result.values() if v['code'])
                    print('%d/%d %.0fs with-code=%d(%.1f%%) eta=%.0fmin'
                          % (n, len(order), el, wc, 100.0 * wc / len(result),
                             (len(order) - n) * el / n / 60), flush=True)
            q.task_done()

    ths = [threading.Thread(target=worker, daemon=True) for _ in range(THREADS)]
    [t.start() for t in ths]
    [t.join() for t in ths]
    json.dump(result, open(outp, 'w', encoding='utf-8'), ensure_ascii=False)
    wc = sum(1 for v in result.values() if v['code'])
    print('DONE with-code %d / %d (%.1f%%)' % (wc, len(result), 100.0 * wc / len(result)), flush=True)


if __name__ == '__main__':
    main()
