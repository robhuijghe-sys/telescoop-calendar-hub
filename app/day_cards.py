"""Responsive day cards reading the existing calendar without changing its text."""
import html
import json
import re
from difflib import SequenceMatcher

from bs4 import BeautifulSoup, NavigableString

from app.calendar_dynamic import MONTH_NAMES, MONTH_PALETTES, SEASONS, _event_line, category_for_row
from app.day_order import ABSENCE, AGENDA, is_meeting, is_replacement, ordered_fragments
from app.rich_editor import reshape_html, bullet_body, bullet_lists


TYPE_PANELS = {'waarschuwing':'absence', 'vervanging':'absence', 'stage':'stage',
               'secretariaat':'practical', 'praktisch':'practical', 'personeel':'meeting',
               'overleg':'meeting', 'onderhoud':'maintenance', 'ouders':'activities', 'uitstap':'activities', 'algemeen':'activities'}
PANEL_LABELS = {'absence':'Afwezigheden en vervangingen','activities':'Dagprogramma','practical':'Praktische afspraken','meeting':'Overleg en agenda','maintenance':'Onderhoud en klusjes','stage':'Stages'}
PANEL_TYPES = {'absence':'waarschuwing','activities':'algemeen','practical':'secretariaat','meeting':'personeel','maintenance':'onderhoud','stage':'stage'}
PRACTICAL = re.compile(r'^(?:Secretariaat\b|[^\w]*Check maximumfactuur|[^\w]*Evaluaties in Skore|[^\w]*IJskast\b|[^\w]*Banken\b)', re.I)
MOMENT = re.compile(r'^((?:\d{1,2}u\d{2})(?:\s*[-–]\s*\d{1,2}u\d{2})?|VM|NM|hele dag|DAG|\d+(?:ste|de)(?:\s+en\s+\d+(?:ste|de))?\s+lesuur)\s*:\s*', re.I)
WEEKDAYS = ['maandag','dinsdag','woensdag','donderdag','vrijdag','zaterdag','zondag']
CLASS_LABEL = re.compile(r'(?<!\w)(?:GR[1-3]|(?:L[1-6])+|(?:K[O0-3])+|[1-6](?:ste|de|e)\s+leerjaar)(?!\w)', re.I)

