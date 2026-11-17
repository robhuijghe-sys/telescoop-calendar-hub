"""Real additions, edits and bulk replacements stay in their selected day panels."""
import json
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
temp=tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name+'/calendar.db',CALENDAR_SNAPSHOT_PATH=temp.name+'/snapshot.json',
    APP_SECRET='test-only',ADMIN_RESET_PASSWORD='',ENABLE_ADMIN_RECOVERY_LOG='false',
    CALENDAR_SOURCE_GZ_B64='',CALENDAR_LINKS_GZ_B64='',CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus':{},'entries':[]}))
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from app.simple_calendar import app,rows_all,setup_editor
from app.calendar_dynamic import MONTH_PALETTES
import app.main as core

day=(datetime.now(core.TZ).date()+timedelta(days=1)).isoformat()
month=int(day[5:7])

def document(c):return BeautifulSoup(c.get('/smartschool-calendar').text,'html.parser')

with TestClient(app) as c:
    cases=[('secretariaat','Kopieën maken','practical'),('personeel','Nieuwe werkafspraak','meeting'),
           ('stage','Mentor maakt kennis','stage'),('waarschuwing','Teamoverleg gaat niet door','absence'),
           ('uitstap','VM: L3 - Uitstap (museum)','activities'),('ouders','Ouders komen langs','activities'),
           ('algemeen','Stagevoorbeeld in taal','activities')]
    for category,title,panel in cases:
        response=c.post('/kalender-toevoegen',data=dict(date=day,category=category,lines=title),follow_redirects=False)
        assert response.status_code==303,(category,response.text)
        doc=document(c)
        assert title.split(': ',1)[-1] in doc.select_one('.panel.'+panel).get_text()
    c.post('/kalender-toevoegen',data=dict(date=day,lines='Lien nascholing – geen sport vandaag'))
    c.post('/kalender-toevoegen',data=dict(date=day,lines='VM: Alex afwezig'))
    c.post('/kalender-toevoegen',data=dict(date=day,category='algemeen',whole_day='1',lines='VM: L3 - Sportdag'))
    doc=document(c)
    training=next(r for r in doc.select('.calendar-row') if 'Lien nascholing' in r.get_text())
    assert training.select_one('.moment').get_text()=='DAG'
    sport=next(r for r in doc.select('.calendar-row') if 'Sportdag' in r.get_text())
    assert sport.select_one('.moment').get_text()=='DAG'
    absence=next(r for r in doc.select('.calendar-row') if 'Alex afwezig' in r.get_text())
    assert absence.select_one('.moment').get_text()=='VM'
    colors=MONTH_PALETTES[month]
    assert all(color in doc.select_one('.day-header')['style'] for color in colors)
    css=doc.select_one('style').get_text()
    assert 'grid-template-columns:128px' in css and 'white-space:nowrap' in css
    assert '.panel.practical{border-color:#68991C}.practical h3{color:#68991C}' in css
    # Existing purple-pink meeting gradient now travels slowly without changing content.
    meeting_css = css.split('.panel.meeting{', 1)[1].split('}', 1)[0]
    assert 'linear-gradient(115deg,#A50092 0%,#DE00C4 25%,#ED60E1 47%,#CA08BC 68%,#94008F 100%) border-box' in meeting_css
    assert 'background-size:100% 100%,240% 240%' in meeting_css
    assert 'animation:stage-border-flow 24s ease-in-out infinite alternate' in meeting_css
    assert 'html .wrap .panel.meeting{animation:none;background-position:0 0,45% 50%}' in css
    from app.day_cards import scoped_css
    assert '.calendar-preview .panel.meeting{animation:none;background-position:0 0,45% 50%}' in scoped_css('.calendar-preview')
    assert '.item-text,.item-text *,.stage-item,.stage-item *,.stage-note,.stage-note *{color:#000000!important}' in css
    assert not any('color:' in n['style'] for n in doc.select('.panel [style]'))
    assert 'border-bottom:1px solid #edf0f5' not in css
    assert not doc.select('.activities [style*="#F09009"]')
    assert not doc.select('b,strong')
    # Selected types survive a full-day edit, including editing a generic task.
    edit=BeautifulSoup(c.get('/kalender-dag/'+day).text,'html.parser')
    rich=edit.select_one('textarea[name=body_html]').get_text().replace('Kopieën maken','Kopieën klaarzetten')
    assert c.post('/kalender-dag/'+day,data=dict(version=edit.select_one('input[name=version]')['value'],body_html=rich)).status_code==200
    doc=document(c)
    assert 'Kopieën klaarzetten' in doc.select_one('.practical').get_text()
    assert 'Sportdag' in next(r for r in doc.select('.calendar-row') if r.select_one('.moment').get_text()=='DAG' and 'Sportdag' in r.get_text()).get_text()
    # Re-selecting a type for the same text changes its panel without duplicating it.
    c.post('/kalender-toevoegen',data=dict(date=day,category='algemeen',lines='Kopieën klaarzetten'))
    doc=document(c)
    assert doc.get_text().count('Kopieën klaarzetten')==1
    assert 'Kopieën klaarzetten' in doc.select_one('.activities').get_text()
    # A search/replace keeps type and the full-day flag, and undo keeps them too.
    preview=BeautifulSoup(c.post('/kalender-vervangen/voorbeeld',data=dict(find='Nieuwe werkafspraak',replacement='Vernieuwde werkafspraak')).text,'html.parser')
    applied=c.post('/kalender-vervangen/toepassen',data={'token':preview.select_one('input[name=token]')['value']})
    assert 'Vernieuwde werkafspraak' in document(c).select_one('.meeting').get_text()
    undo=BeautifulSoup(applied.text,'html.parser').select_one('input[name=token]')['value']
    assert c.post('/kalender-vervangen/ongedaan-maken',data={'token':undo}).status_code==200
    assert 'Nieuwe werkafspraak' in document(c).select_one('.meeting').get_text()
    before=rows_all()
    setup_editor()
    assert rows_all()==before
    assert 'Kopieën klaarzetten' in document(c).select_one('.activities').get_text()
    assert c.post('/kalender-toevoegen',data=dict(date=day,category='unknown',lines='Ongeldige keuze')).status_code==400
    # An imported activity heading remains before its timed instructions.
    con=core.db()
    con.execute('INSERT INTO editor_lines(date_local,body_html,title) VALUES(?,?,?)',
        (day,'Voorleessessie<br/>11u45: einde lessen<br/>11u55: verplaatsing','Voorleessessie\n11u45: einde lessen\n11u55: verplaatsing'))
    con.commit();con.close()
    program=document(c).select_one('.activities').get_text()
    assert program.index('Voorleessessie')<program.index('einde lessen')<program.index('verplaatsing')
    # A day containing only stages keeps the right column, even with absences above.
    stage_day=(datetime.now(core.TZ).date()+timedelta(days=2)).isoformat()
    c.post('/kalender-toevoegen',data=dict(date=stage_day,category='stage',lines='Stage: Noor bij K2'))
    doc=document(c)
    card=doc.select_one('[data-calendar-date="'+stage_day+'"]')
    columns=card.select_one('.day-columns')
    assert columns.select_one(':scope > .day-main').get_text()==''
    stage=columns.select_one(':scope > .day-stages > .stage')
    assert stage.select_one('.stage-name').get_text()=='Noor'
    assert 'bij K2' in stage.get_text() and 'Stage:' not in stage.get_text()
    c.post('/kalender-toevoegen',data=dict(date=stage_day,category='waarschuwing',lines='VM: Alex afwezig'))
    card=document(c).select_one('[data-calendar-date="'+stage_day+'"]')
    body=card.select_one('.calendar-body')
    assert body.select_one(':scope > .absence') is not None
    assert body.find(recursive=False).get('class')==['panel','absence']
    assert card.select_one('.day-columns > .day-stages > .stage') is not None
    assert any(r['title']=='Stage: Noor bij K2' for r in rows_all())

    # A real-world Friday: three absences stay above every replacement,
    # even when records were entered in a mixed order or use lesson periods.
    friday=(datetime.now(core.TZ).date()+timedelta(days=3)).isoformat()
    entries=[
        'DAG: Chantal afwezig',
        'DAG: Rob afwezig',
        '13u00 - 13u20: KS - Marinela vervangt Guler voor toezicht (speelplaats)',
        'DAG: Ananda afwezig',
        '2de en 3de lesuur: GR3 - Eline (vervangt Ananda)',
        '4de lesuur: L2 - Helena (NED, vervangt Ananda)',
        '5de lesuur: L2 - Helena (NED, vervangt Ananda)',
        '6de lesuur: L1 - Axelle (WO thema, vervangt Ananda)',
        '3de lesuur: L4 - Frans: Christophe',
        '4de lesuur: L4 - Spelling: Milla (50 min, waarvan 25 min digitaal)',
    ]
    for entry in entries:
        assert c.post('/kalender-toevoegen',data=dict(
            date=friday,category='waarschuwing',lines=entry
        ),follow_redirects=False).status_code==303
    card=document(c).select_one('[data-calendar-date="'+friday+'"]')
    panel=card.select_one('.panel.absence')
    lines=panel.select('.calendar-row')
    values=[r.select_one('.item-text').get_text(' ',strip=True) for r in lines]
    assert len(values)==len(entries),values
    assert ['Chantal afwezig','Rob afwezig','Ananda afwezig']==values[:3],values
    periods=[r.select_one('.moment').get_text(' ',strip=True) for r in lines]
    assert periods[3:]==[
        '2de en 3de lesuur','3de lesuur','4de lesuur','4de lesuur',
        '13u00 - 13u20','5de lesuur','6de lesuur'
    ],periods
    names=[r.select_one('.replacement-person').get_text(' ',strip=True)
           if r.select_one('.replacement-person') else None for r in lines]
    assert names==[None,None,None,'Eline','Christophe','Helena','Milla',
                   'Marinela','Helena','Axelle'],names
    assert '.wrap .panel.absence .replacement-person{font-weight:700!important}' in document(c).select_one('style').get_text()
    assert not card.select('b,strong')
    assert not any('Ananda'==span.get_text() or 'Guler'==span.get_text()
                   for span in card.select('.replacement-person'))

print('TCH_DAY_CARDS_SMOKE_TEST=PASS')
temp.cleanup()
