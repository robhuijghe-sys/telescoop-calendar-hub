import test from 'node:test';
import assert from 'node:assert/strict';
import {harness} from './support.mjs';
import {serveCalendar} from '../src/read-calendar.mjs';
import {html} from '../src/worker.mjs';
import {parseInstruction} from '../src/parser.mjs';
import {convert} from '../scripts/import-html.mjs';
import {parseHTML} from 'linkedom';

test('publieke cache leest alleen revisie bij herhaling en wordt direct ongeldig na elke wijziging',async()=>{
  const {env,call,queries,sqlite}=harness(),stored=new Map(),pending=[];
  const cache={async match(key){return stored.get(key.url)?.clone();},async put(key,response){stored.set(key.url,response);}};
  const ctx={waitUntil(p){pending.push(p);}};
  const get=async(headers={},method='GET')=>{const result=await serveCalendar(new Request('https://example.workers.dev/smartschool-calendar',{headers,method}),env,ctx,html,cache);await Promise.all(pending.splice(0));return result;};
  let response=await get(),etag=response.headers.get('ETag');assert.equal(response.headers.get('X-Calendar-Cache'),'MISS');await response.text();
  queries.length=0;response=await get();assert.equal(response.headers.get('X-Calendar-Cache'),'HIT');assert.equal(queries.length,1);assert.equal(queries[0].rows,1);await response.text();
  response=await get({'If-None-Match':'W/'+etag});assert.equal(response.status,304);assert.equal(await response.text(),'');
  const {id}=await (await call('/api/manage/links','POST',{description:'Nieuwe link',url:'https://example.org'})).json();
  response=await get({'If-None-Match':etag});assert.equal(response.status,200);assert.notEqual(response.headers.get('ETag'),etag);assert.match(await response.text(),/Nieuwe link/);
  await call('/api/manage/links/'+id,'PUT',{description:'Aangepast',url:'https://example.com'},'a'.repeat(64),{'If-Match':'1'});
  response=await get();assert.match(await response.text(),/Aangepast/);
  await call('/api/manage/links/'+id,'DELETE',undefined,'a'.repeat(64),{'If-Match':'2'});
  response=await get();assert.doesNotMatch(await response.text(),/Aangepast/);
  await call('/api/manage/items','POST',{title:'Teamoverleg',date_local:'2026-10-01'});
  response=await get();assert.match(await response.text(),/Teamoverleg/);
  await call('/api/manage/items/1','DELETE');response=await get();assert.doesNotMatch(await response.text(),/Teamoverleg/);
  sqlite.prepare("INSERT INTO calendar_settings VALUES('layout',?)").run(JSON.stringify({dates:['2026-10-01'],focus:{'2026-10':'Spelling'}}));
  response=await get();etag=response.headers.get('ETag');assert.match(await response.text(),/Spelling/);
  env.WORKER_VERSION={id:'new-code'};response=await get();assert.notEqual(response.headers.get('ETag'),etag);await response.text();
  response=await get({},'HEAD');assert.equal(await response.text(),'');assert.match(response.headers.get('Cache-Control'),/no-cache/);
});

test('cachefout blokkeert de kalender niet, health detecteert ontbrekende linktabel',async()=>{
  const {env,call,sqlite}=harness(),pending=[];
  const response=await serveCalendar(new Request('https://example.workers.dev/smartschool-calendar'),env,{waitUntil(p){pending.push(p);}},html,{match(){throw Error('cache down');},async put(){throw Error('cache down');}});
  await Promise.all(pending);assert.equal(response.status,200);assert.match(await response.text(),/Kalender wijzigen/);
  sqlite.exec('DROP TABLE calendar_links');assert.equal((await call('/health')).status,503);
});

test('linkwijzigingen uit twee beheerschermen overschrijven elkaar niet en dubbel toevoegen wordt geweigerd',async()=>{
  const {call}=harness(),token='a'.repeat(64),body={description:'Test',url:'https://example.org'};
  const first=await (await call('/api/manage/links','POST',body)).json();
  assert.equal((await call('/api/manage/links','POST',body)).status,409);
  const path='/api/manage/links/'+first.id;
  assert.equal((await call(path,'PUT',{...body,description:'Eerste wijziging'},token,{'If-Match':String(first.version)})).status,200);
  assert.equal((await call(path,'PUT',{...body,description:'Tweede wijziging'},token,{'If-Match':String(first.version)})).status,409);
  assert.equal((await call(path,'DELETE',undefined,token,{'If-Match':String(first.version)})).status,409);
  assert.equal((await (await call('/api/manage/links')).json()).links[0].description,'Eerste wijziging');
});

test('Nederlandse uren en verwijderopdrachten met leestekens blijven correct',()=>{
  const now=new Date('2026-09-26T10:00:00Z');
  for(const notation of ['15.30u','15:30','15u30']) {const item=parseInstruction('Voeg overleg op 6 oktober om '+notation+' toe',now);assert.equal(item.start_time,'15:30');assert.equal(item.title,'Overleg');}
  const range=parseInstruction('Voeg op 6 oktober van 9 tot 10 uur overleg toe',now);assert.equal(range.start_time,'09:00');assert.equal(range.end_time,'10:00');assert.equal(range.title,'Overleg');
  const colonRange=parseInstruction('Voeg op 6 oktober 09:00-10 uur overleg toe',now);assert.equal(colonRange.start_time,'09:00');assert.equal(colonRange.end_time,'10:00');
  assert.equal(parseInstruction('Voeg De Klas van Morgen morgen toe',now).title,'De Klas van Morgen');
  const deletion=parseInstruction('Haal overleg morgen weg.',now);assert.equal(deletion.action,'delete');assert.equal(deletion.date,'2026-09-27');assert.equal(deletion.title,'Overleg');
  assert.equal(parseInstruction('Voeg De Klas van Morgen toe',now).date,'');
});

test('import bewaart overgeërfde celkleur en publieke beheerlink bevat nooit een beheersleutel',async()=>{
  const source='<div class="telescoop-kalender-webfont"><div><div><table><tr><td>ma 04/01</td><td style="color:#c614a1;font-weight:bold">Regel één<br>Regel twee</td></tr></table></div></div></div>';
  const imported=convert(source,2026);assert.equal(imported.items.length,2);for(const item of imported.items)assert.match(item.html,/color:#c614a1/);
  const {sqlite,call}=harness();sqlite.exec(imported.sql);
  const {document}=parseHTML(await (await call('/smartschool-calendar')).text());
  const link=document.querySelector('.reference-links a');assert.equal(link.textContent.trim(),'🔗 Kalender wijzigen');assert.equal(link.getAttribute('href'),'/beheer');assert.doesNotMatch(link.outerHTML,/sleutel=|[a-f0-9]{64}/);
});


test('Smartschool-code verwijst naar dezelfde host en bevat geen beheersleutel',async()=>{
  const {call}=harness();
  const {document}=parseHTML(await (await call('/beheer')).text());
  // Linkedom leaves textarea character references encoded; browsers decode this RCDATA.
  const code=parseHTML('<div>'+document.querySelector('#embedCode').textContent+'</div>').document.firstElementChild.textContent;
  assert.match(code,/src="https:\/\/example.workers.dev\/smartschool-calendar"/);
  assert.match(code,/title="Schoolkalender De Telescoop"/);
  assert.doesNotMatch(code,/sleutel=|Bearer/);
});
