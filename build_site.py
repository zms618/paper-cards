# -*- coding: utf-8 -*-
"""从精读卡片 JSON 生成静态站点（GitHub Pages 用）"""
import os, json, glob, re, hashlib, html, statistics

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'data')
OUT = os.path.join(ROOT, 'site')

CONFS = ['cvpr2026', 'neurips2025', 'icml2025', 'iclr2026', 'iccv2025', 'cvpr2025']
NAMES = {
    'cvpr2025': 'CVPR 2025', 'cvpr2026': 'CVPR 2026', 'iccv2025': 'ICCV 2025',
    'iclr2026': 'ICLR 2026', 'icml2025': 'ICML 2025', 'neurips2025': 'NeurIPS 2025',
}
TOTAL = 0

# 主题分类：按关键词命中数打分，取最高者（一卡可多主题）
TOPICS = [
    ('reliability', '可靠性 · 泛化 · 不确定性', '#2563eb', [
        'domain generalization', 'out-of-distribution', 'distribution shift', 'ood',
        'robustness', 'robust ', 'test-time', 'tta', 'calibration', 'uncertainty',
        'hallucination', 'reliab', 'adversarial', 'generaliz', 'invariant',
        'shortcut', 'spurious', 'failure detection', 'conformal', 'risk']),
    ('medical', '医学影像 · 病理', '#0891b2', [
        'medical', 'clinical', 'pathology', 'wsi', 'whole slide', 'histopath',
        'mri', 'ct ', 'x-ray', 'radiolog', 'lesion', 'tumor', 'diagnos',
        'biomedical', 'healthcare', 'dermatol', 'retina', 'fundus', 'ultrasound',
        'microscopy', 'cell ', 'biopsy', 'organ']),
    ('multimodal', '多模态 · 视觉语言', '#7c3aed', [
        'multimodal', 'vision-language', 'vision language', 'vlm', 'clip',
        'image-text', 'text-image', 'captioning', 'visual question', 'vqa',
        'grounding', 'cross-modal', 'audio-visual', 'video-language', 'llava']),
    ('llm', '大模型 · 推理与智能体', '#c026d3', [
        'large language model', 'llm', 'reasoning', 'agent', 'chain-of-thought',
        'chain of thought', 'in-context', 'instruction', 'rlhf', 'alignment',
        'prompt', 'retrieval-augment', 'rag ', 'moe', 'mixture-of-experts',
        'post-training', 'fine-tun', 'cot']),
    ('generation', '生成模型 · 扩散', '#db2777', [
        'diffusion', 'generative', 'image generation', 'text-to-image', 'video generation',
        'gan', 'flow matching', 'score-based', 'synthesis', 'editing', '3dgs',
        'gaussian splatting', 'nerf', 'avatar']),
    ('rl_embodied', '强化学习 · 具身智能', '#ea580c', [
        'reinforcement learning', 'policy', 'robot', 'embodied', 'manipulation',
        'autonomous driving', 'navigation', 'world model', 'vla', 'action',
        'reward model', 'process reward', 'decision']),
    ('efficiency', '高效计算 · 压缩', '#65a30d', [
        'efficient', 'compression', 'quantization', 'pruning', 'distillation',
        'sparse', 'low-rank', 'lora', 'inference cost', 'throughput', 'latency',
        'memory-efficient', 'token reduction']),
    ('perception', '视觉感知 · 分割检测', '#059669', [
        'segmentation', 'detection', 'tracking', 'depth estimation', 'pose',
        'recognition', 'classification', 're-identification', 'anomaly',
        'super-resolution', 'restoration', 'denoising', 'deblur', 'matting']),
    ('representation', '表征学习 · 自监督', '#475569', [
        'self-supervised', 'contrastive', 'representation learning', 'pretrain',
        'pre-train', 'masked image', 'mae', 'embedding', 'feature learn', 'ssl']),
]
TOPIC_MAP = {k: (n, c) for k, n, c, _ in TOPICS}
FALLBACK_TOPIC = ('other', '其他', '#71717a')
TOPIC_EN = {
    'reliability': 'Reliability · Generalization · Uncertainty',
    'medical': 'Medical Imaging · Pathology',
    'multimodal': 'Multimodal · Vision-Language',
    'llm': 'LLMs · Reasoning · Agents',
    'generation': 'Generative Models · Diffusion',
    'rl_embodied': 'RL · Embodied AI',
    'efficiency': 'Efficiency · Compression',
    'perception': 'Perception · Detection & Segmentation',
    'representation': 'Representation · Self-supervised',
    'other': 'Other',
}


def classify(c):
    """返回 [(topic_key, hits)]，按命中数降序；全不中归 other"""
    text = ' '.join([c['title'], c['one_line'], c['method']]).lower()
    hits = []
    for key, _name, _col, kws in TOPICS:
        n = sum(1 for k in kws if k in text)
        if n:
            hits.append((key, n))
    hits.sort(key=lambda x: -x[1])
    if not hits:
        return [('other', 0)]
    top = hits[0][1]
    # 保留所有接近最高命中的主题，避免强论文只落一个桶
    return [(k, n) for k, n in hits if n >= max(2, top - 1)][:2]


def esc(s):
    return html.escape('' if s is None else str(s), quote=True)


