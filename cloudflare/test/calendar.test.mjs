import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {DatabaseSync} from 'node:sqlite';
import worker from '../src/worker.mjs';
import {parseInstruction} from '../src/parser.mjs';
import {renderCalendar, REFRESH_SECONDS} from '../src/pages.mjs';

const TOKEN='a'.repeat(64);
function harness() {
  const sqlite=new DatabaseSync(':memory:');
  sqlite.exec(readFileSync(new URL('../schema.sql',import.meta.url),'utf8'));
  const DB={prepare(sql){return {bind(...args){const statement=sqlite.prepare(sql);return {
    async all(){return {results:statement.all(...args)};},
    async first(){return statement.get(...args) || null;},
    async run(){const result=statement.run(...args);return {meta:{changes:Number(result.changes)}};}
  };}}}};
  const env={DB,EDITOR_TOKEN_SHA256:createHash('sha256').update(TOKEN).digest('hex')};
  async function call(path,method='GET',body,token=TOKEN){
    const headers=token ? {Authorization:`Bearer ${token}`} : {};
    if(body) headers['Content-Type']='application/json';
    return worker.fetch(new Request('https://example.workers.dev'+path,{method,headers,body:body?JSON.stringify(body):undefined}),env);
  }
  return {call,sqlite};
}

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
