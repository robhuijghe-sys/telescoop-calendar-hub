"""Monthly focus edits are visible in both views and reject stale saves."""
import json
import os
import sys
import tempfile
from datetime import datetime,timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
temp=tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name+'/calendar.db',CALENDAR_SNAPSHOT_PATH=temp.name+'/snapshot.json',
                  APP_SECRET='test-only',ADMIN_RESET_PASSWORD='',ENABLE_ADMIN_RECOVERY_LOG='false',
                  CALENDAR_SOURCE_GZ_B64='',CALENDAR_LINKS_GZ_B64='',CALENDAR_SNAPSHOT_GZ_B64='')
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
import app.main as core
day=(datetime.now(core.TZ).date()+timedelta(days=1)).isoformat()
month=day[:7]
Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus':{month:'Bestaande focus'},'entries':[{'date':day,'html':'L3 - Lezen'}]}))
from app.simple_calendar import app,rows_all

with TestClient(app) as c:
    before=rows_all()
    page=BeautifulSoup(c.get('/kalender-maandfocus/'+month).text,'html.parser')
    token=page.select_one('input[name=version]')['value']
    assert page.select_one('input[name=focus]')['value']=='Bestaande focus'
    assert c.post('/kalender-maandfocus/'+month,data={'version':token,'focus':'KS: onthaal • LS: spelling'},follow_redirects=False).status_code==303
    for url in ('/smartschool-calendar','/kalender-wijzigen'):
        assert 'KS: onthaal • LS: spelling' in c.get(url).text
    assert rows_all()==before
    assert c.post('/kalender-maandfocus/'+month,data={'version':token,'focus':'Verouderd'}).status_code==409
    assert 'Verouderd' not in c.get('/smartschool-calendar').text
    con=core.db()
    changes=con.execute("SELECT payload FROM audit_log WHERE action='calendar.month_focus_changed'").fetchall()
    assert len(changes)==1 and json.loads(changes[0][0])['before']=='Bestaande focus'
    con.close()
    fresh=BeautifulSoup(c.get('/kalender-maandfocus/'+month).text,'html.parser').select_one('input[name=version]')['value']
    assert c.post('/kalender-maandfocus/'+month,data={'version':fresh,'focus':''}).status_code==200
    assert 'Bestaande focus' not in c.get('/smartschool-calendar').text
    assert c.post('/kalender-maandfocus/'+month,data={'version':fresh,'focus':'Te veel\nregels'}).status_code==400
    assert c.get('/kalender-maandfocus/2026-13').status_code==400
    assert c.post('/kalender-maandfocus/'+month,data={'version':fresh,'focus':'Onveilig'},headers={'Origin':'https://unrelated.example'}).status_code==403
print('TCH_MONTH_FOCUS_SMOKE_TEST=PASS')
temp.cleanup()