# 双语界面文案（卡片正文保持原文；仅界面元素切换）
I18N = {
    'zh': {
        'brand': '论文精读卡片', 'home': '首页', 'search': '搜索',
        'hero_h1': '论文精读卡片库',
        'hero_p': '6 个顶会 · 每张卡片含四维评分（新颖性 / 深度 / 证据 / 相关性）、创新点、方法框架、可借鉴点与缺点。',
        'stat_cards': '张精读卡片', 'stat_confs': '个会议', 'stat_avg': '平均综合分',
        'stat_hi': '7 分以上（稀有）',
        'sec_topic': '按主题', 'sec_topic_s': '自动按研究方向归类',
        'sec_conf': '按会议', 'sec_conf_s': '点进去看全部卡片，可按分数排序或筛选',
        'sec_top': '高分榜', 'sec_top_s': '按综合评分排序的前 24 张',
        'n_cards': '张卡片', 'avg': '均分', 'seven_plus': '7+',
        'filt_ph': '在标题与一句话评价里筛选…',
        'all_confs': '全部会议',
        'th_title': '标题', 'th_overall': '综合', 'th_rel': '相关性',
        'th_nov': '新颖', 'th_depth': '深度', 'th_evid': '证据', 'th_tier': '档',
        'prev': '上一页', 'next': '下一页', 'no_match': '没有匹配的卡片',
        'footer': '张精读卡片 · 数据来自本地卡片库，由脚本自动生成',
        'score_overall': '综合评分', 'novelty': '新颖性', 'depth': '技术深度',
        'evidence': '实验证据', 'relevance': '相关性',
        'innovations': '创新点', 'method': '方法框架', 'experiment': '实验框架',
        'takeaways': '可借鉴点', 'weaknesses': '缺点', 'rel_reason': '相关性判断',
        'tier_label': '档', 'conf_label': '置信度',
        'search_h1': '搜索', 'search_p': '在全部卡片的标题与一句话评价里检索。',
        'search_ph': '输入关键词，例如：domain generalization、WSI、reward model…',
        'loading': '正在载入索引…', 'loaded': '张卡片已载入，输入关键词开始搜索',
        'hits': '命中', 'topic_sub': '按主题自动归类，共',
        'conf_sub': '按综合评分排序，可点击表头改排序，或按会议筛选。',
        'lang_btn': 'EN',
    },
    'en': {
        'brand': 'Paper Notes', 'home': 'Home', 'search': 'Search',
        'hero_h1': 'Paper Reading Notes',
        'hero_p': '6 conferences · every card has four scores (novelty / depth / evidence / relevance), key ideas, method & experiment summaries, takeaways and weaknesses.',
        'stat_cards': 'reading cards', 'stat_confs': 'conferences', 'stat_avg': 'mean overall score',
        'stat_hi': 'scored 7+ (rare)',
        'sec_topic': 'By topic', 'sec_topic_s': 'auto-grouped by research area',
        'sec_conf': 'By conference', 'sec_conf_s': 'browse all cards, sortable and filterable',
        'sec_top': 'Top rated', 'sec_top_s': 'top 24 by overall score',
        'n_cards': 'cards', 'avg': 'avg', 'seven_plus': '7+',
        'filt_ph': 'Filter by title or one-line summary…',
        'all_confs': 'All conferences',
        'th_title': 'Title', 'th_overall': 'Overall', 'th_rel': 'Relevance',
        'th_nov': 'Novelty', 'th_depth': 'Depth', 'th_evid': 'Evidence', 'th_tier': 'Tier',
        'prev': 'Prev', 'next': 'Next', 'no_match': 'No matching cards',
        'footer': 'reading cards · generated from a local card library',
        'score_overall': 'Overall', 'novelty': 'Novelty', 'depth': 'Depth',
        'evidence': 'Evidence', 'relevance': 'Relevance',
        'innovations': 'Key ideas', 'method': 'Method', 'experiment': 'Experiments',
        'takeaways': 'Takeaways', 'weaknesses': 'Weaknesses', 'rel_reason': 'Relevance note',
        'tier_label': 'Tier', 'conf_label': 'confidence',
        'search_h1': 'Search', 'search_p': 'Search titles and one-line summaries across all cards.',
        'search_ph': 'Try: domain generalization, WSI, reward model…',
        'loading': 'Loading index…', 'loaded': 'cards loaded — type to search',
        'hits': 'hits', 'topic_sub': 'auto-grouped by topic,',
        'conf_sub': 'Sorted by overall score. Click a column header to re-sort.',
        'lang_btn': '中',
    },
}
LANG = 'zh'


def t(key):
    return I18N[LANG].get(key, key)


def fmt(v):
    if v is None:
        return '—'
    try:
        t = '%.1f' % float(v)
        return t[:-2] if t.endswith('.0') else t
    except Exception:
        return str(v)


def slugify(key, path):
    stem = os.path.splitext(os.path.basename(path.replace('\\', '/')))[0]
    s = re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-')[:80].strip('-')
    h = hashlib.md5(key.encode('utf-8')).hexdigest()[:6]
    return (s + '-' + h) if s else h


