"""Responsive day cards reading the existing calendar without changing its text."""
import html
import json
import re
from difflib import SequenceMatcher

from bs4 import BeautifulSoup

from app.calendar_dynamic import MONTH_NAMES, MONTH_PALETTES, SEASONS, _event_line, category_for_row
from app.day_order import ABSENCE, AGENDA, is_meeting, is_replacement, ordered_fragments
from app.rich_editor import reshape_html


TYPE_PANELS = {'waarschuwing':'absence', 'vervanging':'absence', 'stage':'stage',
               'secretariaat':'practical', 'praktisch':'practical', 'personeel':'meeting',
               'overleg':'meeting', 'ouders':'activities', 'uitstap':'activities', 'algemeen':'activities'}
PRACTICAL = re.compile(r'^(?:Secretariaat\b|[^\w]*Check maximumfactuur|[^\w]*Evaluaties in Skore|[^\w]*IJskast\b|[^\w]*Banken\b)', re.I)
MOMENT = re.compile(r'^((?:\d{1,2}u\d{2})(?:\s*[-–]\s*\d{1,2}u\d{2})?|VM|NM|hele dag|DAG|\d+(?:ste|de)(?:\s+en\s+\d+(?:ste|de))?\s+lesuur)\s*:\s*', re.I)
ORANGE = re.compile(r'#(?:f09009|ff8800|ff8c00|ffa500)|rgb\(\s*(?:240\s*,\s*144\s*,\s*9|255\s*,\s*(?:136|140|165)\s*,\s*0)\s*\)|\borange\b', re.I)
WEEKDAYS = ['maandag','dinsdag','woensdag','donderdag','vrijdag','zaterdag','zondag']

CSS = '''
*{box-sizing:border-box}html,body{margin:0;padding:0;background:#fff;color:#293447;font-size:14px;line-height:1.5;-webkit-text-size-adjust:100%}.wrap{max-width:1100px;margin:auto;padding:20px 12px 28px}.logo{display:block;width:100%;max-width:210px;height:auto;margin:0 auto 10px}.links{margin-bottom:20px}.quick{margin:0;font-size:12px;line-height:1.6}.quick a{color:#232563;text-decoration:none;border-bottom:1px solid #d8e1c9}.month-card{margin:0 0 26px;background:#fff}.month-head{padding:10px 16px;color:white;border-radius:10px;display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.month-title{font-size:22px;line-height:1.3}.season{font-size:11px;letter-spacing:.08em}.focus{padding:8px 2px 13px;color:#59677e;font-size:13px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px}.calendar-day{margin:0 0 23px}.day-header{color:white;border-radius:10px;padding:11px 16px;display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.day-header h2{font-size:19px;line-height:1.3;margin:0;font-weight:400}.day-header>span{font-size:12px;white-space:nowrap}.day-columns{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(0,1fr);gap:14px;align-items:start}.day-main,.day-stages{min-width:0}.panel{border:2px solid #dce2ee;border-radius:12px;background:#fff;padding:14px 15px;margin-bottom:12px;min-width:0}.panel h3{font-size:15px;line-height:1.3;margin:0 0 10px;font-weight:400;color:#232563}.panel.absence{border-color:#efd1d1}.absence h3{color:#ad373f}.panel.stage{border-color:#cee6f7}.stage h3{color:#2c719c}.panel.practical{border-color:#a2c647}.practical h3{color:#48691e}.panel.meeting{border-color:#efd3e6}.meeting h3{color:#D31996}.calendar-row{display:grid;grid-template-columns:128px minmax(0,1fr);gap:10px;padding:7px 0;align-items:start}.calendar-row:first-child{padding-top:0}.calendar-row:last-child{padding-bottom:1px}.item-text{min-width:0;overflow-wrap:anywhere;white-space:pre-wrap;font-size:14px;line-height:1.5}.moment{white-space:nowrap;font-size:12px;line-height:1.75;color:#68738a}.absence .calendar-row{padding:3px 0}.absence-text{color:#D32F2F}.training-text{color:#c614a1}.stage-item{margin:0 0 12px;color:#2c719c;font-size:14px;line-height:1.5;overflow-wrap:anywhere}.stage-item:last-child{margin-bottom:0}.stage-name{display:block;margin-bottom:4px}.stage-detail{display:block;font-size:13px;line-height:1.6}.stage-note{font-size:13px;line-height:1.6;white-space:pre-wrap}.meeting-group,.meeting-group *{color:#D31996!important;font-weight:400!important}.overleg-group,.overleg-group *{color:#000000!important;font-weight:400!important}.meeting-group+.meeting-group,.overleg-group+.meeting-group,.meeting-group+.overleg-group{margin-top:10px}.muted{color:#68738a}.empty-day{padding:8px 15px}.wrap,.wrap *{font-weight:400!important}.panel p,.panel div{margin-block-start:0}.item-text p,.item-text div{margin:0}a:focus-visible{outline:3px solid #f7bf23;outline-offset:3px}
@media(max-width:720px){.wrap{padding:12px 8px 20px}.logo{max-width:170px}.day-columns{grid-template-columns:1fr;gap:0}.day-header{padding:10px 13px}.day-header h2{font-size:17px}.panel{padding:12px 13px}.calendar-row{grid-template-columns:112px minmax(0,1fr);gap:8px}.moment{font-size:12px}.month-title{font-size:20px}.season,.day-header>span{font-size:11px}}
@media print{.calendar-day{break-inside:avoid}.month-head,.day-header{print-color-adjust:exact;-webkit-print-color-adjust:exact}.wrap{max-width:none;padding:0}}
'''


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


