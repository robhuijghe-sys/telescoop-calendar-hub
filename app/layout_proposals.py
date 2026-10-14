"""Two read-only day layout proposals using calendar data at request time."""
import re

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from app.day_order import ABSENCE, is_meeting, is_replacement, ordered_fragments
from app.rich_editor import reshape_html


EXAMPLE = [
    ('#ff0000', 'VM: leerkrachten afwezig – begeleiding uitstap'),
    ('#ff00ff', 'Nascholing – geen sport vandaag'),
    ('#ff8800', 'VM: GR3 - Uitstap (museum)'),
    ('#203555', 'Voorleesmoment'),
    ('#203555', '11u45: einde lessen'),
    ('#203555', '11u45 - 11u55: opruimen (jassen en boekentassen mee)'),
    ('#203555', '11u55: verplaatsing naar lokaal'),
    ('#203555', '12u00: start voorleesmoment (tot 12u20)'),
    ('#ff8800', 'GR2 - niet op school: bosklassen'),
    ('#5dade2', 'Stage kleuterklas van 8u30 tot 12u40'),
    ('#5dade2', 'Stage lagere school – toezicht 10u40 - 10u55'),
]

CSS = '''
main{max-width:1440px}
.proposal-intro{max-width:850px}.proposal-picker{display:flex;gap:12px;align-items:end;flex-wrap:wrap}.proposal-picker>div{flex:1;min-width:180px}.proposal-picker input{box-sizing:border-box;width:100%}.proposal-picker button{width:auto;margin-bottom:0}.proposal-grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start}.proposal-column{min-width:0}.proposal-number{display:inline-flex;justify-content:center;align-items:center;width:28px;height:28px;margin-right:7px;border-radius:50%;background:var(--school-navy);color:white;font-size:15px}.proposal-column h2{font-size:21px;font-weight:400}.proposal-column>p{min-height:58px;font-size:14px;color:var(--muted);line-height:1.5}.proposal-classic{border:1px solid #e9d9c9;border-radius:12px;overflow:hidden;background:#fff}.proposal-month{padding:13px 16px;background:linear-gradient(135deg,#da5b12,#b24315);color:white;letter-spacing:1px}.proposal-cell{display:grid;grid-template-columns:100px 1fr;align-items:stretch}.proposal-date{padding:16px 10px;background:#fff5eb;color:#203555;line-height:1.6;border-right:1px solid #e9d9c9;font-size:14px}.proposal-lines{padding:16px;font-size:14px;line-height:1.65;overflow-wrap:anywhere}.proposal-lines,.proposal-lines *{font-weight:400!important}.proposal-space+.proposal-space{margin-top:18px}.proposal-line{white-space:pre-wrap}.proposal-board{background:#f5f7fb;border:1px solid #dce2ee;border-radius:16px;padding:18px;color:#203555}.proposal-board-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;border-bottom:1px solid #dce2ee;padding-bottom:14px;margin-bottom:16px}.proposal-board-heading h3{margin:0;font-size:21px;font-weight:400}.proposal-board-heading span{font-size:12px;white-space:nowrap;color:#5d6882}.proposal-panel{border-radius:10px;border:1px solid #dce2ee;background:white;margin-top:14px;padding:14px}.proposal-panel h4{margin:0 0 12px;color:#203555;font-size:15px;font-weight:400;display:flex;justify-content:space-between;gap:8px}.proposal-panel h4 span{font-size:12px;color:#66718b}.proposal-panel.absence{background:#fff6f6;border-color:#efd1d1}.proposal-panel.absence h4{color:#9a2626}.proposal-panel.stage{background:#f2f9ff;border-color:#cee6f7}.proposal-panel.stage h4{color:#23628b}.proposal-panel.meeting{background:#fff4fb;border-color:#f2d1e7}.proposal-panel.meeting h4{color:#9e2574}.proposal-board .proposal-line{font-size:14px;line-height:1.6;overflow-wrap:anywhere}.proposal-board .proposal-line+.proposal-line{margin-top:9px}.proposal-timeline{display:grid;grid-template-columns:72px 1fr;gap:10px;padding:9px 0;border-top:1px solid #eef0f4;font-size:14px;line-height:1.6;overflow-wrap:anywhere}.proposal-timeline:first-of-type{border-top:0;padding-top:0}.proposal-time{font-size:12px;color:#63718c;white-space:pre-line}.proposal-stage-item+.proposal-stage-item{border-top:1px solid #cee6f7;margin-top:12px;padding-top:12px}.proposal-stage-item{font-size:14px;line-height:1.6;overflow-wrap:anywhere}.proposal-footer{margin-top:24px;padding-top:16px;border-top:1px solid var(--line);line-height:1.6}.proposal-footer p{margin:8px 0}.proposal-empty{color:var(--muted);font-size:14px}@media(max-width:1150px){.proposal-grid{grid-template-columns:1fr}.proposal-column>p{min-height:0}.proposal-cell{grid-template-columns:95px 1fr}}@media(max-width:600px){.proposal-cell{grid-template-columns:1fr}.proposal-date{border-right:0;border-bottom:1px solid #e9d9c9;padding:8px 12px}.proposal-lines{padding:12px}.proposal-board{padding:12px}.proposal-board-heading{flex-wrap:wrap}.proposal-timeline{grid-template-columns:62px 1fr}.proposal-picker button{width:100%}}
'''