def load_cards():
    cards = []
    for conf in CONFS:
        d = os.path.join(DATA, conf)
        if not os.path.isdir(d):
            continue
        for f in sorted(glob.glob(os.path.join(d, '*.json'))):
            try:
                raw = open(f, 'rb').read()
                c = None
                for enc in ('utf-8', 'gbk'):
                    try:
                        c = json.loads(raw.decode(enc))
                        break
                    except Exception:
                        pass
                if not isinstance(c, dict):
                    continue
            except Exception:
                continue
            sc = c.get('scores') or {}
            title = (c.get('title') or '').strip() or os.path.splitext(os.path.basename(f))[0]
            key = c.get('key') or (conf + '/' + os.path.basename(f))
            path = c.get('path') or key
            val = lambda k: (sc.get(k) if isinstance(sc.get(k), (int, float)) else None)
            cards.append({
                'conf': conf,
                'title': title,
                'key': key,
                'path': path,
                'novelty': val('novelty'),
                'depth': val('depth'),
                'evidence': val('evidence'),
                'relevance': val('relevance'),
                'overall': val('overall'),
                'one_line': (c.get('one_line') or '').strip(),
                'innovations': [x for x in (c.get('innovations') or []) if x],
                'method': (c.get('method_framework') or '').strip(),
                'experiment': (c.get('experiment_framework') or '').strip(),
                'takeaways': [x for x in (c.get('takeaways') or []) if x],
                'weaknesses': [x for x in (c.get('weaknesses') or []) if x],
                'confidence': (c.get('confidence') or '').strip(),
                'tier': (c.get('tier') or '').strip(),
                'rel_reason': (c.get('relevance_reason') or '').strip(),
                'slug': slugify(key, path),
            })
    for c in cards:
        c['topics'] = [k for k, _n in classify(c)]
    return cards


