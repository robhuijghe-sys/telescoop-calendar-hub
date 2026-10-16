"""Agenda lists survive day-panel editing and remain attached to their meetings."""
import json, os, sys, tempfile
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
from app.simple_calendar import app, clean_html, split_lines, plain
from app.day_cards import PANEL_LABELS
import app.main as core

day=(datetime.now(core.TZ).date()+timedelta(days=1)).isoformat()
def document(c):return BeautifulSoup(c.get('/smartschool-calendar').text,'html.parser')
def edit(c):
    soup=BeautifulSoup(c.get('/kalender-dag/'+day).text,'html.parser')
    return soup, {'version':soup.select_one('input[name=version]')['value'],'sections_present':'1',
        **{'body_'+key:soup.select_one('textarea[name=body_'+key+']').get_text() for key in PANEL_LABELS}}
def records():
    con=core.db()
    rows=[dict(r) for r in con.execute('SELECT * FROM editor_lines WHERE deleted=0 ORDER BY id')]
    con.close();return rows

with TestClient(app) as c:
    c.post('/kalender-toevoegen',data={'date':day,'lines_html':
        '9u00: Vakgroep NED<br/>* EDI spelling<br/>* Analyse <a href="https://example.org/klas">klasbeelden</a>'
        '<br/>15u30: Teamvergadering<br/>* Leerlingenraad<br/>* Evaluatie WO'})
    c.post('/kalender-toevoegen',data={'date':day,'category':'stage','lines':'Stage Noor van 8u30 tot 12u20'})
    soup=document(c)
    groups=soup.select('.meeting .meeting-group')
    assert len(groups)==2
    assert [li.get_text(' ',strip=True) for li in groups[0].select('li')]==['EDI spelling','Analyse klasbeelden']
    assert [li.get_text(' ',strip=True) for li in groups[1].select('li')]==['Leerlingenraad','Evaluatie WO']
    assert soup.select_one('.meeting li a')['href']=='https://example.org/klas'
    assert '*' not in soup.select_one('.meeting').get_text()
    stage=next(r for r in records() if 'Noor' in r['title'])
    soup,data=edit(c)
    assert len(soup.select('[data-action=bullets]'))==6
    assert len(BeautifulSoup(data['body_meeting'],'html.parser').select('ul li'))==4
    data['body_meeting']+='\n<ul><li>Nieuwe afspraak</li><li><a href="https://example.org/a">Actie opvolgen</a></li></ul>'
    data['body_practical']='<ul><li>Materiaal klaarzetten</li><li>Kopieën maken</li></ul>'
    response=c.post('/kalender-dag/'+day,data=data,follow_redirects=False)
    assert response.status_code==303,response.text
    soup=document(c)
    assert len(soup.select('.meeting li'))==6
    assert len(soup.select('.practical li'))==2
    assert soup.select_one('.meeting li a[href="https://example.org/a"]')
    assert next(r for r in records() if 'Noor' in r['title'])==stage
    saved=records()
    _,data=edit(c)
    assert c.post('/kalender-dag/'+day,data=data,follow_redirects=False).status_code==303
    assert records()==saved,'Opening and saving a list must not rewrite its records'
    data['body_meeting']=data['body_meeting'].replace('Nieuwe afspraak','Bijgewerkte afspraak')
    # Old version is still valid after the no-op save.
    assert c.post('/kalender-dag/'+day,data=data,follow_redirects=False).status_code==303
    assert 'Bijgewerkte afspraak' in document(c).select_one('.meeting').get_text()
    # A list cannot smuggle executable markup through the new formatting path.
    cleaned=clean_html('<ul onclick="evil()"><li><a href="javascript:evil()">Veilig</a><script>evil()</script></li></ul>')
    assert 'evil' not in cleaned and 'javascript' not in cleaned
    assert [plain(x) for x in split_lines(cleaned)]==['• Veilig']
print('PASS: existing stars, separate meeting agendas, links, panel lists, edits, no-op saves and sanitization')