CSS = '''
*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#000000;font-size:14px;line-height:1.5;-webkit-text-size-adjust:100%}.wrap{max-width:1100px;margin:auto;padding:20px 12px 28px}.logo{display:block;width:100%;max-width:210px;height:auto;margin:0 auto 10px}.links{margin-bottom:20px}.quick{margin:0;font-size:12px;line-height:1.6}.quick a{color:#232563;text-decoration:none;border-bottom:1px solid #d8e1c9}.month-card{margin:0 0 26px;background:#fff}.month-head{padding:10px 16px;color:white;border-radius:10px;display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.month-title{font-size:22px;line-height:1.3}.season{font-size:11px;letter-spacing:.08em}.focus{padding:8px 2px 13px;color:#000000;font-size:13px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px}.calendar-day{margin:0 0 23px}.day-header{color:var(--day-color);background:transparent;border-radius:0;border-bottom:1px solid var(--day-line);padding:6px 0 10px;display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.day-header h2{font-size:16px;line-height:1.3;margin:0;font-weight:400}.day-header>span{font-size:12px;white-space:nowrap}.day-columns{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:14px;align-items:start}.day-main,.day-stages{min-width:0}.panel{color:#000000;line-height:1.15;border:1px solid #dce2ee;border-radius:12px;background:#fff;padding:14px 15px;margin-bottom:12px;min-width:0}.panel h3{font-size:15px;line-height:1.15;margin:0 0 8px;font-weight:700;color:#232563}.panel.absence{border-color:#E02020}.absence h3{color:#E02020}.panel.stage{border-color:#cee6f7}.stage h3{color:#2c719c}.panel.practical{border-color:#68991C}.practical h3{color:#68991C}.panel.maintenance{border-color:#8FA382}.maintenance h3{color:#8FA382}.panel.meeting{border-color:#D31996}.meeting h3{color:#D31996}.calendar-row{display:grid;grid-template-columns:128px minmax(0,1fr);gap:10px;padding:4px 0;align-items:baseline}.calendar-row:first-child{padding-top:0}.calendar-row:last-child{padding-bottom:1px}.item-text{min-width:0;overflow-wrap:anywhere;white-space:pre-wrap;font-size:14px;line-height:1.15}.moment{white-space:nowrap;font-size:12px;line-height:1.15;color:#000000}.absence-text,.training-text{color:#000000}.stage-item{margin:0 0 8px;color:#000000;font-size:14px;line-height:1.15;overflow-wrap:anywhere}.stage-item:last-child{margin-bottom:0}.stage-name{display:block;margin-bottom:0}.stage-detail{display:block;font-size:13px;line-height:1.15}.stage-note{font-size:13px;line-height:1.15;white-space:pre-wrap}.meeting-group,.meeting-group *{color:#000000!important;font-weight:400!important}.overleg-group,.overleg-group *{color:#000000!important;font-weight:400!important}.meeting-group+.meeting-group,.overleg-group+.meeting-group,.meeting-group+.overleg-group{margin-top:8px}.muted{color:#000000}.empty-day{padding:8px 15px}.wrap,.wrap *{font-weight:400!important}.wrap .month-title,.wrap .day-header h2,.wrap .panel h3,.wrap .activities .class-label,.wrap .activities .class-label *{font-weight:700!important}.panel,.panel *{line-height:1.15}.panel p,.panel div{margin-block-start:0}.item-text p,.item-text div{margin:0}.item-text,.item-text *,.stage-item,.stage-item *,.stage-note,.stage-note *{color:#000000!important}a:focus-visible{outline:3px solid #f7bf23;outline-offset:3px}
@media(max-width:720px){.wrap{padding:12px 8px 20px}.logo{max-width:170px}.day-columns{grid-template-columns:1fr;gap:0}.day-header{padding:6px 0 10px}.day-header h2{font-size:14px}.panel{padding:12px 13px}.calendar-row{grid-template-columns:112px minmax(0,1fr);gap:8px}.moment{font-size:12px}.month-title{font-size:20px}.season,.day-header>span{font-size:11px}}
@media print{.calendar-day{break-inside:avoid}.month-head,.day-header{print-color-adjust:exact;-webkit-print-color-adjust:exact}.wrap{max-width:none;padding:0}}
'''

CSS += '.calendar-bullets{list-style:disc;margin:0;padding-left:20px;white-space:normal}.calendar-bullets li{margin:0;padding:2px 0;white-space:pre-wrap}'


def scoped_css(scope):
    """Reuse the calendar styles in the management page without styling its forms."""
    def rule(match):
        selectors, declarations = match.groups()
        scoped = []
        for selector in selectors.split(','):
            selector = selector.strip()
            if selector in ('html','body'):
                scoped.append(scope)
            elif '.wrap' in selector:
                scoped.append(selector.replace('.wrap',scope))
            else:
                scoped.append(scope+' '+selector)
        return ','.join(scoped)+'{'+declarations+'}'
    return re.sub(r'([^{}]+)\{([^{}]*)\}',rule,CSS)


def emphasize_classes(rich):
    """Emphasize class labels, including labels split across styled text or links."""
    soup = BeautifulSoup(rich, 'html.parser')
    nodes = list(soup.find_all(string=True))
    labels = [match.span() for match in CLASS_LABEL.finditer(''.join(str(node) for node in nodes))]
    position = 0
    for node in nodes:
        text = str(node)
        end = position + len(text)
        ranges = [(max(start,position)-position,min(stop,end)-position)
                  for start,stop in labels if start < end and stop > position]
        if ranges:
            offset = 0
            for start,stop in ranges:
                if start > offset:node.insert_before(NavigableString(text[offset:start]))
                label = soup.new_tag('span', attrs={'class':'class-label'})
                label.string = text[start:stop]
                node.insert_before(label)
                offset = stop
            if offset < len(text):node.insert_before(NavigableString(text[offset:]))
            node.extract()
        position = end
    return str(soup)