CSS = """
:root{--bg:#fafafa;--surface:#fff;--border:#e5e7eb;--text:#18181b;--muted:#71717a;
--accent:#2563eb;--accent-soft:#eff6ff;--warn:#b45309;--warn-soft:#fffbeb;
--ok:#047857;--ok-soft:#ecfdf5;--r:12px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei","Noto Sans SC",sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1040px;margin:0 auto;padding:0 20px}
.topbar{background:rgba(255,255,255,.92);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:20}
.topbar .wrap{display:flex;align-items:center;justify-content:space-between;height:56px}
.brand{font-weight:700;color:var(--text);font-size:15px;letter-spacing:.2px}
nav{display:flex;align-items:center}
nav a{color:var(--muted);margin-left:20px;font-size:14px}
nav a:hover{color:var(--text);text-decoration:none}
.langbtn{margin-left:16px;padding:3px 10px;font-size:12px;border:1px solid var(--border);background:var(--surface);color:var(--muted);border-radius:6px;cursor:pointer;line-height:1.6}
.langbtn:hover{border-color:#93c5fd;color:var(--accent)}
main{padding:34px 20px 60px}
h1,h2,h3{line-height:1.35;margin:0}
.hero{padding:14px 0 26px}
.hero h1{font-size:30px;letter-spacing:-.5px}
.hero p{color:var(--muted);margin:12px 0 0;font-size:15px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:26px 0 8px}
.stat{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:16px 18px}
.stat b{display:block;font-size:24px;letter-spacing:-.5px}
.stat span{color:var(--muted);font-size:13px}
h2.sec{font-size:17px;margin:44px 0 16px;display:flex;align-items:center;gap:10px}
h2.sec small{font-weight:400;color:var(--muted);font-size:13px}
.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.conf{display:block;background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:18px;transition:.15s}
.conf:hover{border-color:#c7d2fe;box-shadow:0 4px 16px rgba(37,99,235,.07);text-decoration:none}
.conf b{display:block;font-size:16px;color:var(--text)}
.conf span{color:var(--muted);font-size:13px}
.conf .row{display:flex;justify-content:space-between;margin-top:12px;font-size:13px;color:var(--muted)}
.conf .row i{font-style:normal;color:var(--text);font-weight:600}
.list{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);overflow:hidden}
.item{display:flex;gap:14px;align-items:flex-start;padding:13px 18px;border-top:1px solid var(--border)}
.item:first-child{border-top:0}
.item:hover{background:#fcfcfd}
.item .num{color:#a1a1aa;font-size:12px;width:24px;flex:none;padding-top:4px;font-variant-numeric:tabular-nums}
.item .body{flex:1;min-width:0}
.item .t{color:var(--text);font-weight:600;font-size:14.5px;display:block;line-height:1.5}
.item .t:hover{color:var(--accent);text-decoration:none}
.item .o{color:var(--muted);font-size:13px;margin-top:3px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.chips{display:flex;gap:6px;flex:none;flex-wrap:wrap;justify-content:flex-end}
.chip{font-size:12px;padding:2px 8px;border-radius:999px;background:#f4f4f5;color:#52525b;white-space:nowrap;font-variant-numeric:tabular-nums}
.chip.hi{background:var(--accent-soft);color:var(--accent);font-weight:600}
.chip.tier{background:#f5f3ff;color:#6d28d9}
.chip.rel{background:var(--ok-soft);color:var(--ok)}
.crumb{font-size:13px;color:var(--muted);margin-bottom:14px}
.crumb a{color:var(--muted)}
.ptitle{font-size:26px;line-height:1.4;letter-spacing:-.3px}
.meta{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:14px 0 22px;font-size:13px;color:var(--muted)}
.meta .file{color:#a1a1aa;font-size:12px;word-break:break-all}
.scoreboard{display:flex;gap:22px;align-items:center;background:var(--surface);border:1px solid var(--border);border-radius:var(--r);padding:18px 20px;margin-bottom:22px}
.bigscore{text-align:center;flex:none;min-width:92px}
.bigscore b{display:block;font-size:34px;letter-spacing:-1px;line-height:1.1}
.bigscore span{font-size:12px;color:var(--muted)}
.bars{flex:1;display:flex;flex-direction:column;gap:7px}
.sbar{display:flex;align-items:center;gap:10px;font-size:12.5px;color:var(--muted)}
.sbar-l{width:52px;flex:none;text-align:right}
.sbar-t{flex:1;height:6px;background:#f4f4f5;border-radius:3px;overflow:hidden}
.sbar-t span{display:block;height:100%;background:var(--accent);border-radius:3px}
.sbar-v{width:28px;flex:none;font-variant-numeric:tabular-nums;color:#52525b}
.oneliner{font-size:16px;line-height:1.7;background:var(--accent-soft);border-left:3px solid var(--accent);padding:12px 16px;border-radius:0 8px 8px 0;margin:0 0 28px}
section.blk{margin:0 0 26px}
section.blk h3{font-size:14px;color:var(--muted);font-weight:600;letter-spacing:.3px;margin-bottom:8px;text-transform:uppercase}
section.blk ol,section.blk ul{margin:0;padding-left:22px}
section.blk li{margin:6px 0}
section.blk p{margin:0;color:#27272a}
section.wk ul{color:#7c2d12}
section.wk li::marker{color:#f97316}
section.tk ul{color:#065f46}
section.tk li::marker{color:#10b981}
table.t{width:100%;border-collapse:collapse;background:var(--surface);border:1px solid var(--border);border-radius:var(--r);overflow:hidden;font-size:13.5px}
table.t th,table.t td{padding:9px 12px;border-bottom:1px solid var(--border);text-align:left;vertical-align:top}
table.t th{background:#fafafa;color:var(--muted);font-weight:600;font-size:12.5px;cursor:pointer;user-select:none;white-space:nowrap;position:sticky;top:56px}
table.t th:hover{color:var(--text)}
table.t td.n{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap;color:#52525b}
table.t tr:hover td{background:#fcfcfd}
table.t td a{display:block}
.toolbar{display:flex;gap:10px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.toolbar input{flex:1;min-width:220px;padding:9px 13px;border:1px solid var(--border);border-radius:9px;font-size:14px;background:var(--surface);color:var(--text);outline:none}
.toolbar input:focus{border-color:#93c5fd;box-shadow:0 0 0 3px #dbeafe}
.toolbar select{padding:9px 12px;border:1px solid var(--border);border-radius:9px;background:var(--surface);font-size:14px;color:var(--text)}
.toolbar .cnt{color:var(--muted);font-size:13px}
.pager{display:flex;gap:8px;align-items:center;justify-content:center;margin:18px 0 0;font-size:13.5px;color:var(--muted)}
.pager button{padding:6px 12px;border:1px solid var(--border);background:var(--surface);border-radius:8px;cursor:pointer;font-size:13px;color:var(--text)}
.pager button:disabled{opacity:.45;cursor:default}
.foot{padding:34px 20px 48px;color:#a1a1aa;font-size:12.5px;text-align:center;border-top:1px solid var(--border);margin-top:40px}
.empty{padding:40px;text-align:center;color:var(--muted);background:var(--surface);border:1px dashed var(--border);border-radius:var(--r)}
@media(max-width:860px){.grid{grid-template-columns:repeat(2,1fr)}.stats{grid-template-columns:repeat(2,1fr)}.ptitle{font-size:22px}}
@media(max-width:560px){.grid{grid-template-columns:1fr}.scoreboard{flex-direction:column;align-items:stretch}.bigscore{display:flex;gap:10px;align-items:baseline;justify-content:center}}
"""


LANG_SWITCH_JS = """
(function(){
  var cur = document.documentElement.lang.indexOf('en')===0 ? 'en' : 'zh';
  function targetPath(target){
    var path = location.pathname;
    if (target === 'en') {
      // 已经是 en 页就不再改；否则给 ] .html 前加 .en
      if (/\\.en\\.html$/.test(path)) return path;
      return path.replace(/\\.html$/, '.en.html');
    }
    return path.replace(/\\.en\\.html$/, '.html');
  }
  var saved = null;
  try { saved = localStorage.getItem('pn_lang'); } catch(e){}
  if (saved && saved !== cur) {
    location.replace(targetPath(saved) + location.search + location.hash);
    return;
  }
  var btn = document.getElementById('langBtn');
  if (btn) {
    btn.addEventListener('click', function(){
      var target = cur === 'en' ? 'zh' : 'en';
      try { localStorage.setItem('pn_lang', target); } catch(e){}
      location.href = targetPath(target) + location.search + location.hash;
    });
    btn.textContent = cur === 'en' ? '中' : 'EN';
  }
})();
"""


