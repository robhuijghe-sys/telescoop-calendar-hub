(() => {
  'use strict';
  // Fixed instants: Belgian midnight, not the visitor's device timezone.
  const start = Date.parse('2026-10-30T00:00:00+01:00');
  const end = Date.parse('2026-11-01T00:00:00+01:00');
  const root = document.documentElement;
  const teachers = {
    annamarie: 'bezemvliegende', ariane: 'abracadabra-roepende', axelle: 'toverdrankbrouwende',
    chantal: 'ketelroerende', charlotte: 'spookjesvangende', christophe: 'pompoenbetoverende',
    eline: 'zwevende', guler: 'glinsterende', güler: 'glinsterende', hanne: 'hocuspocussende',
    helena: 'heksenhoeddragende', jorge: 'vleermuisfluisterende', kathy: 'knetterende',
    kim: 'maanlichtdansende', lien: 'lichtgevende', liese: 'spinnenwebbreiende',
    magda: 'maanlichtdansende', mailis: 'misttoverende', marinela: 'pompoenjodelende',
    milla: 'mummiedansende', noemi: 'nachtfladderende', 'noëmi': 'nachtfladderende',
    rob: 'spookdirigerende', rudi: 'toverende', silke: 'spookjeskietelende',
    sofie: 'bezemracende', steven: 'pompoenjonglerende', veronica: 'vleermuisdirigerende',
    wout: 'weerwolfwalsende'
  };
  const pattern = new RegExp('(?<![\\p{L}\\p{N}_])(' + Object.keys(teachers).sort((a,b) => b.length-a.length).join('|') + ')(?![\\p{L}\\p{N}_])', 'giu');
  let timer;

  function restore() {
    clearTimeout(timer);
    root.classList.remove('halloween-2026', 'halloween-paused');
    document.querySelectorAll('.halloween-name').forEach(node => node.replaceWith(document.createTextNode(node.dataset.originalName)));
    ['halloween-hero', 'halloween-decorations', 'halloween-style', 'halloween-script'].forEach(id => document.getElementById(id)?.remove());
    document.removeEventListener('visibilitychange', checkExpiry);
    window.removeEventListener('pageshow', checkExpiry);
  }

  function checkExpiry() {
    clearTimeout(timer);
    const now = Date.now();
    if (now < start || now >= end) { restore(); return false; }
    // Exact boundary for active tabs; visibility/pageshow cover sleeping tabs.
    timer = setTimeout(checkExpiry, Math.min(end-now, 60000));
    return true;
  }

  if (!checkExpiry()) return;
  document.querySelectorAll('.calendar-day .panel, .focus').forEach(panel => {
    const walker = document.createTreeWalker(panel, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        return node.parentElement?.closest('script,style,textarea,input,select,button,a,[contenteditable],.halloween-name') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT;
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
        fragment.append(document.createTextNode(text.slice(position, match.index)));
        const wrapper = document.createElement('span');
        wrapper.className = 'halloween-name';
        wrapper.dataset.originalName = match[0];
        const adjective = document.createElement('span');
        adjective.className = 'halloween-adjective';
        adjective.textContent = teachers[match[0].toLocaleLowerCase('nl-BE')] + ' ';
        wrapper.append(adjective, document.createTextNode(match[0]));
        fragment.append(wrapper);
        position = match.index + match[0].length;
      });
      fragment.append(document.createTextNode(text.slice(position)));
      node.replaceWith(fragment);
    });
  });
  document.getElementById('halloween-motion')?.addEventListener('click', event => {
    const paused = root.classList.toggle('halloween-paused');
    event.currentTarget.setAttribute('aria-pressed', String(paused));
    event.currentTarget.textContent = paused ? 'Spookjes laten zweven' : 'Spookjes pauzeren';
  });
  document.addEventListener('visibilitychange', checkExpiry);
  window.addEventListener('pageshow', checkExpiry);
})();
