import base64, gzip, json, os, sys, tempfile
from pathlib import Path
from datetime import datetime as RealDatetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
tmp=tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=tmp.name+'/db',CALENDAR_SNAPSHOT_PATH=tmp.name+'/snapshot.json',CALENDAR_SNAPSHOT_GZ_B64='',CALENDAR_SOURCE_GZ_B64='',CALENDAR_LINKS_GZ_B64='',ADMIN_RESET_PASSWORD='',ENABLE_ADMIN_RECOVERY_LOG='false')
original={'focus':{},'entries':[{'date':'2026-10-01','html':'Original<br>Changed<br>Deleted'}]}
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps(original))
from fastapi.testclient import TestClient
import app.simple_calendar as editor
import app.calendar_snapshot as snapshot
import app.main as core
class Clock(RealDatetime):
    current='2026-09-30T21:59:59+00:00'
    @classmethod
    def now(cls,tz=None):
        return RealDatetime.fromisoformat(cls.current).astimezone(tz)
editor.datetime=snapshot.datetime=Clock
with TestClient(editor.app) as c:
    c.post('/kalender-regel/basis:2',data={'version':'1','date':'2026-10-01','body_html':'User change'})
    c.post('/kalender-verwijderen/basis:3',data={'version':'1'})
    c.post('/kalender-toevoegen',data={'date':'2026-10-01','lines':'Manual'})
    seed={'digest':'a'*64,'layout':{'entries':[{'date':'2026-10-01','html':''}], 'focus':{}},'lines':[{'date_local':'2026-10-01','body_html':x,'title':x} for x in ['New source','Changed','Deleted']], 'links':[]}
    os.environ['CALENDAR_SOURCE_GZ_B64']=base64.b64encode(gzip.compress(json.dumps(seed).encode())).decode()
    editor.setup_editor()
    assert {r['title'] for r in editor.rows_all()}=={'User change','Manual','New source'}
    editor.setup_editor()
    assert len(editor.rows_all())==3
    c.post('/public/create',data={'date':'2026-10-01','title':'Extra event'})
    c.post('/kalender-toevoegen',data={'date':'2026-10-02','lines':'Adjacent'})
    # Today stays visible until Belgian midnight, then both desktop/mobile hide it.
    Clock.current='2026-10-01T21:59:59+00:00'
    before=c.get('/smartschool-calendar')
    assert 'data-calendar-date="2026-10-01"' in before.text
    Clock.current='2026-10-01T22:00:00+00:00'
    after=c.get('/smartschool-calendar',headers={'If-None-Match':before.headers['etag']})
    assert after.status_code==200 and 'data-calendar-date="2026-10-01"' not in after.text
    assert len(editor.rows_all())==5
    Clock.current='2026-09-30T21:59:59+00:00'
    assert c.post('/kalender-dag-verwijderen',data={'date':'2026-02-30'}).status_code==400
    assert c.post('/kalender-dag-verwijderen',data={'date':'2026-10-01'}).status_code==200
    assert [r['title'] for r in editor.rows_all()]==['Adjacent']
    assert 'data-calendar-date="2026-10-01"' not in c.get('/smartschool-calendar').text
    assert c.post('/kalender-regel/basis:2',data={'version':'2','date':'2026-10-01','body_html':'Stale'}).status_code==404
    c.post('/kalender-dag-verwijderen',data={'date':'2026-10-01'})
    c.post('/public/create',data={'date':'2026-10-01','title':'Extra event'})
    assert 'data-calendar-date="2026-10-01"' in c.get('/smartschool-calendar').text
    assert {r['title'] for r in editor.rows_all()}=={'Extra event','Adjacent'}
    c.post('/kalender-dag-verwijderen',data={'date':'2026-10-01'})
    c.post('/kalender-toevoegen',data={'date':'2026-10-01','lines':'Restored with new lines'})
    assert {r['title'] for r in editor.rows_all()}=={'Restored with new lines','Adjacent'}
    editor.setup_editor()
    assert len(editor.rows_all())==2
    con=core.db()
    assert con.execute('SELECT count(*) FROM editor_lines WHERE deleted=1').fetchone()[0]>=5
    assert con.execute("SELECT count(*) FROM audit_log WHERE action='calendar.day_deleted'").fetchone()[0]==3
    con.close()
print('TCH_DAY_SOURCE_SMOKE_TEST=PASS')
