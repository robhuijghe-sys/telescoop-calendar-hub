"""Exercise uniform labels, stage exclusion, storage and repeated checks."""
import os
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
temp = tempfile.TemporaryDirectory()
os.environ.update(DB_PATH=temp.name+'/calendar.db',CALENDAR_SNAPSHOT_PATH=temp.name+'/snapshot.json',APP_SECRET='test-only',ADMIN_RESET_PASSWORD='',ENABLE_ADMIN_RECOVERY_LOG='false',CALENDAR_SOURCE_GZ_B64='',CALENDAR_LINKS_GZ_B64='',CALENDAR_SNAPSHOT_GZ_B64='')
from app.display_format import normalize_text, normalize_html
from app.simple_calendar import app
import app.main as core
from fastapi.testclient import TestClient
from bs4 import BeautifulSoup

cases = {
 '11:11 tot 11:12: L5: CLB (op school)': '11u11 - 11u12: L5 - CLB (op school)',
 '6de lesuur: L5: CLB (op school)': '6de lesuur: L5 - CLB (op school)',
 'L6: CLB Bezoek (9uur)': '9u00: L6 - CLB Bezoek',
 '08.45 - 10.25 - K3 - Panda': '8u45 - 10u25: K3 - Panda',
 'vakgroep NED: 15u38 tot 16u45': '15u38 - 16u45: vakgroep NED',
 'WIS K3 in L1, 3de lesuur': '3de lesuur: K3 - WIS in L1',
 'GR2 niet op school: GWP': 'GR2 - niet op school: GWP',
 '🧊 IJskast leegmaken tegen 13u20': '🧊 IJskast leegmaken tegen 13u20',
 'Stage Noor van 8u30 tot 12u40 (+ refter)': 'Stage Noor van 8u30 tot 12u40 (+ refter)',
}
for before, after in cases.items():
 assert normalize_text(before)==after, (before,normalize_text(before))
 assert normalize_text(after)==after
assert '1,5 uur' in normalize_text('Mechanische schakelingen: L4 — 1,5 uur.')
assert '2 uur in totaal' in normalize_text('Koloniekwekers: L5 en L6 — 2 uur in totaal.')
rich = '<span style="color:#912345">11:23: L5: <a href="https://example.org">CLB</a> (op school)</span>'
n = normalize_html(rich)
assert BeautifulSoup(n,'html.parser').get_text()=='11u23: L5 - CLB (op school)'
assert '#912345' in n and BeautifulSoup(n,'html.parser').find('a')['href']=='https://example.org'
assert normalize_html(n)==n
stage = '<span style="color:blue">Stage Tasnim K0K1 + refter – toezicht 10u40 - 10u55</span>'
assert normalize_html(stage)==stage
assert 'GR3 + K3 - Digitale wolven' in BeautifulSoup(normalize_html('digitale wolven:<br>1ste en 2de lesuur: GR3 + K3'),'html.parser').get_text()

with TestClient(app) as client:
 con=core.db()
 for value in (rich,stage):
  con.execute('INSERT INTO editor_lines(date_local,body_html,title) VALUES(?,?,?)',('2026-10-12',value,BeautifulSoup(value,'html.parser').get_text()))
 con.commit()
 before=dict(con.execute('SELECT * FROM editor_lines WHERE id=2').fetchone())
 con.close()
 report=client.post('/kalender-opmaak-controleren').json()
 assert report['checked']==2 and report['changed']==1 and report['stages_skipped']==1,report
 assert client.post('/kalender-opmaak-controleren').json()['changed']==0
 con=core.db()
 assert dict(con.execute('SELECT * FROM editor_lines WHERE id=2').fetchone())==before
 assert con.execute('SELECT title FROM editor_lines WHERE id=1').fetchone()[0]=='11u23: L5 - CLB (op school)'
 con.close()
 assert client.get('/health').json()['format_check']['changed']==0
 # All editors use the same normalizer; retrying an addition is idempotent.
 for _ in range(2):
  assert client.post('/kalender-toevoegen',data={'date':'2026-10-12','structured':'1','lines':'6de lesuur: L5 - CLB (op school)'},follow_redirects=False).status_code==303
 con=core.db()
 assert con.execute('SELECT COUNT(*) FROM editor_lines WHERE deleted=0').fetchone()[0]==3
 con.close()
print('TCH_DISPLAY_FORMAT_SMOKE_TEST=PASS')
