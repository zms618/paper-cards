(() => {
  const english = document.documentElement.lang === 'en';
  const label = (chinese, translated) => english ? translated : chinese;
  const main = document.querySelector('main');
  const title = document.querySelector('.ptitle');
  const read = key => { try { return JSON.parse(localStorage.getItem(key) || '[]'); } catch { return []; } };
  const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} };
  const libraryKey = 'paper-cards-reading-list';
  const libraryButton = document.createElement('button');
  libraryButton.className = 'langbtn library-button';
  libraryButton.textContent = label('稍后阅读', 'Reading list');
  document.querySelector('.topbar nav').prepend(libraryButton);
  const panel = document.createElement('dialog');
  panel.className = 'reading-dialog';
  document.body.append(panel);
  libraryButton.addEventListener('click', () => {
    panel.replaceChildren();
    const heading = document.createElement('h2');
    heading.textContent = label('你的阅读清单', 'Your reading list');
    const close = document.createElement('button');
    close.textContent = label('关闭', 'Close');
    close.className = 'reader-control';
    close.addEventListener('click', () => panel.close());
    panel.append(heading, close);
    const saved = read(libraryKey);
    if (!saved.length) {
      const empty = document.createElement('p');
      empty.textContent = label('在论文页点击“稍后阅读”，将感兴趣的论文留在这里。', 'Save papers from their reading pages to return to them here.');
      panel.append(empty);
    }
    saved.forEach(item => {
      const row = document.createElement('div');
      row.className = 'saved-paper';
      const link = document.createElement('a');
      link.href = item.url;
      link.textContent = item.title;
      const remove = document.createElement('button');
      remove.textContent = label('移除', 'Remove');
      remove.className = 'reader-control';
      remove.addEventListener('click', () => {
        write(libraryKey, read(libraryKey).filter(entry => entry.url !== item.url));
        row.remove();
        document.dispatchEvent(new Event('reading-list-updated'));
      });
      row.append(link, remove);
      panel.append(row);
    });
    panel.showModal();
  });
  const homeSearch = document.querySelector('.hero-search');
  if (homeSearch) {
    const form = document.createElement('form');
    form.className = 'hero-search';
    form.action = homeSearch.getAttribute('href');
    const input = document.createElement('input');
    input.type = 'search';
    input.name = 'q';
    input.placeholder = label('搜索论文标题、研究问题或关键词…', 'Search titles, research questions or keywords…');
    input.setAttribute('aria-label', label('搜索论文', 'Search papers'));
    const submit = document.createElement('button');
    submit.textContent = '→';
    submit.setAttribute('aria-label', label('搜索', 'Search'));
    form.append(input, submit);
    homeSearch.replaceWith(form);
  }
  const searchInput = document.querySelector('#q');
  const initialQuery = new URLSearchParams(location.search).get('q');
  if (searchInput && initialQuery) {
    searchInput.value = initialQuery;
    const count = document.querySelector('#cnt');
    let dispatched = false;
    const runSearch = () => {
      if (dispatched) return;
      dispatched = true;
      searchInput.dispatchEvent(new Event('input'));
      observer.disconnect();
    };
    const observer = new MutationObserver(runSearch);
    if (count && count.textContent.match(/\d/)) runSearch();
    else if (count) observer.observe(count, {childList: true, subtree: true});
  }
  if (!title) return;
  document.body.classList.add('paper-reading');
  const progress = document.createElement('div');
  progress.className = 'reading-progress';
  document.body.append(progress);
  const updateProgress = () => {
    const distance = document.documentElement.scrollHeight - innerHeight;
    progress.style.width = `${distance > 0 ? Math.min(100, scrollY / distance * 100) : 100}%`;
  };
  addEventListener('scroll', updateProgress, {passive: true});
  addEventListener('resize', updateProgress);
  const tools = document.createElement('div');
  tools.className = 'reader-tools';
  const button = (text, action) => {
    const control = document.createElement('button');
    control.className = 'reader-control';
    control.textContent = text;
    control.addEventListener('click', action);
    tools.append(control);
    return control;
  };
  const url = location.href.split('#')[0];
  const save = button('', () => {
    const saved = read(libraryKey);
    write(libraryKey, saved.some(item => item.url === url) ? saved.filter(item => item.url !== url) : [{url, title: title.textContent}, ...saved]);
    updateSaved();
  });
  function updateSaved() {
    const saved = read(libraryKey).some(item => item.url === url);
    save.textContent = saved ? label('✓ 已加入清单', '✓ Saved') : label('＋ 稍后阅读', '＋ Save paper');
    save.setAttribute('aria-pressed', String(saved));
  }
  updateSaved();
  document.addEventListener('reading-list-updated', updateSaved);
  const focus = button(label('专注阅读', 'Focus mode'), () => {
    const enabled = document.body.classList.toggle('focus-reading');
    focus.textContent = enabled ? label('退出专注', 'Exit focus') : label('专注阅读', 'Focus mode');
    focus.setAttribute('aria-pressed', String(enabled));
    updateProgress();
  });
  let fontSize = 16;
  button('A−', () => { fontSize = Math.max(14, fontSize - 1); main.style.setProperty('--reader-size', `${fontSize}px`); updateProgress(); });
  button('A＋', () => { fontSize = Math.min(22, fontSize + 1); main.style.setProperty('--reader-size', `${fontSize}px`); updateProgress(); });
  title.after(tools);
  const contents = document.createElement('aside');
  contents.className = 'reader-contents';
  const contentsTitle = document.createElement('strong');
  contentsTitle.textContent = label('本篇导读', 'On this page');
  contents.append(contentsTitle);
  const sections = [...document.querySelectorAll('section.blk')];
  sections.forEach((section, index) => {
    section.id = `reading-section-${index}`;
    const link = document.createElement('a');
    link.href = `#${section.id}`;
    link.textContent = section.querySelector('h3').textContent;
    contents.append(link);
  });
  main.append(contents);
  const sectionObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      contents.querySelectorAll('a').forEach(link => link.classList.toggle('current', link.hash === `#${entry.target.id}`));
    });
  }, {rootMargin: '-10% 0px -60% 0px'});
  sections.forEach(section => sectionObserver.observe(section));
  updateProgress();
})();
