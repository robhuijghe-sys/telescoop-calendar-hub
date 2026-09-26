import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../src/worker.mjs';
import {parseInstruction} from '../src/parser.mjs';
import {renderCalendar, REFRESH_SECONDS, filterItems} from '../src/pages.mjs';

const TOKEN='a'.repeat(64);
import {harness} from './support.mjs';

test('30 minuten en Nederlandse datum, uur en kleur',()=>{
  assert.equal(REFRESH_SECONDS,1800);
  const p=parseInstruction('Voeg op 6 oktober om 15.30 teamvergadering toe',new Date('2026-09-26T09:00:00Z'));
  assert.deepEqual([p.title,p.date,p.start_time,p.category],['Teamvergadering','2026-10-06','15:30','personeel']);
  assert.equal(parseInstruction('Uitstap op 31 februari',new Date('2026-09-26T09:00:00Z')).date,'');
});

test('toevoegen, Smartschool-weergave, bevestigd verwijderen en audit',async()=>{
  const {call,sqlite}=harness();
  const item={title:'Teamvergadering',date_local:'2026-10-06',start_time:'15:30',end_time:'',category:'personeel',description:'In de leraarskamer'};
  assert.equal((await call('/api/manage/items','POST',item,'wrong-token')).status,401);
  const created=await call('/api/manage/items','POST',item);
  assert.equal(created.status,201);
  const {id}=await created.json();
  assert.equal((await call('/api/manage/items','POST',item)).status,409);
  let page=await (await call('/smartschool-calendar','GET',undefined,null)).text();
  assert.match(page,/http-equiv="refresh" content="1800"/);
  assert.match(page,/Teamvergadering/);
  assert.match(page,/15:30/);
  assert.match(page,/leraarskamer/);
  assert.equal((await call(`/api/manage/items/${id}`,'DELETE',undefined,'wrong-token')).status,401);
  assert.equal((await call(`/api/manage/items/${id}`,'DELETE')).status,200);
  assert.equal((await call(`/api/manage/items/${id}`,'DELETE')).status,404);
  page=await (await call('/smartschool-calendar','GET',undefined,null)).text();
  assert.doesNotMatch(page,/Teamvergadering/);
  assert.deepEqual(sqlite.prepare('SELECT action FROM audit_log ORDER BY id').all().map(x=>x.action),['item.created','item.deleted']);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM calendar_items WHERE deleted_at IS NOT NULL').get().n,1);
});

test('oude geïmporteerde kalenderregels zijn afzonderlijk te verwijderen',async()=>{
  const {call,sqlite}=harness();
  sqlite.prepare("INSERT INTO calendar_items(date_local,title,source,created_at) VALUES(?,?,?,?)")
    .run('2026-12-01','Directie afwezig','legacy','2026-09-26T00:00:00Z');
  assert.equal((await call('/api/manage/items')).status,200);
  assert.equal((await call('/api/manage/items/1','DELETE')).status,200);
  assert.equal(sqlite.prepare('SELECT deleted_at FROM calendar_items WHERE id=1').get().deleted_at!==null,true);
});

test('invoer wordt gevalideerd en kalendertekst wordt ontsmet',async()=>{
  const {call}=harness();
  assert.equal((await call('/api/manage/items','POST',{title:'x',date_local:'2026-02-31'})).status,400);
  assert.equal((await call('/api/manage/items','POST',{title:'x',date_local:'2026-10-01',start_time:'16:00',end_time:'15:00'})).status,400);
  const page=renderCalendar([{date_local:'2026-10-01',title:'<script>alert(1)</script>',description:'',category:'algemeen',start_time:'',end_time:''}]);
  assert.doesNotMatch(page,/<script>alert/);
  assert.match(page,/&lt;script&gt;/);
});

test('titels blijven intact, ongeldige uren zijn zichtbaar en verwijdering kiest geen volgend jaar',()=>{
  const now=new Date('2026-09-26T09:00:00Z');
  assert.equal(parseInstruction('Voeg De Klas van Morgen op 6 oktober toe',now).title,'De Klas van Morgen');
  assert.equal(parseInstruction('Voeg De Klas van Morgen toe',now).date,'');
  assert.equal(parseInstruction('Haal op 1 september directie afwezig weg',now).date,'2026-09-01');
  assert.equal(parseInstruction('Haal op 1 december directie afwezig weg',now).title,'Directie afwezig');
  const invalid=parseInstruction('Voeg op 6 oktober om 15.99 overleg toe',now);
  assert.equal(invalid.start_time,'');assert.ok(invalid.missing.includes('geldige tijd'));
  assert.equal(parseInstruction('Voeg morgen om 8u30 overleg toe',now).start_time,'08:30');
  assert.equal(parseInstruction('Voeg op 2026-10-06 overleg toe',now).date,'2026-10-06');
});

test('verwijderzoekopdracht combineert datum en losse zoekwoorden',()=>{
  const items=[{date_local:'2026-12-01',title:'Directie afwezig',description:''},{date_local:'2026-12-02',title:'Directie afwezig',description:''}];
  assert.equal(filterItems(items,'2026-12-01 Afwezigheid directie').length,1);
  assert.equal(filterItems(items,'01/12 directie').length,1);
  assert.equal(filterItems(items,'1/12 directie').length,1);
});

test('meer dan 2000 items blijven bereikbaar en zichtbaar',async()=>{
  const {call,sqlite}=harness();
  const insert=sqlite.prepare("INSERT INTO calendar_items(date_local,title,source,created_at) VALUES(?,?,?,?)");
  sqlite.exec('BEGIN');
  for(let i=0;i<2005;i++) insert.run('2026-12-01','Item '+i,'legacy','now');
  sqlite.exec('COMMIT');
  const ids=[];let cursor=0;
  do {const result=await (await call('/api/manage/items?after='+cursor)).json();ids.push(...result.items.map(x=>x.id));cursor=result.next_cursor;} while(cursor!==null);
  assert.equal(ids.length,2005);assert.equal(new Set(ids).size,2005);
  const page=await (await call('/smartschool-calendar')).text();assert.match(page,/Item 2004/);
});

test('gezondheidscontrole en strengere invoer- en sleutelcontrole',async()=>{
  const {call,sqlite,env}=harness();
  assert.equal((await call('/api/manage/items','GET',undefined,'b'.repeat(64))).status,401);
  for(const extra of [{category:'constructor'},{category:'__proto__'},{title:{value:'Test'}}]) {
    assert.equal((await call('/api/manage/items','POST',{title:'Test',date_local:'2026-10-01',...extra})).status,400);
  }
  const oversized=new Request('https://example.workers.dev/api/manage/interpret',{method:'POST',headers:{Authorization:'Bearer '+TOKEN},body:JSON.stringify({text:'漢'.repeat(6000)})});
  assert.equal((await worker.fetch(oversized,env)).status,400);
  assert.equal((await call('/health')).status,200);
  const calendar=await call('/smartschool-calendar');
  assert.doesNotMatch(calendar.headers.get('Content-Security-Policy'),/frame-ancestors/);
  sqlite.exec('DROP TABLE calendar_items');
  assert.equal((await call('/health')).status,503);
});
