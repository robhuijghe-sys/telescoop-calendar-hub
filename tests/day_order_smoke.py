import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.day_order import ordered_fragments, time_key
rows=['15u30: vergadering','09:00: uitstap','Lien AFW','vakgroep: 16u00','13:20–14:10: Eline vervangt Lien','08:45–09:35: geen turnen','Directie afwezig','VM: K3: lezen','hele dag: project','NM: museum','Zonder uur']
result=ordered_fragments(rows)
assert result[:5]==['Lien AFW','08:45–09:35: geen turnen','13:20–14:10: Eline vervangt Lien','Directie afwezig','hele dag: project']
assert result[5:]==['VM: K3: lezen','09:00: uitstap','NM: museum','vakgroep: 16u00','Zonder uur','15u30: vergadering']
rows=['Eline afwezig','9.35–10.00 LIST L6 → Christophe','8.45–9.10 LIST L5 → Milla','Lien afw','11u: Sofie vervangt Eline']
assert ordered_fragments(rows)==[rows[0],rows[2],rows[1],rows[4],rows[3]]
rich=['<a href="https://example.org">Uitstap</a>','<span style="color:red">Rudi afw</span>'];assert ordered_fragments(rich)==rich[::-1]
assert time_key('12.40-13.20u spel')==760
assert time_key('K3 uitstap 2026')==1440
assert ordered_fragments(['A','B'])==['A','B']
print('TCH_DAY_ORDER_SMOKE_TEST=PASS')

rows=['teamvergadering: 15u45 tot 17u00','* actuakring: wat werkt?', 'Stage Fatima van 8u00 tot 12u00','09u: uitstap','Milla afw','10u: Rob vervangt Milla','Zonder uur']
assert ordered_fragments(rows)==[rows[4],rows[5],rows[3],rows[6],rows[2],rows[0],rows[1]]
assert sorted(ordered_fragments(rows))==sorted(rows)
print('STAGES_MEETINGS_QC=PASS')

from bs4 import BeautifulSoup
from app.day_order import is_replacement
rows=['digitale wolven','3de en 4de lesuur: <b>GR3 + K3</b>','5de en 6de lesuur: <b>L1 + L2</b>','GR2 niet op school: GWP Bosklassen - Sint Joris Weert','WIS K3 in L1, 3de lesuur','Stage Fatima','teamvergadering','* agenda']
result=ordered_fragments(rows)
group=BeautifulSoup(result[0], 'html.parser')
assert group.select_one('.activity-group')
assert ' '.join(group.get_text(' ',strip=True).split())=='digitale wolven: 3de en 4de lesuur: GR3 + K3 5de en 6de lesuur: L1 + L2'
assert len(group.select('b'))==2
assert rows[3] in result and rows[4] in result
assert result[-3:]==rows[-3:]
assert time_key('3de en 4de lesuur: GR3 + K3')==580
assert is_replacement('Marinela vervangt Milla (GWP GR2)')
assert not is_replacement('Milla afwezig: GWP GR2')
print('WORKSHOP_GROUPS_QC=PASS')