def register_layout_proposals(s):
    def groups(fragments):
        result = dict(absence=[], activities=[], meeting=[], stage=[])
        for fragment in ordered_fragments(fragments, style_meetings=True):
            text = s.plain(fragment)
            if 'class="meeting-group"' in fragment or 'class="overleg-group"' in fragment:
                key = 'meeting'
            elif re.search(r'\bstage(?:s|stagiair)?\b|\bstagiair', text, re.I):
                key = 'stage'
            elif ABSENCE.search(text) or is_replacement(text):
                key = 'absence'
            elif is_meeting(text) or 'class="meeting-group"' in fragment or 'class="overleg-group"' in fragment:
                key = 'meeting'
            else:
                key = 'activities'
            result[key].append(fragment)
        return result

    def lines(fragments):
        return ''.join('<div class="proposal-line">' + f + '</div>' for f in fragments)

    def timeline(fragments):
        result = ''
        pattern = re.compile(r'^((?:\d{1,2}u\d{2})(?:\s*-\s*\d{1,2}u\d{2})?|VM|NM|hele dag)\s*:\s*', re.I)
        for fragment in fragments:
            text = s.plain(fragment)
            match = pattern.match(text)
            if match:
                moment = match[1].replace(' - ', '\n– ')
                content = s.clean_html(reshape_html(fragment, text[match.end():]))
            else:
                moment, content = '', fragment
            result += '<div class="proposal-timeline"><div class="proposal-time">' + s.esc(moment) + '</div><div>' + content + '</div></div>'
        return result

    @s.app.get('/kalender-voorstellen')
    def proposals(date: str = ''):
        # Show today's existing contents (the screenshot's day), or the next
        # populated day. Calendar records never become public source literals.
        if not date:
            today = s.datetime.now(s.core.TZ).date().isoformat()
            available = sorted({r['date'] for r in s.rows_all() if r['date'] >= today})
            date = available[0] if available else ''
        if date:
            s.valid_date(date)
            con = s.core.db()
            try:
                con.execute('BEGIN')
                _, _, rich = s.day_records(con, date)
            finally:
                con.close()
            if not s.plain(rich):
                raise HTTPException(404, 'Deze dag heeft geen kalenderregels. Kies een andere datum of bekijk de voorbeelddag.')
            d = s.datetime.fromisoformat(date)
            label = ['maandag', 'dinsdag', 'woensdag', 'donderdag', 'vrijdag', 'zaterdag', 'zondag'][d.weekday()] + ' ' + d.strftime('%d/%m')
            month = ['JANUARI','FEBRUARI','MAART','APRIL','MEI','JUNI','JULI','AUGUSTUS','SEPTEMBER','OKTOBER','NOVEMBER','DECEMBER'][d.month-1]
            fragments = s.split_lines(rich)
        else:
            label, month = 'Voorbeelddag', 'SCHOOLKALENDER'
            fragments = [f'<span style="color:{color}">{s.esc(text)}</span>' for color, text in EXAMPLE]
        grouped = groups(fragments)
        spaces = ''.join('<div class="proposal-space">' + lines(grouped[key]) + '</div>'
                         for key in ('absence','activities','meeting','stage') if grouped[key])
        board = ''
        labels = dict(absence='Afwezigheden en vervangingen', activities='Dagprogramma', meeting='Overleg en agenda', stage='Stages')
        for key in ('absence','activities','meeting','stage'):
            items = grouped[key]
            if not items:
                continue
            contents = timeline(items) if key == 'activities' else lines(items)
            if key == 'stage':
                contents = ''.join('<div class="proposal-stage-item">' + f + '</div>' for f in items)
            board += (f'<section class="proposal-panel {key}"><h4>{labels[key]}<span>{len(items)} {"item" if len(items)==1 else "items"}</span></h4>'
                      + contents + '</section>')
        body = ('<div class="card"><div class="proposal-intro"><h2>Meer rust in het dagoverzicht</h2>'
                '<p>Beide voorstellen tonen dezelfde inhoud. De bestaande kalender blijft zoals hij is; dit zijn twee voorbeelden om te vergelijken.</p>'
                '<form class="proposal-picker"><div><label for="proposal-date">Bekijk met een eigen kalenderdag</label>'
                f'<input id="proposal-date" type="date" name="date" value="{s.esc(date, quote=True)}" required></div>'
                '<button>Dag bekijken</button><a class="btn alt" href="/kalender-voorstellen">Vandaag / eerstvolgende dag</a></form></div>'
                '<div class="proposal-grid"><section class="proposal-column"><h2><span class="proposal-number">1</span>De vertrouwde kalender, met ruimte</h2>'
                '<p>De datumkolom, tekstkleuren en compacte regels blijven. Eén witlijn scheidt afwezigheden, activiteiten, overleg en stages.</p>'
                f'<div class="proposal-classic"><div class="proposal-month">{month}</div><div class="proposal-cell"><div class="proposal-date">{label}</div>'
                '<div class="proposal-lines">' + spaces + '</div></div></div></section>'
                '<section class="proposal-column"><h2><span class="proposal-number">2</span>Een dagkaart met vaste blokken</h2>'
                '<p>Elke dag krijgt een eigen kaart. Aparte blokken en een tijdkolom laten meteen zien wie afwezig is, wat er gebeurt en welke stages er zijn.</p>'
                f'<div class="proposal-board"><div class="proposal-board-heading"><h3>{label}</h3><span>{sum(len(v) for v in grouped.values())} items</span></div>'
                + board + '</div></section></div>'
                '<div class="proposal-footer"><p>Mijn voorkeur: voorstel 1. Het geeft meer rust, past direct in Smartschool en houdt een lange schoolkalender compact.</p>'
                '<p>Voorstel 2 helpt sneller scannen en werkt goed op een telefoon, maar vraagt meer verticale ruimte per dag. Agendapunten blijven bij hun overleg staan.</p></div></div>')
        return HTMLResponse(s.page('Voorstellen dagoverzicht', body).replace('</style>', CSS + '</style>', 1))
