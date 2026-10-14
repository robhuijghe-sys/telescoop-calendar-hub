"""Independent day panels preserve untouched data and place edits explicitly."""
import json,os,sys,tempfile
from datetime import datetime,timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
temp=tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name+'/calendar.db',CALENDAR_SNAPSHOT_PATH=temp.name+'/snapshot.json',
                  APP_SECRET='test-only',ADMIN_RESET_PASSWORD='',ENABLE_ADMIN_RECOVERY_LOG='false',
                  CALENDAR_SOURCE_GZ_B64='',CALENDAR_LINKS_GZ_B64='',CALENDAR_SNAPSHOT_GZ_B64='')
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus':{},'entries':[]}))
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import app.main as core
from app.simple_calendar import app
from app.day_cards import PANEL_LABELS
day=(datetime.now(core.TZ).date()+timedelta(days=1)).isoformat()

def state():
    con=core.db()
    result=([dict(r) for r in con.execute('SELECT * FROM editor_lines WHERE deleted=0 ORDER BY id')],
            [dict(r) for r in con.execute('SELECT * FROM events WHERE visible_in_embed=1 ORDER BY id')])
    con.close()
    return result

def edit(c):
    soup=BeautifulSoup(c.get('/kalender-dag/'+day).text,'html.parser')
    data={'version':soup.select_one('input[name=version]')['value'],'sections_present':'1'}
    data.update({'body_'+key:soup.select_one('textarea[name=body_'+key+']').get_text() for key in PANEL_LABELS})
    return soup,data

def calendar(c):return BeautifulSoup(c.get('/smartschool-calendar').text,'html.parser')

with TestClient(app) as c:
    for category,text,extra in [
        ('waarschuwing','VM: Alex afwezig',{}),
        ('algemeen','VM: L3 - Sportdag',{'whole_day':'1'}),
        ('secretariaat','Kopieën maken',{}),
        ('personeel','15u30: Teamvergadering',{}),
        ('stage','Stage Noor bij K2',{}),
    ]:
        assert c.post('/kalender-toevoegen',data={'date':day,'category':category,'lines':text,**extra}).status_code==200
    c.post('/public/create',data={'date':day,'title':'Bibliotheek','start_time':'09:00','end_time':'10:00','category':'algemeen','description':'Boeken meenemen'})
    c.post('/kalender-toevoegen',data={'date':day,'category':'algemeen','lines_html':'L2 - <a href="https://example.org/info">Informatie</a>'})
    con=core.db()
    con.execute('INSERT INTO editor_lines(date_local,body_html,title,activity_type) VALUES(?,?,?,?)',
                (day,'Activiteitsintro<br/>11u45: einde lessen<br/>11u55: verplaatsing','Activiteitsintro\n11u45: einde lessen\n11u55: verplaatsing','algemeen'))
    con.commit();con.close()
    soup,data=edit(c)
    assert len(soup.select('[data-editor-panel]'))==5
    assert soup.select_one('.calendar-edit-panels > .absence')
    assert soup.select_one('.day-columns > .day-stages > .stage')
    assert 'Stage' not in BeautifulSoup(data['body_stage'],'html.parser').get_text()
    assert 'DAG: L3 - Sportdag' in BeautifulSoup(data['body_activities'],'html.parser').get_text()
    initial=state()
    assert c.post('/kalender-dag/'+day,data=data,follow_redirects=False).status_code==303
    assert state()==initial
    # Changing only practical agreements retains all other record IDs and events.
    data['body_practical']=data['body_practical'].replace('Kopieën maken','Kopieën klaarleggen')+'<br/>Teamoverleg voorbereiden'
    assert c.post('/kalender-dag/'+day,data=data,follow_redirects=False).status_code==303
    after=state()
    assert after[1]==initial[1]
    untouched=[r for r in initial[0] if r['activity_type']!='secretariaat']
    assert all(row in after[0] for row in untouched)
    assert 'Teamoverleg voorbereiden' in calendar(c).select_one('.practical').get_text()
    assert 'Teamoverleg voorbereiden' not in calendar(c).select_one('.meeting').get_text()
    # Moving a stage line places it in the target panel despite its wording.
    _,data=edit(c)
    moved=data['body_stage'];data['body_stage']=''
    data['body_activities']+='<br/>'+moved
    assert c.post('/kalender-dag/'+day,data=data,follow_redirects=False).status_code==303
    doc=calendar(c)
    assert 'Noor' in doc.select_one('.activities').get_text()
    assert not doc.select('.stage')
    assert doc.select_one('a[href="https://example.org/info"]')
    # The explicit day marker can be changed without keeping an old all-day flag.
    _,data=edit(c)
    data['body_activities']=data['body_activities'].replace('DAG: L3','VM: L3').replace('Activiteitsintro','Nieuwe activiteitsintro')
    assert c.post('/kalender-dag/'+day,data=data).status_code==200
    doc=calendar(c)
    sport=next(row for row in doc.select('.calendar-row') if 'Sportdag' in row.get_text())
    assert sport.select_one('.moment').get_text()=='VM'
    program=doc.select_one('.activities').get_text()
    assert program.index('Nieuwe activiteitsintro')<program.index('einde lessen')<program.index('verplaatsing')
    _,data=edit(c)
    current=state()
    incomplete={k:v for k,v in data.items() if k!='body_stage'}
    assert c.post('/kalender-dag/'+day,data=incomplete).status_code==400
    assert state()==current
    empty={**data,**{'body_'+key:'' for key in PANEL_LABELS}}
    assert c.post('/kalender-dag/'+day,data=empty).status_code==400
    assert state()==current
    # Stale submissions retain each unsaved panel and change no records.
    c.post('/kalender-toevoegen',data={'date':day,'category':'stage','lines':'Nieuwe stagiair'})
    current=state()
    data['body_practical']+='<br/>Mijn niet-opgeslagen afspraak'
    response=c.post('/kalender-dag/'+day,data=data)
    assert response.status_code==409
    error=BeautifulSoup(response.text,'html.parser')
    assert 'Mijn niet-opgeslagen afspraak' in error.select_one('textarea[name=body_practical]').get_text()
    assert state()==current
    _,fresh=edit(c)
    fresh['body_practical']+='<br/><span onclick="bad()">Veilige afspraak</span><script>bad()</script>'
    assert c.post('/kalender-dag/'+day,data=fresh).status_code==200
    rendered=c.get('/smartschool-calendar').text
    assert 'onclick=' not in rendered and '<script>bad()' not in rendered
    listing=BeautifulSoup(c.get('/kalender-wijzigen').text,'html.parser')
    ids=[node['id'] for node in listing.select('[id]')]
    assert len(ids)==len(set(ids))
    assert listing.select('.panel-edit[data-edit-panel=practical]')
print('TCH_SECTION_EDITOR_SMOKE_TEST=PASS')
temp.cleanup()
