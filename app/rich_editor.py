"""Small shared HTML editor and formatting-preserving text normalization."""
import html
import re
from difflib import SequenceMatcher

from bs4 import BeautifulSoup, NavigableString


def without_bold(value):
    """Remove bold presentation while retaining every word, color and link."""
    soup = BeautifulSoup(value, 'html.parser')
    for tag in soup.find_all(('b', 'strong')):
        tag.unwrap()
    for tag in soup.find_all(style=True):
        style = ';'.join(part for part in tag['style'].split(';')
                         if not re.match(r'\s*font-weight\s*:', part, re.I))
        if style:
            tag['style'] = style
        else:
            del tag['style']
    return str(soup)


def fragment_text(value):
    soup = BeautifulSoup(value, 'html.parser')
    for br in soup.find_all('br'):
        br.replace_with('\n')
    for block in soup.find_all(('p', 'div')):
        block.append('\n')
    return soup.get_text().strip()


def inline_html(value):
    """Keep paragraphs valid inside a calendar line or a link label."""
    soup = BeautifulSoup(value, 'html.parser')
    for block in soup.find_all(('p', 'div')):
        block.name = 'span'
        block.insert_after(soup.new_tag('br'))
    while soup.contents and getattr(soup.contents[-1], 'name', None) == 'br':
        soup.contents[-1].extract()
    return compact_lines(str(soup))


def compact_lines(value):
    """One visible break per nonempty line, retaining inline styles and links."""
    value = re.sub(r'<br\s*/?>', '<br/>', value, flags=re.I)
    soup = BeautifulSoup(value, 'html.parser')
    for block in list(soup.find_all(('p', 'div'))):
        block.insert_before(soup.new_tag('br'))
        block.insert_after(soup.new_tag('br'))
        block.name = 'span'
    for node in list(soup.find_all(string=True)):
        if '\n' not in node and '\r' not in node:
            continue
        for i, part in enumerate(re.split(r'\r\n|\r|\n', str(node))):
            if i:
                node.insert_before(soup.new_tag('br'))
            if part:
                node.insert_before(NavigableString(part))
        node.extract()
    pending, has_text = None, False
    for node in list(soup.descendants):
        if getattr(node, 'name', None) == 'br':
            if pending is not None or not has_text:
                node.extract()
            else:
                pending = node
        elif isinstance(node, NavigableString):
            if not str(node).strip():
                if pending is not None or not has_text:
                    node.extract()
                continue
            pending, has_text = None, True
    if pending is not None:
        pending.extract()
    return str(soup)


def reshape_html(value, text):
    """Keep inline colors/links when structured notation or hours are normalized."""
    soup = BeautifulSoup(value, 'html.parser')
    links = [(tag, tag.get_text(), dict(tag.attrs)) for tag in soup.find_all('a') if tag.get_text()]
    nodes = list(soup.find_all(string=True))
    original = ''.join(str(node) for node in nodes)
    if not nodes:
        return html.escape(text)
    starts, pos = [], 0
    for node in nodes:
        starts.append(pos)
        pos += len(node)
    pieces = [''] * len(nodes)
    for op, a, b, c, d in SequenceMatcher(None, original, text, autojunk=False).get_opcodes():
        if op == 'equal':
            for i, node in enumerate(nodes):
                left, right = max(a, starts[i]), min(b, starts[i] + len(node))
                if left < right:
                    pieces[i] += original[left:right]
        elif op in ('replace', 'insert'):
            index = next((i for i, node in enumerate(nodes) if a < starts[i] + len(node)), len(nodes) - 1)
            pieces[index] += text[c:d]
    for node, piece in zip(nodes, pieces):
        node.replace_with(NavigableString(piece))
    for tag, label, attrs in links:
        if tag.get_text() == label or label not in text:
            continue
        tag.unwrap()
        for node in list(soup.find_all(string=True)):
            if node.find_parent('a') or label not in str(node):
                continue
            before, after = str(node).split(label, 1)
            link = soup.new_tag('a', attrs=attrs)
            link.string = label
            node.insert_before(NavigableString(before))
            node.insert_before(link)
            node.insert_before(NavigableString(after))
            node.extract()
            break
    return str(soup)


def editor(name, value='', label='Tekst', required=False, limit=20000, placeholder='', field_id=None):
    """Values must already be sanitized. Unique IDs also work on the links page."""
    ident = 'editor-' + (field_id or name)
    return f'''<div class="html-editor" data-required="{int(required)}" data-limit="{limit}">
      <label id="{ident}-label" for="{ident}-source">{html.escape(label)}</label>
      <div class="editor-tools" hidden role="group" aria-label="Tekstopmaak">
        <label>Kleur <input type="color" value="#203555" aria-label="Tekstkleur"></label>
        <button type="button" data-action="color">Kleur toepassen</button>
        <button type="button" data-action="bold" aria-label="Vet">Vet</button>
        <button type="button" data-action="clear">Opmaak wissen</button>
        <button type="button" data-action="source" aria-pressed="false">HTML</button>
      </div>
      <div class="editbox editor-visual" hidden contenteditable="true" role="textbox" aria-multiline="true" aria-labelledby="{ident}-label" data-placeholder="{html.escape(placeholder, quote=True)}"></div>
      <textarea class="editor-source" id="{ident}-source" name="{html.escape(name, quote=True)}" rows="5" maxlength="{limit}" placeholder="{html.escape(placeholder, quote=True)}">{html.escape(value)}</textarea>
      <p class="muted editor-help">Selecteer tekst om een deel te kleuren. Zonder selectie pas je het hele veld aan. Via HTML kun je de broncode bewerken.</p>
      <p class="editor-error" role="alert" hidden></p>
    </div>'''


EDITOR_CSS = '''
.html-editor{margin:12px 0}.editor-tools{display:flex;align-items:center;flex-wrap:wrap;gap:6px;padding:8px;background:#edf1f7;border:1px solid #c9c2bd;border-bottom:0;border-radius:8px 8px 0 0}
.editor-tools[hidden],.editor-visual[hidden],.editor-source[hidden],.editor-error[hidden]{display:none}
.editor-tools label{display:flex;align-items:center;gap:6px;margin:0;font-size:14px}.editor-tools input[type=color]{width:42px;height:34px;padding:2px;cursor:pointer}
.editor-tools button{font-size:14px;padding:7px 9px}.html-editor .editbox{background:white;border-radius:0 0 8px 8px;white-space:pre-wrap;overflow-wrap:anywhere;min-height:110px}.editbox:empty:before{content:attr(data-placeholder);color:#726761;pointer-events:none}
.html-editor textarea{font-family:monospace!important;min-height:130px}.editor-error{color:#8a2f2f}.editor-tools button[aria-pressed=true]{background:#672f57}.editor-visual p,.editor-visual div{margin:0}
.type-color{display:flex;align-items:center;gap:8px;font-size:14px}.type-color-dot{width:14px;height:14px;flex-shrink:0;border:1px solid #b9b9b9;border-radius:50%;background:#fff}
'''