def retain_metadata(s, originals, fragments):
    """Keep explicit types through a full-day edit, including small text edits."""
    candidates = []
    for row in originals:
        for fragment in s.split_lines(row['body_html']):
            candidates.append((s.plain(fragment), row.get('activity_type','auto'), row.get('whole_day',0)))
    result = []
    for fragment in fragments:
        text = s.plain(fragment)
        exact = next((i for i,c in enumerate(candidates) if c[0] == text), None)
        if exact is None and candidates:
            ranked = [(SequenceMatcher(None, text, c[0], autojunk=False).ratio(), i) for i,c in enumerate(candidates)]
            score, index = max(ranked)
            exact = index if score >= .65 else None
        result.append(candidates.pop(exact)[1:] if exact is not None else ('auto',0))
    return result


def render_calendar(s, hide_past=True, dates=None, cards_only=False, connection=None, editor_data=False, visible_from=None):
    selected = set(dates) if dates is not None else None
    owned = connection is None
    con = connection if connection is not None else s.core.db()
    try:
        if owned:con.execute('BEGIN')
        layout = json.loads(con.execute("SELECT value FROM settings WHERE key='editor_layout'").fetchone()[0])
        records = [dict(r) for r in con.execute('SELECT * FROM editor_lines WHERE deleted=0 ORDER BY date_local,id')]
        events = [dict(r) for r in con.execute('SELECT * FROM events WHERE visible_in_embed=1 ORDER BY start_at,id')]
        hidden = {r[0] for r in con.execute('SELECT date_local FROM editor_days WHERE hidden=1')}
        settings = dict(con.execute('SELECT key,value FROM settings'))
    finally:
        if owned:con.close()
    days = {e['date']:[] for e in layout.get('entries',[])}
    for row in records:
        if selected is not None and row['date_local'] not in selected:continue
        days.setdefault(row['date_local'],[]).append(dict(rich=s.without_bold(s.clean_html(row['body_html'])),type=row['activity_type'],
            whole_day=row['whole_day'],custom=row['custom_format'],event=False,record=('basis',row['id'])))
    for event in events:
        ds = s.datetime.fromisoformat(event['start_at']).astimezone(s.core.TZ).date().isoformat()
        if selected is not None and ds not in selected:continue
        days.setdefault(ds,[]).append(dict(rich=s.without_bold(s.clean_html(_event_line(event))),type=category_for_row(event),
            whole_day=event['all_day'],custom=bool(event['title_html'] or event['description_html']),event=True,record=('event',event['id'])))
    today = s.datetime.now(s.core.TZ).date()
    visible_from = visible_from if visible_from is not None else s.calendar_start_date()
    school_end = (today.year if today.month < 8 else today.year+1, 8)
    months = {}
    for ds,items in sorted(days.items()):
        day = s.datetime.fromisoformat(ds).date()
        if selected is not None and ds not in selected:continue
        if ds in hidden or (hide_past and day<visible_from) or (selected is None and ((day.year,day.month)<(today.year,today.month) or (day.year,day.month)>school_end)):
            continue
        months.setdefault((day.year,day.month),[]).append((ds,items))

    def panel_for(item, meeting=False, previous=None):
        if item['type'] in TYPE_PANELS:
            return TYPE_PANELS[item['type']]
        text = s.plain(item['rich'])
        if meeting or (AGENDA.match(text) and previous=='meeting'):
            return 'meeting'
        if re.search(r'\bstage(?:s|stagiair)?\b|\bstagiair',text,re.I):
            return 'stage'
        if ABSENCE.search(text) or is_replacement(text) or re.search(r'\bnascholing\b',text,re.I):
            return 'absence'
        if is_meeting(text):
            return 'meeting'
        if PRACTICAL.search(text):
            return 'practical'
        return 'activities'

    def content(item, key):
        soup = BeautifulSoup(item['rich'],'html.parser')
        for tag in soup.find_all(style=True):
            parts = []
            for part in tag['style'].split(';'):
                name,_,value = part.partition(':')
                if name.strip().lower() in ('font-weight','background-color','color'):
                    continue
                parts.append(part)
            if parts:tag['style']=';'.join(parts)
            else:del tag['style']
        rich = str(soup)
        return '<span data-custom-format="true">'+rich+'</span>' if item['custom'] else rich

    def moment_body(item):
        original = s.plain(item['rich'])
        match = MOMENT.match(original)
        label,body = (match[1],original[match.end():]) if match else ('',original)
        if label.lower() in ('hele dag','dag') or (item['whole_day'] and not AGENDA.match(original)):
            label='DAG'
        elif not label and re.search(r'\bnascholing\b',original,re.I):
            label='DAG'
        elif re.match(r'^GR\d\s*-\s*niet op school:\s*GWP\s+Bosklassen\b',body,re.I):
            label='DAG'
        return label,body,match

    def editable(item,key):
        rich=content(item,key)
        if key=='stage':
            text=re.sub(r'\bstage\b\s*[:–-]?\s*','',s.plain(item['rich']),flags=re.I).strip()
        else:
            label,body,_=moment_body(item)
            text=(label+': ' if label else '')+body
        return s.clean_html(reshape_html(rich,text))

    def row(item,key):
        original=s.plain(item['rich'])
        rich=content(item,key)
        label,body,match=moment_body(item)
        extra = ' absence-text' if key=='absence' and ABSENCE.search(original) else (' training-text' if key=='absence' and 'nascholing' in original.lower() else '')
        body_html = s.clean_html(reshape_html(rich,body)) if match else rich
        if key=='activities':body_html=emphasize_classes(body_html)
        # The time column is always present, aligning untimed rows as well.
        custom=' data-custom-format="true"' if item['custom'] else ''
        return f'<div class="calendar-row{extra}"><span class="moment">{html.escape(label)}</span><div class="item-text"{custom}>{body_html}</div></div>'

    def stage_item(item):
        rich = content(item,'stage')
        # The panel supplies the label; preserve the original text in storage.
        text = re.sub(r'\bstage\b\s*[:–-]?\s*', '', s.plain(item['rich']), flags=re.I).strip()
        rich = s.clean_html(reshape_html(rich,text))
        if item['description']:
            return '<div class="stage-note">'+rich+'</div>'
        head,*tail=re.split(r'\s+[–—-]\s+(?=toezicht)',text,maxsplit=1,flags=re.I)
        name,details=head,[]
        match=re.search(r'\s+(?:van\s+\d{1,2}u\d{2}\s+tot\s+\d{1,2}u\d{2}|bij\s+K\d)',head,re.I)
        if match:name,details=head[:match.start()],[head[match.start():].strip()]
        details+=tail
        custom=' data-custom-format="true"' if item['custom'] else ''
        return '<div class="stage-item"'+custom+'><span class="stage-name">'+s.clean_html(reshape_html(rich,name))+'</span> '+''.join('<span class="stage-detail">'+s.clean_html(reshape_html(rich,d))+'</span> ' for d in details)+'</div>'

    def rows(key, items):
        body, bullets = '', []
        def flush():
            if not bullets:return ''
            markup=bullet_lists(bullets)
            bullets.clear()
            if key=='stage':return '<div class="stage-note">'+markup+'</div>'
            return '<div class="calendar-row"><span class="moment"></span><div class="item-text">'+markup+'</div></div>'
        for item in items:
            if bullet_body(item['rich']) is not None:
                bullets.append(content(item,key))
            else:
                body+=flush()
                body+=stage_item(item) if key=='stage' else row(item,key)
        return body+flush()

    def panel(key,items):
        body=''
        if key=='stage':body=rows(key,items)
        elif key=='meeting':
            group=None
            grouped=[]
            for item in items:
                if item['group']!=group:
                    if group is not None:body+=rows(key,grouped)+'</div>'
                    grouped=[]
                    body+='<div class="'+item['meeting_class']+'">';group=item['group']
                grouped.append(item)
            if group is not None:body+=rows(key,grouped)+'</div>'
        else:body=rows(key,items)
        return f'<section class="panel {key}"><h3>{PANEL_LABELS[key]}</h3>'+body+'</section>'

    blocks=[]
    rendered={}
    editing={}
    for (year,month),entries in months.items():
        c1,c2=MONTH_PALETTES[month]
        gradient=f'background:linear-gradient(135deg,{c1} 0%,{c2} 100%)'
        focus=settings.get(f'month_focus_{year}_{month:02d}',layout.get('focus',{}).get(f'{year}-{month:02d}',''))
        focus_html=f'<div class="focus"><span class="dot" style="background:{c1}"></span>{html.escape(focus)}</div>' if focus else ''
        cards=[]
        for ds,items in entries:
            packed=[f'<span data-card-index="{i}">{item["rich"]}</span>' for i,item in enumerate(items)]
            buckets={k:[] for k in ('absence','activities','practical','meeting','maintenance','stage')}
            previous=None
            for group_index,fragment in enumerate(ordered_fragments(packed,style_meetings=True)):
                soup=BeautifulSoup(fragment,'html.parser')
                meeting=soup.select_one('.meeting-group,.overleg-group')
                for node in soup.select('[data-card-index]'):
                    source=items[int(node['data-card-index'])]
                    # Sort a stored activity as one unit, then draw its lines.
                    # This keeps its heading before instructions and times.
                    for line_index,rich in enumerate(s.split_lines(''.join(str(child) for child in node.contents))):
                        item=dict(source,rich=rich,description=source['event'] and line_index>0)
                        if item['description']:item['whole_day']=0
                        key=panel_for(item,bool(meeting),previous)
                        item['group']=group_index
                        item['meeting_class']=meeting['class'][0] if meeting else 'meeting-group'
                        if key=='meeting' and AGENDA.match(s.plain(item['rich'])) and buckets['meeting']:
                            item['group']=buckets['meeting'][-1]['group']
                            item['meeting_class']=buckets['meeting'][-1]['meeting_class']
                        buckets[key].append(item);previous=key
            activities=buckets['activities']
            heading=next((i for i,item in enumerate(activities) if re.fullmatch(r'digitale wolven\s*:?',s.plain(item['rich']),re.I)),None)
            slot=next((i for i,item in enumerate(activities) if re.search(r'\b(?:Panda|Scratch|Wunderkind|Digitale wolven)\b',s.plain(item['rich']),re.I) and i!=heading),None)
            if heading is not None and slot is not None and slot<heading:
                activities.insert(slot,activities.pop(heading))
            if editor_data:
                editing[ds]={key:[dict(item,rich=editable(item,key)) for item in bucket] for key,bucket in buckets.items()}
            day=s.datetime.fromisoformat(ds)
            label=WEEKDAYS[day.weekday()]+' '+str(day.day)+' '+MONTH_NAMES[month].lower()
            card=f'<article class="calendar-day" data-calendar-date="{ds}"><header class="day-header" style="--day-color:{c1};--day-line:{c2}"><h2>{label}</h2></header><div class="calendar-body">'
            if buckets['absence']:card+=panel('absence',buckets['absence'])
            left=''.join(panel(k,buckets[k]) for k in ('activities','practical','meeting','maintenance') if buckets[k])
            if buckets['stage']:
                card+='<div class="day-columns"><div class="day-main">'+left+'</div><aside class="day-stages" aria-label="Stages">'+panel('stage',buckets['stage'])+'</aside></div>'
            elif left:card+='<div class="day-main">'+left+'</div>'
            if not items:card+='<p class="muted empty-day">Nog geen inhoud.</p>'
            rendered[ds]=card+'</div></article>'
            cards.append(rendered[ds])
        blocks.append(f'<section class="month-card"><div class="month-head" style="{gradient}"><span class="month-title">{MONTH_NAMES[month]}</span><span class="season">{SEASONS[month]}</span></div>'+focus_html+''.join(cards)+'</section>')
    if editor_data:return {'cards':rendered,'sections':editing}
    if cards_only:return rendered
    return '<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="7200"><title>Schoolkalender De Telescoop</title><style>'+CSS+'</style></head><body><main class="wrap"><img class="logo" src="https://telescoop-sgr8.smartschool.be/public/telescoop-sgr8/Images/P8JUKt6zzs28fnA9LjPg2owGK1768144749.PNG" alt="De Telescoop"><div class="links">'+s.links_html()+'</div>'+''.join(blocks)+'</main></body></html>'
