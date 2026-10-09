/* One editor per field; no remote dependencies or background requests. */
(() => {
  function safeHTML(value) {
    const doc = new DOMParser().parseFromString(value, 'text/html');
    doc.querySelectorAll('script,style,iframe,object,svg,math,template').forEach(el => el.remove());
    const allowed = new Set(['SPAN','B','STRONG','I','EM','U','A','BR','P','DIV','FONT']);
    doc.body.querySelectorAll('*').forEach(el => {
      if (!allowed.has(el.tagName)) { el.replaceWith(...el.childNodes); return; }
      const color = el.getAttribute('color');
      const style = ['color','background-color','font-weight','font-style','text-decoration']
        .map(key => [key, el.style.getPropertyValue(key)]).filter(([, val]) => val && !/url\s*\(/i.test(val));
      const href = el.getAttribute('href');
      [...el.attributes].forEach(attr => el.removeAttribute(attr.name));
      style.forEach(([key, val]) => el.style.setProperty(key, val));
      if (el.tagName === 'FONT') {
        const span = doc.createElement('span');
        span.style.cssText = el.style.cssText;
        if (color && CSS.supports('color', color)) span.style.color = color;
        span.append(...el.childNodes); el.replaceWith(span);
      } else if (el.tagName === 'A') {
        if (href && (/^https?:\/\//i.test(href) || /^\/(?!\/)/.test(href))) {
          el.setAttribute('href', href); el.setAttribute('target', '_blank'); el.setAttribute('rel', 'noopener noreferrer');
        } else el.replaceWith(...el.childNodes);
      }
    });
    // Calendar entries use line breaks, never paragraph blocks.
    doc.body.querySelectorAll('p,div').forEach(el => {
      if (el.previousSibling && el.previousSibling.nodeName !== 'BR') el.before(doc.createElement('br'));
      if (el.nextSibling && el.nextSibling.nodeName !== 'BR') el.after(doc.createElement('br'));
      const span = doc.createElement('span');
      span.style.cssText = el.style.cssText;
      span.append(...el.childNodes); el.replaceWith(span);
    });
    return doc.body.innerHTML;
  }
  document.querySelectorAll('.html-editor').forEach(root => {
    const source = root.querySelector('textarea');
    const visual = root.querySelector('.editor-visual');
    const tools = root.querySelector('.editor-tools');
    const picker = tools.querySelector('input[type=color]');
    const error = root.querySelector('.editor-error');
    let selection = null, sourceMode = false;
    visual.innerHTML = safeHTML(source.value);
    source.hidden = true; visual.hidden = false; tools.hidden = false;
    const form = root.closest('form');
    const type = form.querySelector('[data-calendar-type]');
    if (type) {
      const updateType = () => {
        const option = type.selectedOptions[0], color = option.dataset.color;
        visual.style.color = color || '';
        visual.style.fontWeight = ['stage','secretariaat'].includes(type.value) ? '700' : '';
        if (color) picker.value = color;
        visual.dataset.placeholder = option.dataset.placeholder;
        source.placeholder = option.dataset.placeholder;
        form.querySelector('#activity-type-help').textContent = option.dataset.help;
        form.querySelector('.type-color-dot').style.backgroundColor = color || '#fff';
        form.querySelector('.type-color-text').textContent = color
          ? 'Automatische kleur: ' + option.dataset.colorName + '. Je kunt de tekstkleur hieronder aanpassen.'
          : 'De kleur wordt automatisch per regel gekozen.';
      };
      type.addEventListener('change', updateType);
      updateType();
    }
    const remember = () => {
      const selected = window.getSelection();
      if (selected.rangeCount && visual.contains(selected.anchorNode) && visual.contains(selected.focusNode)) selection = selected.getRangeAt(0).cloneRange();
    };
    document.addEventListener('selectionchange', remember);
    const showVisual = () => {
      if (sourceMode) { visual.innerHTML = safeHTML(source.value); selection = null; }
      sourceMode = false; source.hidden = true; visual.hidden = false;
      tools.querySelector('[data-action=source]').setAttribute('aria-pressed', 'false');
    };
    const restore = () => {
      showVisual(); visual.focus();
      const selected = window.getSelection();
      const range = selection && visual.contains(selection.commonAncestorContainer) ? selection.cloneRange() : document.createRange();
      if (!selection || range.collapsed || !visual.contains(range.commonAncestorContainer)) range.selectNodeContents(visual);
      selected.removeAllRanges(); selected.addRange(range);
    };
    tools.addEventListener('mousedown', event => { if (event.target.closest('button')) event.preventDefault(); });
    tools.addEventListener('click', event => {
      const action = event.target.closest('button')?.dataset.action;
      if (!action) return;
      if (action === 'source') {
        if (sourceMode) { showVisual(); visual.focus(); }
        else {
          source.value = safeHTML(visual.innerHTML); sourceMode = true;
          source.hidden = false; visual.hidden = true;
          event.target.setAttribute('aria-pressed', 'true'); source.focus();
        }
        return;
      }
      restore();
      document.execCommand('styleWithCSS', false, true);
      if (action === 'color') document.execCommand('foreColor', false, picker.value);
      if (action === 'bold') document.execCommand('bold', false);
      if (action === 'clear') document.execCommand('removeFormat', false);
      remember(); source.value = safeHTML(visual.innerHTML);
    });
    visual.addEventListener('beforeinput', event => {
      if (event.inputType === 'insertParagraph') {
        event.preventDefault();
        document.execCommand('insertLineBreak', false);
      }
    });
    visual.addEventListener('paste', event => {
      event.preventDefault();
      const value = event.clipboardData.getData('text/plain');
      const escaped = document.createElement('div'); escaped.textContent = value;
      document.execCommand('insertHTML', false, escaped.innerHTML.replace(/\r?\n/g, '<br>'));
    });
    // Dropped markup must not bypass the paste/source sanitizer.
    visual.addEventListener('drop', event => event.preventDefault());
    form.addEventListener('submit', event => {
      source.value = safeHTML(sourceMode ? source.value : visual.innerHTML);
      const check = new DOMParser().parseFromString(source.value, 'text/html');
      const empty = !check.body.textContent.trim();
      let message = root.dataset.required === '1' && empty ? 'Vul tekst in voordat je opslaat.' : '';
      if (source.value.length > Number(root.dataset.limit)) message = 'De opgemaakte tekst is te lang. Kort de tekst in of wis overbodige opmaak.';
      error.textContent = message; error.hidden = !message;
      if (message) { event.preventDefault(); (sourceMode ? source : visual).focus(); }
    });
  });
})();
