"""Meetings stay below activities, with their own agenda and substitutions."""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bs4 import BeautifulSoup
from app.day_order import ordered_fragments, is_meeting, meeting_time_key

rows = [
    '<b>Vakgroep NED: 3de en 4de lesuur</b>',
    '<span style="color:red;font-weight:bold">Vakgroep WO: 1ste en 2de lesuur</span>',
    'Wissel L2: WO naar het 5de lesuur, MUVO naar het 2de lesuur.',
    'Sofie vervangt Wout voor vakgroep NED',
    'Stage Imane van 8u30 tot 12u40',
    'Sinterklaas op bezoek',
    'Lien afwezig',
    '09u: Veronica vervangt Lien',
    '18 uur: oudervergadering',
    'oudervereniging: 16u30',
    'Teamvergadering: 15u45',
]
result = ordered_fragments(rows)
assert result == [rows[i] for i in [6, 7, 5, 4, 1, 2, 0, 3, 10, 9, 8]]
assert sorted(result) == sorted(rows)
assert not is_meeting('Directie afwezig: overleg scholengroep')
assert not is_meeting('Sofie vervangt Wout voor vakgroep NED')
assert is_meeting('18 uur: oudervergadering')
assert is_meeting('klassenraden')
assert meeting_time_key('Vakgroep WO: 1ste en 2de lesuur; vervanging 9u30') == 525
assert meeting_time_key('8u30: overleg') < meeting_time_key('Vakgroep WO: 1ste lesuur')
agenda = ['Vakgroep NED: 15u30', 'zorgoverleg', 'L6: CLB bezoek', '* EDI spelling']
assert ordered_fragments(agenda) == [agenda[i] for i in [2, 0, 3, 1]]
groups = BeautifulSoup(''.join(ordered_fragments(rows, style_meetings=True)), 'html.parser')
assert len(groups.select('.meeting-group')) == 5
assert 'Wissel L2' in groups.select('.meeting-group')[0].get_text()
assert 'Sofie vervangt' in groups.select('.meeting-group')[1].get_text()

with tempfile.TemporaryDirectory() as temp:
    os.environ.update(DB_PATH=temp + '/calendar.db', CALENDAR_SNAPSHOT_PATH=temp + '/snapshot.json',
                      APP_SECRET='test-only', ADMIN_RESET_PASSWORD='', ENABLE_ADMIN_RECOVERY_LOG='false',
                      CALENDAR_SOURCE_GZ_B64='', CALENDAR_LINKS_GZ_B64='', CALENDAR_SNAPSHOT_GZ_B64='')
    Path(os.environ['CALENDAR_SNAPSHOT_PATH']).write_text(json.dumps({'focus': {}, 'entries': []}))
    from fastapi.testclient import TestClient
    from app.simple_calendar import app
    import app.main as core
    with TestClient(app) as client:
        day = (datetime.now(core.TZ).date() + timedelta(days=1)).isoformat()
        con = core.db()
        for row in rows:
            con.execute('INSERT INTO editor_lines(date_local,body_html,title,custom_format) VALUES(?,?,?,1)',
                        (day, row, BeautifulSoup(row, 'html.parser').get_text()))
        con.commit()
        before = [tuple(row) for row in con.execute('SELECT * FROM editor_lines')]
        response = client.get('/smartschool-calendar')
        assert response.status_code == 200
        assert '.meeting-group,.meeting-group *{color:#8e44ad!important;font-weight:400!important}' in response.text
        soup = BeautifulSoup(response.text, 'html.parser')
        for selector in ('.desktop-calendar .event-cell', '.mobile-calendar .mobile-events'):
            body = soup.select_one(selector)
            meetings = body.select('.meeting-group')
            assert len(meetings) == 5
            assert meetings[0].get_text().startswith('Vakgroep WO')
            assert 'Wissel L2' in meetings[0].get_text()
            assert meetings[1].get_text().startswith('Vakgroep NED')
            assert 'Sofie vervangt' in meetings[1].get_text()
            assert 'oudervergadering' in body.find_all(recursive=False)[-1].get_text()
            assert not any(m.find_parent(class_='replacement-line') for m in meetings)
            for row in rows:
                assert body.get_text().count(BeautifulSoup(row, 'html.parser').get_text()) == 1
        assert [tuple(row) for row in con.execute('SELECT * FROM editor_lines')] == before
        con.close()
print('OK: purple regular meetings last, chronological, linked replacements, both views, data preserved')