def page(title, body, depth=0, head=''):
    pre = '../' * depth
    lang = 'en' if LANG == 'en' else 'zh-CN'
    return (
        f'<!DOCTYPE html>\n<html lang="{lang}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        f'<title>{esc(title)}</title>\n'
        f'<link rel="stylesheet" href="{pre}assets/style.css">\n{head}'
        '</head>\n<body>\n'
        '<header class="topbar"><div class="wrap">'
        f'<a class="brand" href="{pre}index{".en" if LANG == "en" else ""}.html">{esc(t("brand"))}</a>'
        f'<nav><a href="{pre}index{".en" if LANG == "en" else ""}.html">{esc(t("home"))}</a>'
        f'<a href="{pre}search{".en" if LANG == "en" else ""}.html">{esc(t("search"))}</a>'
        '<button id="langBtn" class="langbtn">' + ('中' if LANG == 'en' else 'EN') + '</button></nav>'
        '</div></header>\n<main class="wrap">\n'
        + body +
        '\n</main>\n'
        f'<footer class="foot">{TOTAL} {esc(t("footer"))}</footer>\n'
        f'<script>{LANG_SWITCH_JS}</script>\n'
        f'<script src="{pre}assets/reader.js" defer></script>\n'
        '</body>\n</html>\n'
    )


def write(rel, text):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)


def score_chips(c, small=False):
    out = []
    if c['overall'] is not None:
        cls = 'chip hi' if (c['overall'] or 0) >= 7 else 'chip'
        out.append(f'<span class="{cls}">{fmt(c["overall"])}</span>')
    if c['relevance'] is not None:
        out.append(f'<span class="chip rel">R {fmt(c["relevance"])}</span>')
    if c['tier']:
        out.append(f'<span class="chip tier">{esc(c["tier"])}</span>')
    return ''.join(out)


def card_page(c):
    suffix = '.en' if LANG == 'en' else ''
    sc = [
        (t('novelty'), c['novelty']), (t('depth'), c['depth']),
        (t('evidence'), c['evidence']), (t('relevance'), c['relevance']),
    ]
    bars = ''.join(
        f'<div class="sbar"><span class="sbar-l">{esc(n)}</span>'
        f'<span class="sbar-t"><span style="width:{max(0, min(100, (v or 0) * 10)):.0f}%"></span></span>'
        f'<span class="sbar-v">{fmt(v)}</span></div>'
        for n, v in sc
    )
    body = [f'<div class="crumb"><a href="../index{suffix}.html">{esc(t("home"))}</a> / '
            f'<a href="index{suffix}.html">{esc(NAMES[c["conf"]])}</a></div>',
            f'<h1 class="ptitle">{esc(c["title"])}</h1>',
            '<div class="meta">',
            f'<span class="chip tier">{esc(NAMES[c["conf"]])}</span>']
    if c['tier']:
        body.append(f'<span class="chip">{esc(t("tier_label"))} {esc(c["tier"])}</span>')
    if c['confidence']:
        body.append(f'<span class="chip">{esc(t("conf_label"))} {esc(c["confidence"])}</span>')
    body.append(f'<span class="file">{esc(c["path"])}</span></div>')
    body.append('<div class="scoreboard"><div class="bigscore">'
                f'<b>{fmt(c["overall"])}</b><span>{esc(t("score_overall"))}</span></div>'
                f'<div class="bars">{bars}</div></div>')
    if c['one_line']:
        body.append(f'<p class="oneliner">{esc(c["one_line"])}</p>')
    if c['innovations']:
        body.append(f'<section class="blk"><h3>{esc(t("innovations"))}</h3><ol>' +
                    ''.join(f'<li>{esc(x)}</li>' for x in c['innovations']) + '</ol></section>')
    if c['method']:
        body.append(f'<section class="blk"><h3>{esc(t("method"))}</h3><p>{esc(c["method"])}</p></section>')
    if c['experiment']:
        body.append(f'<section class="blk"><h3>{esc(t("experiment"))}</h3><p>{esc(c["experiment"])}</p></section>')
    if c['takeaways']:
        body.append(f'<section class="blk tk"><h3>{esc(t("takeaways"))}</h3><ul>' +
                    ''.join(f'<li>{esc(x)}</li>' for x in c['takeaways']) + '</ul></section>')
    if c['weaknesses']:
        body.append(f'<section class="blk wk"><h3>{esc(t("weaknesses"))}</h3><ul>' +
                    ''.join(f'<li>{esc(x)}</li>' for x in c['weaknesses']) + '</ul></section>')
    if c['rel_reason']:
        body.append(f'<section class="blk"><h3>{esc(t("rel_reason"))}</h3><p>{esc(c["rel_reason"])}</p></section>')
    return page(c['title'] + ' · ' + NAMES[c['conf']], '\n'.join(body), depth=1)


