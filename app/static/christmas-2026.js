(() => {
  'use strict';
  const { start, end } = document.currentScript.dataset;
  const startsAt = Date.parse(start);
  const endsAt = Date.parse(end);
  const root = document.documentElement;
  const teachers = {
    ananda: 'vrolijke', annamarie: 'hartelijke', ariane: 'warme', axelle: 'creatieve',
    chantal: 'hartelijke', charlotte: 'stralende', christophe: 'enthousiaste',
    eline: 'vrolijke', güler: 'warme', guler: 'warme', hanne: 'goedgemutste',
    helena: 'zorgzame', jorge: 'vrolijke', kathy: 'hartelijke', kim: 'creatieve',
    lien: 'zorgzame', liese: 'stralende', magda: 'warme', maïlis: 'vrolijke',
    mailis: 'vrolijke', marinela: 'enthousiaste', mila: 'creatieve', milla: 'creatieve',
    noëmi: 'stralende', noemi: 'stralende', rob: 'goedgemutste', rudi: 'hartelijke',
    silke: 'enthousiaste', sofie: 'zorgzame', steven: 'vrolijke',
    veronica: 'warme', wout: 'goedgemutste'
  };
  const names = Object.keys(teachers).flatMap(name => [name, name.normalize('NFD')]);
  const nameTokens = [...new Set(['anna[ \\p{Pd}]?marie', ...names])];
  const tokenBoundary = '[\\p{L}\\p{M}\\p{N}_]';
  const pattern = new RegExp('(?<!' + tokenBoundary + ')(?:' + nameTokens.join('|') + ')(?!' + tokenBoundary + ')', 'giu');
  let timer;

  function restore() {
    clearTimeout(timer);
    root.classList.remove('christmas-2026', 'christmas-paused');
    document.querySelectorAll('.christmas-name').forEach(node => node.replaceWith(document.createTextNode(node.dataset.originalName)));
    ['christmas-hero', 'christmas-style', 'christmas-script'].forEach(id => document.getElementById(id)?.remove());
    document.removeEventListener('visibilitychange', checkExpiry);
    window.removeEventListener('pageshow', checkExpiry);
  }

  function checkExpiry() {
    clearTimeout(timer);
    const now = Date.now();
    if (now < startsAt || now >= endsAt) {
      restore();
      return false;
    }
    timer = setTimeout(checkExpiry, Math.min(endsAt - now, 60000));
    return true;
  }

  if (!checkExpiry()) return;
  document.querySelectorAll('.calendar-day .item-text, .calendar-day .stage-detail, .calendar-day .stage-note, .focus').forEach(panel => {
    const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        return node.parentElement?.closest('script,style,textarea,input,select,button,a,[contenteditable],.christmas-name') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
      }
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const text = node.nodeValue;
      const matches = [...text.matchAll(pattern)];
      if (!matches.length) return;
      const fragment = document.createDocumentFragment();
      let position = 0;
      matches.forEach(match => {
        const originalName = match[0];
        const name = originalName.normalize('NFC').toLocaleLowerCase('nl-BE').replace(/[ \p{Pd}]/gu, '');
        fragment.append(text.slice(position, match.index));
        const wrapper = document.createElement('span');
        wrapper.className = 'christmas-name';
        wrapper.dataset.originalName = originalName;
        const adjective = document.createElement('span');
        adjective.className = 'christmas-adjective';
        adjective.textContent = teachers[name] + ' ';
        wrapper.append(adjective, originalName);
        fragment.append(wrapper);
        position = match.index + originalName.length;
      });
      fragment.append(text.slice(position));
      node.replaceWith(fragment);
    });
  });

  const motion = document.getElementById('christmas-motion');
  motion.hidden = false;
  motion.addEventListener('click', () => {
    const paused = root.classList.toggle('christmas-paused');
    motion.setAttribute('aria-pressed', String(paused));
    motion.firstElementChild.textContent = paused ? 'Animaties hervatten' : 'Animaties pauzeren';
  });
  document.addEventListener('visibilitychange', checkExpiry);
  window.addEventListener('pageshow', checkExpiry);
})();