def render_calendar(s, hide_past=True):
    con = s.core.db()
    try:
        con.execute('BEGIN')
        layout = json.loads(con.execute("SELECT value FROM settings WHERE key='editor_layout'").fetchone()[0])
        records = [dict(r) for r in con.execute('SELECT * FROM editor_lines WHERE deleted=0 ORDER BY date_local,id')]
        events = [dict(r) for r in con.execute('SELECT * FROM events WHERE visible_in_embed=1 ORDER BY start_at,id')]
        hidden = {r[0] for r in con.execute('SELECT date_local FROM editor_days WHERE hidden=1')}
        settings = dict(con.execute('SELECT key,value FROM settings'))
    finally:
        con.close()
    days = {e['date']:[] for e in layout.get('entries',[])}
    for row in records:
        days.setdefault(row['date_local'],[]).append(dict(rich=s.without_bold(s.clean_html(row['body_html'])),type=row['activity_type'],
            whole_day=row['whole_day'],custom=row['custom_format'],event=False))
    for event in events:
        ds = s.datetime.fromisoformat(event['start_at']).astimezone(s.core.TZ).date().isoformat()
        days.setdefault(ds,[]).append(dict(rich=s.without_bold(s.clean_html(_event_line(event))),type=category_for_row(event),
            whole_day=event['all_day'],custom=bool(event['title_html'] or event['description_html']),event=True))
    today = s.datetime.now(s.core.TZ).date()
    school_end = (today.year if today.month < 8 else today.year+1, 8)
    months = {}
    for ds,items in sorted(days.items()):
        day = s.datetime.fromisoformat(ds).date()
        if ds in hidden or (hide_past and day<today) or (day.year,day.month)<(today.year,today.month) or (day.year,day.month)>school_end:
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
                if name.strip().lower() in ('font-weight','background-color'):
                    continue
                if name.strip().lower()=='color' and (key=='activities' and ORANGE.search(value)):
                    continue
                parts.append(part)
            if parts:tag['style']=';'.join(parts)
            else:del tag['style']
        rich = str(soup)
        return '<span data-custom-format="true">'+rich+'</span>' if item['custom'] else rich

    def row(item,key):
        original = s.plain(item['rich'])
        rich = content(item,key)
        match = MOMENT.match(original)
        label,body = (match[1],original[match.end():]) if match else ('',original)
        if label.lower() in ('hele dag','dag') or (item['whole_day'] and not AGENDA.match(original)):
            label='DAG'
        elif not label and re.search(r'\bnascholing\b',original,re.I):
            label='DAG'
        elif re.match(r'^GR\d\s*-\s*niet op school:\s*GWP\s+Bosklassen\b',body,re.I):
            label='DAG'
        extra = ' absence-text' if key=='absence' and ABSENCE.search(original) else (' training-text' if key=='absence' and 'nascholing' in original.lower() else '')
        body_html = s.clean_html(reshape_html(rich,body)) if match else rich
        # The time column is always present, aligning untimed rows as well.
        custom=' data-custom-format="true"' if item['custom'] else ''
        return f'<div class="calendar-row{extra}"><span class="moment">{html.escape(label)}</span><div class="item-text"{custom}>{body_html}</div></div>'

    def stage_item(item):
        rich = content(item,'stage')
        if item['description']:
            return '<div class="stage-note">'+rich+'</div>'
        text=s.plain(item['rich'])
        head,*tail=re.split(r'\s+[–—-]\s+(?=toezicht)',text,maxsplit=1,flags=re.I)
        name,details=head,[]
        match=re.search(r'\s+(?:van\s+\d{1,2}u\d{2}\s+tot\s+\d{1,2}u\d{2}|bij\s+K\d)',head,re.I)
        if match:name,details=head[:match.start()],[head[match.start():].strip()]
        details+=tail
        custom=' data-custom-format="true"' if item['custom'] else ''
        return '<div class="stage-item"'+custom+'><span class="stage-name">'+s.clean_html(reshape_html(rich,name))+'</span> '+''.join('<span class="stage-detail">'+s.clean_html(reshape_html(rich,d))+'</span> ' for d in details)+'</div>'

    def panel(key,items):
        labels={'absence':'Afwezigheden en vervangingen','activities':'Dagprogramma','practical':'Praktische afspraken','meeting':'Overleg en agenda','stage':'Stages'}
        body=''
        if key=='stage':body=''.join(stage_item(i) for i in items)
        elif key=='meeting':
            group=None
            for item in items:
                if item['group']!=group:
                    if group is not None:body+='</div>'
                    body+='<div class="'+item['meeting_class']+'">';group=item['group']
                body+=row(item,key)
            if group is not None:body+='</div>'
        else:body=''.join(row(i,key) for i in items)
        return f'<section class="panel {key}"><h3>{labels[key]}</h3>'+body+'</section>'

    blocks=[]
    for (year,month),entries in months.items():
        c1,c2=MONTH_PALETTES[month]
        gradient=f'background:linear-gradient(135deg,{c1} 0%,{c2} 100%)'
        focus=settings.get(f'month_focus_{year}_{month:02d}') or layout.get('focus',{}).get(f'{year}-{month:02d}','')
        focus_html=f'<div class="focus"><span class="dot" style="background:{c1}"></span>{html.escape(focus)}</div>' if focus else ''
        cards=[]
        for ds,items in entries:
            packed=[f'<span data-card-index="{i}">{item["rich"]}</span>' for i,item in enumerate(items)]
            buckets={k:[] for k in ('absence','activities','practical','meeting','stage')}
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
            day=s.datetime.fromisoformat(ds)
            label=WEEKDAYS[day.weekday()]+' '+str(day.day)+' '+MONTH_NAMES[month].lower()
            card=f'<article class="calendar-day" data-calendar-date="{ds}"><header class="day-header" style="{gradient}"><h2>{label}</h2><span>Dagoverzicht</span></header><div class="calendar-body">'
            if buckets['absence']:card+=panel('absence',buckets['absence'])
            left=''.join(panel(k,buckets[k]) for k in ('activities','practical','meeting') if buckets[k])
            if left and buckets['stage']:
                card+='<div class="day-columns"><div class="day-main">'+left+'</div><aside class="day-stages" aria-label="Stages">'+panel('stage',buckets['stage'])+'</aside></div>'
            elif left:card+='<div class="day-main">'+left+'</div>'
            elif buckets['stage']:card+=panel('stage',buckets['stage'])
            if not items:card+='<p class="muted empty-day">Nog geen inhoud.</p>'
            cards.append(card+'</div></article>')
        blocks.append(f'<section class="month-card"><div class="month-head" style="{gradient}"><span class="month-title">{MONTH_NAMES[month]}</span><span class="season">{SEASONS[month]}</span></div>'+focus_html+''.join(cards)+'</section>')
    return '<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="7200"><title>Schoolkalender De Telescoop</title><style>'+CSS+'</style></head><body><main class="wrap"><img class="logo" src="https://telescoop-sgr8.smartschool.be/public/telescoop-sgr8/Images/P8JUKt6zzs28fnA9LjPg2owGK1768144749.PNG" alt="De Telescoop"><div class="links">'+s.links_html()+'</div>'+''.join(blocks)+'</main></body></html>'