TABLE_JS = """
(function(){
  var dataEl = document.getElementById('cards-data');
  var state = {key:'overall', dir:-1, q:'', conf:'ALL', page:0, size:60};
  var tb = document.getElementById('tbody'), cnt = document.getElementById('cnt');
  var q = document.getElementById('q'), sel = document.getElementById('confSel');
  var pager = document.getElementById('pager');
  var DATA = null;
  function num(v){ return (v===null||v===undefined)?-1:v; }
  function apply(){
    if(!DATA) return;
    var rows = DATA.filter(function(r){
      if(state.conf!=='ALL' && r.c!==state.conf) return false;
      if(!state.q) return true;
      var qq = state.q.toLowerCase();
      return ((r.t||'')+' '+(r.o||'')).toLowerCase().indexOf(qq)>=0;
    });
    rows.sort(function(a,b){
      var av=num(a[state.key]), bv=num(b[state.key]);
      if(typeof av==='string'||typeof bv==='string'){
        av=String(a[state.key]||''); bv=String(b[state.key]||'');
        return av<bv?state.dir:av>bv?-state.dir:0;
      }
      return (av-bv)*state.dir;
    });
    cnt.textContent = rows.length + ' ' + PN_I18N.n_cards;
    var pages = Math.max(1, Math.ceil(rows.length/state.size));
    if(state.page>=pages) state.page=pages-1;
    var start = state.page*state.size, end = Math.min(rows.length, start+state.size);
    var h='';
    for(var i=start;i<end;i++){
      var r=rows[i];
      h+='<tr><td class="n">'+(i+1)+'</td><td><a href="'+r.u+'.html">'+esc(r.t)+'</a>'+
         (r.o?'<div style="color:#a1a1aa;font-size:12px;margin-top:2px">'+esc(r.o)+'</div>':'')+
         '</td><td class="n">'+f(r.s)+'</td><td class="n">'+f(r.r)+'</td><td class="n">'+f(r.n)+
         '</td><td class="n">'+f(r.d)+'</td><td class="n">'+f(r.e)+'</td><td class="n">'+esc(r.k||'')+'</td></tr>';
    }
    tb.innerHTML = h || '<tr><td colspan="8" style="text-align:center;color:#a1a1aa;padding:30px">'+PN_I18N.no_match+'</td></tr>';
    pager.innerHTML = '<button id="pv"'+(state.page===0?' disabled':'')+'>'+PN_I18N.prev+'</button>'+
      '<span>'+(state.page+1)+' / '+pages+'</span>'+
      '<button id="nx"'+(state.page>=pages-1?' disabled':'')+'>'+PN_I18N.next+'</button>';
    var pv=document.getElementById('pv'), nx=document.getElementById('nx');
    if(pv) pv.onclick=function(){state.page--;apply();};
    if(nx) nx.onclick=function(){state.page++;apply();};
  }
  function f(v){ return (v===null||v===undefined||v==='')?'—':(Math.round(v*10)/10).toString(); }
  function esc(s){ var d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }
  function boot(){
    // 优先用外置 JSON（避免把上万条数据内嵌进 HTML），失败则回退到内嵌数据
    var src = dataEl.getAttribute('data-src');
    var inline = dataEl.getAttribute('data-inline') === '1';
    if (src) {
      fetch(src).then(function(r){ return r.json(); }).then(function(d){ DATA=d; apply(); })
                .catch(function(){ if(inline){ DATA=JSON.parse(dataEl.textContent); apply(); } });
    } else {
      DATA = JSON.parse(dataEl.textContent); apply();
    }
  }
  q.addEventListener('input', function(){ state.q=this.value.trim(); state.page=0; apply(); });
  if(sel) sel.addEventListener('change', function(){ state.conf=this.value; state.page=0; apply(); });
  document.querySelectorAll('th[data-k]').forEach(function(th){
    th.addEventListener('click', function(){
      var k=this.getAttribute('data-k');
      if(state.key===k) state.dir=-state.dir; else {state.key=k; state.dir=-1;}
      state.page=0; apply();
    });
  });
  boot();
})();
"""


def make_list_page(title, subtitle, cards, depth, crumb_html, conf_filter=None, data_name=None):
    """通用卡片列表页（带筛选/排序/分页）；数据外置为 JSON，避免每页内嵌上万条"""
    suffix = '.en' if LANG == 'en' else ''
    rows = [{
        't': c['title'], 'o': c['one_line'], 's': c['overall'], 'r': c['relevance'],
        'n': c['novelty'], 'd': c['depth'], 'e': c['evidence'],
        'k': c['tier'], 'c': c['conf'], 'u': c['slug'] + suffix,
    } for c in cards]
    payload = json.dumps(rows, ensure_ascii=False, separators=(',', ':'))
    pre = '../' * depth
    # 数据文件与页面同目录（xxx.data.json），路径相对于页面自身
    dname = (data_name or 'cards') + '.data.json'
    data_src = dname
    ov = [c['overall'] for c in cards if c['overall'] is not None]
    avg = statistics.mean(ov) if ov else 0
    hi = sum(1 for v in ov if v >= 7)
    opts = ''.join(f'<option value="{c}"{" selected" if c == conf_filter else ""}>{esc(NAMES[c])}</option>' for c in CONFS)
    body = f'''{crumb_html}
<h1 class="ptitle">{title}</h1>
<p style="color:var(--muted);margin:10px 0 16px">{subtitle}</p>
<div class="meta"><span class="chip">{len(cards)} {esc(t("n_cards"))}</span>
<span class="chip">{esc(t("avg"))} {avg:.2f}</span>
<span class="chip hi">{esc(t("seven_plus"))} {hi}</span></div>
<div class="toolbar">
  <input id="q" type="search" placeholder="{esc(t("filt_ph"))}">
  <select id="confSel"><option value="ALL">{esc(t("all_confs"))}</option>{opts}</select>
  <span class="cnt" id="cnt"></span>
</div>
<table class="t">
<thead><tr><th>#</th><th data-k="t">{esc(t("th_title"))}</th><th data-k="s">{esc(t("th_overall"))}</th>
<th data-k="r">{esc(t("th_rel"))}</th><th data-k="n">{esc(t("th_nov"))}</th>
<th data-k="d">{esc(t("th_depth"))}</th><th data-k="e">{esc(t("th_evid"))}</th>
<th data-k="k">{esc(t("th_tier"))}</th></tr></thead>
<tbody id="tbody"></tbody></table>
<div class="pager" id="pager"></div>
<script id="cards-data" type="application/json" data-src="{data_src}"></script>
<script>var PN_I18N={json.dumps({'prev': t('prev'), 'next': t('next'), 'no_match': t('no_match'), 'n_cards': t('n_cards')}, ensure_ascii=False)};</script>
<script>{TABLE_JS}</script>'''
    return page(title, body, depth=depth), payload, dname


