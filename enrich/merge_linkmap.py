# -*- coding: utf-8 -*-
"""合并 urls.json + code.json -> linkmap.json（build_site.py 读取的唯一入口）。"""
import json, os

ENR = r'D:\Desktop\study\github_proj\paper-cards\enrich'
urls = json.load(open(os.path.join(ENR, 'urls.json'), encoding='utf-8'))
code = json.load(open(os.path.join(ENR, 'code.json'), encoding='utf-8')) if \
    os.path.exists(os.path.join(ENR, 'code.json')) else {}

out = {}
for k, v in urls.items():
    out[k] = {
        'url': v.get('url', ''),
        'pdf': v.get('pdf', ''),
        'src': v.get('src', ''),
        'code': (code.get(k) or {}).get('code', []),
        'code_src': (code.get(k) or {}).get('src', ''),
    }
# 只有 code 记录没有 url 的情况也保留代码链接
for k, v in code.items():
    if k not in out and v.get('code'):
        out[k] = {'url': '', 'pdf': '', 'src': '', 'code': v['code'], 'code_src': v.get('src', '')}

p = os.path.join(ENR, 'linkmap.json')
json.dump(out, open(p, 'w', encoding='utf-8'), ensure_ascii=False)
n_url = sum(1 for v in out.values() if v['url'])
n_code = sum(1 for v in out.values() if v['code'])
print('entries %d  with-url %d  with-code %d  -> %s' % (len(out), n_url, n_code, p))