def conference_page(conf, cards):
    suffix = '.en' if LANG == 'en' else ''
    html, payload, dname = make_list_page(
        esc(NAMES[conf]) + (' 精读卡片' if LANG == 'zh' else ' Reading Cards'),
        esc(t('conf_sub')),
        cards, 1,
        f'<div class="crumb"><a href="../index{suffix}.html">{esc(t("home"))}</a> / {esc(NAMES[conf])}</div>',
        conf_filter=conf,
        data_name=conf + suffix)
    return html, payload, dname


SEARCH_JS = """
(function(){
  var box=document.getElementById('q'), out=document.getElementById('out'), cnt=document.getElementById('cnt');
  var data=null, suffix=document.documentElement.lang.indexOf('en')===0?'.en':'';
  fetch('data/index.json').then(function(r){return r.json();}).then(function(d){
    data=d; cnt.textContent = d.length+' '+PN_I18N.loaded;
  });
  function f(v){ return (v===null||v===undefined)?'—':(Math.round(v*10)/10).toString(); }
  function esc(s){ var d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }
  var timer=null;
  box.addEventListener('input', function(){
    clearTimeout(timer);
    var q=this.value.trim().toLowerCase();
    timer=setTimeout(function(){
      if(!data) return;
      if(!q){ out.innerHTML=''; cnt.textContent=data.length+' '+PN_I18N.loaded; return; }
      var res=data.filter(function(r){ return (r.t+' '+(r.o||'')).toLowerCase().indexOf(q)>=0; });
      res.sort(function(a,b){ return (b.s||0)-(a.s||0); });
      cnt.textContent=PN_I18N.hits+' '+res.length;
      out.innerHTML = res.slice(0,200).map(function(r){
        return '<div class="item"><div class="body"><a class="t" href="'+r.c+'/'+r.u+suffix+'.html">'+esc(r.t)+'</a>'+
          '<span class="o">'+esc(r.c.toUpperCase())+' · '+esc(r.o)+'</span></div>'+
          '<div class="chips"><span class="chip hi">'+f(r.s)+'</span><span class="chip rel">R '+f(r.r)+'</span></div></div>';
      }).join('') || '<div class="empty">'+PN_I18N.no_match+'</div>';
    }, 120);
  });
})();
"""


def build():
    """按 zh / en 各生成一遍，英文页用 .en.html 后缀"""
    global TOTAL, LANG
    cards = load_cards()
    TOTAL = len(cards)
    if os.path.isdir(OUT):
        # 不直接删除（2 万文件，安全删除机制会失败）：重命名为带时间戳的旧目录
        import time as _time
        stale = OUT + '.stale.' + _time.strftime('%H%M%S')
        try:
            os.rename(OUT, stale)
        except OSError:
            import shutil
            shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(ROOT, 'theme.css'), encoding='utf-8') as theme_file:
        write('assets/style.css', CSS + '\n' + theme_file.read())
    write('.nojekyll', '')
    with open(os.path.join(ROOT, 'reader.js'), encoding='utf-8') as reader_file:
        write('assets/reader.js', reader_file.read())

    by_conf = {}
    for c in cards:
        by_conf.setdefault(c['conf'], []).append(c)

    # 与语言无关：搜索索引
    idx = [{'t': c['title'], 'o': c['one_line'], 's': c['overall'], 'r': c['relevance'],
            'c': c['conf'], 'u': c['slug']} for c in cards]
    write('data/index.json', json.dumps(idx, ensure_ascii=False, separators=(',', ':')))

    by_topic = {}
    for c in cards:
        for tk in c['topics']:
            by_topic.setdefault(tk, []).append(c)

    ov = [c['overall'] for c in cards if c['overall'] is not None]
    avg = statistics.mean(ov) if ov else 0
    hi = sum(1 for v in ov if v >= 7)

    for lang_code in ('zh', 'en'):
        LANG = lang_code
        sfx = '' if lang_code == 'zh' else '.en'

        # 卡片详情页
        for conf, lst in by_conf.items():
            for c in lst:
                write(os.path.join(conf, c['slug'] + sfx + '.html'), card_page(c))
            html, payload, dname = conference_page(conf, lst)
            write(os.path.join(conf, 'index' + sfx + '.html'), html)
            write(os.path.join(conf, dname), payload)

        # 主题页
        for tkey, lst in by_topic.items():
            name, _col = TOPIC_MAP.get(tkey, FALLBACK_TOPIC[:2])
            html, payload, dname = make_list_page(
                f'{esc(name)}',
                f'{esc(t("topic_sub"))} {len(lst)} {esc(t("n_cards"))}。',
                lst, 1,
                f'<div class="crumb"><a href="../index{sfx}.html">{esc(t("home"))}</a>'
                f' / {esc(name)}</div>',
                data_name=tkey + sfx)
            write(os.path.join('topic', tkey + sfx + '.html'), html)
            write(os.path.join('topic', dname), payload)

        # 首页
        top = sorted([c for c in cards if c['overall'] is not None],
                     key=lambda x: (-x['overall'], -(x['relevance'] or 0)))[:24]
        conf_cards = []
        for conf in CONFS:
            lst = by_conf.get(conf, [])
            if not lst:
                continue
            o = [c['overall'] for c in lst if c['overall'] is not None]
            conf_cards.append(f'''<a class="conf" href="{conf}/index{sfx}.html">
<b>{esc(NAMES[conf])}</b><span>{len(lst)} {esc(t("n_cards"))}</span>
<div class="row"><em>{esc(t("avg"))} <i>{statistics.mean(o):.2f}</i></em>
<em>{esc(t("seven_plus"))} <i>{sum(1 for v in o if v >= 7)}</i></em></div></a>''')
        topic_cards = []
        for tkey, _name, col, _kw in TOPICS:
            lst = by_topic.get(tkey, [])
            if not lst:
                continue
            o = [c['overall'] for c in lst if c['overall'] is not None]
            navg = statistics.mean(o) if o else 0
            tname = _name if lang_code == 'zh' else TOPIC_EN[tkey]
            topic_cards.append(f'''<a class="conf" href="topic/{tkey}{sfx}.html">
<b><span style="display:inline-block;width:8px;height:8px;border-radius:2px;background:{col};margin-right:8px"></span>{esc(tname)}</b>
<span>{len(lst)} {esc(t("n_cards"))} · {esc(t("avg"))} {navg:.2f}</span></a>''')
        items = []
        for i, c in enumerate(top, 1):
            items.append(f'''<div class="item"><div class="num">{i}</div>
<div class="body"><a class="t" href="{c['conf']}/{c['slug']}{sfx}.html">{esc(c['title'])}</a>
<span class="o">{esc(NAMES[c['conf']])} · {esc(c['one_line'])}</span></div>
<div class="chips">{score_chips(c)}</div></div>''')
        welcome = '读懂一篇论文，发现一个新想法。' if lang_code == 'zh' else 'Read a paper. Discover your next idea.'
        intro = '从核心问题到方法与证据，探索 AI 顶会研究，建立自己的知识地图。' if lang_code == 'zh' else 'Explore ideas, methods and evidence from leading AI conferences.'
        search_label = '搜索论文、关键词，开启新的探索' if lang_code == 'zh' else 'Search papers and discover new ideas'
        body = f'''<div class="hero home-hero"><span class="hero-label">PAPER CARDS / RESEARCH LIBRARY</span><h1>{welcome}</h1><p>{intro}</p><a class="hero-search" href="search{sfx}.html"><span>⌕ &nbsp; {search_label}</span><b>→</b></a><div class="hero-tags"><a href="topic/llm{sfx}.html">LLM & Reasoning ↗</a><a href="topic/multimodal{sfx}.html">Multimodal ↗</a><a href="topic/medical{sfx}.html">Medical AI ↗</a></div></div>
<div class="stats">
<div class="stat"><b>{TOTAL}</b><span>{esc(t("stat_cards"))}</span></div>
<div class="stat"><b>{len(by_conf)}</b><span>{esc(t("stat_confs"))}</span></div>
<div class="stat"><b>{avg:.2f}</b><span>{esc(t("stat_avg"))}</span></div>
<div class="stat"><b>{hi}</b><span>{esc(t("stat_hi"))}</span></div>
</div>
<h2 class="sec">{esc(t("sec_topic"))} <small>{esc(t("sec_topic_s"))}</small></h2>
<div class="grid">{''.join(topic_cards)}</div>
<h2 class="sec">{esc(t("sec_conf"))} <small>{esc(t("sec_conf_s"))}</small></h2>
<div class="grid">{''.join(conf_cards)}</div>
<h2 class="sec">{esc(t("sec_top"))} <small>{esc(t("sec_top_s"))}</small></h2>
<div class="list">{''.join(items)}</div>'''
        write('index' + sfx + '.html', page(t('hero_h1'), body))

        # 搜索页
        sbody = (f'<div class="hero"><h1>{esc(t("search_h1"))}</h1><p>{esc(t("search_p"))}</p></div>\n'
                 f'<div class="toolbar"><input id="q" type="search" placeholder="{esc(t("search_ph"))}">'
                 f'<span class="cnt" id="cnt">{esc(t("loading"))}</span></div>\n'
                 '<div class="list" id="out"></div>\n'
                 f'<script>var PN_I18N={json.dumps({"loaded": t("loaded"), "hits": t("hits"), "no_match": t("no_match")}, ensure_ascii=False)};</script>\n'
                 f'<script>{SEARCH_JS}</script>')
        write('search' + sfx + '.html', page(t('search_h1'), sbody))

    LANG = 'zh'
    print('OK cards=%d confs=%d topics=%d (zh+en)' % (TOTAL, len(by_conf), len(by_topic)))


if __name__ == '__main__':
    build()
