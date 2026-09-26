import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync,existsSync} from 'node:fs';
import {runInNewContext} from 'node:vm';
import {parseHTML,DOMParser} from 'linkedom';
import {buildBrowserPackage,startPage,DEPLOY_URL} from '../scripts/browser-package.mjs';
import {browserImport,renderImport} from '../src/browser-import.mjs';
import {harness} from './support.mjs';

const digest='b'.repeat(64),token='a'.repeat(64),guard=' WHERE NOT EXISTS(SELECT 1 FROM import_batches);';
function fixture(){return buildBrowserPackage([
  ...Array.from({length:37},(_,i)=>`INSERT INTO calendar_items(date_local,title,source,created_at) SELECT '2026-10-01','Regel ${i}; tekst ''met quotes''','legacy','now'`+guard),
  `INSERT INTO calendar_links(description,url,updated_at) SELECT 'Info','https://example.org','now'`+guard,
  `INSERT INTO import_batches(digest,created_at) SELECT '${digest}','now'`+guard
].join('\n'));}

test('browserimport: gecontroleerde SQL, volgorde, hervatten en geen dubbele of herstelde regels',async()=>{
  const {env,sqlite}=harness(),{manifest,data}=fixture();assert.equal(data.chunks.length,2);
  await assert.rejects(()=>browserImport(env.DB,data.chunks[1],manifest),/begin het overzetten opnieuw/);
  const altered=structuredClone(data.chunks[0]);altered.statements[0]='DROP TABLE calendar_items;';
  await assert.rejects(()=>browserImport(env.DB,altered,manifest),/gewijzigd/);
  await browserImport(env.DB,data.chunks[0],manifest);
  sqlite.exec("UPDATE calendar_items SET deleted_at='now' WHERE id=1");
  await browserImport(env.DB,data.chunks[0],manifest);
  assert.equal(sqlite.prepare('SELECT count(*) AS n FROM calendar_items').get().n,35);
  assert.equal((await browserImport(env.DB,data.chunks[1],manifest)).complete,true);
  for(const chunk of data.chunks) assert.equal((await browserImport(env.DB,chunk,manifest)).complete,true);
  assert.equal(sqlite.prepare('SELECT count(*) AS n FROM calendar_items').get().n,37);
  assert.equal(sqlite.prepare('SELECT count(*) AS n FROM calendar_links').get().n,1);
  assert.equal(sqlite.prepare('SELECT deleted_at FROM calendar_items WHERE id=1').get().deleted_at,'now');
});

test('browserpublicatie: directe geheime sleutel en weigeren van ongeldige import',async()=>{
  const {call,env}=harness();delete env.EDITOR_TOKEN_SHA256;env.EDITOR_TOKEN=token;
  assert.equal((await call('/api/manage/import')).status,200);
  assert.equal((await call('/api/manage/import','GET',undefined,'b'.repeat(64))).status,401);
  assert.equal((await call('/api/manage/import','POST',{index:0,statements:['DROP TABLE calendar_items;']})).status,400);
  env.EDITOR_TOKEN='short';assert.equal((await call('/api/manage/items')).status,401);
  const html=await (await call('/overzetten')).text();assert.match(html,/Kalender-start.html/);assert.doesNotMatch(html,new RegExp(token));
});

test('startbestand: geldige publicatielink, alleen Cloudflare-adressen en privégegevens niet uitvoeren',()=>{
  const {data}=fixture(),html=startPage(data,token),{document}=parseHTML(html);
  const source=new URL(DEPLOY_URL).searchParams.get('url');assert.match(source,/\/tree\/calendar-browser\/cloudflare$/);
  assert.deepEqual(JSON.parse(document.getElementById('calendar-data').textContent),data);
  assert.equal(document.querySelectorAll('script').length,2);
  runInNewContext(document.querySelectorAll('script')[1].textContent,{document,URL,navigator:{}});
  const input=document.getElementById('origin'),links=document.getElementById('links');
  for(const bad of ['https://evil.example','https://test.account.workers.dev.evil.example','https://user:pass@test.account.workers.dev','http://test.account.workers.dev']){input.value=bad;document.getElementById('prepare').onclick();assert.equal(links.hidden,true);}
  input.value='https://test.account.workers.dev/';document.getElementById('prepare').onclick();
  assert.equal(links.hidden,false);assert.equal(document.getElementById('import').getAttribute('href'),'https://test.account.workers.dev/overzetten#sleutel='+token);
});

test('importpagina leest hetzelfde HTML-startbestand, herstelt verbinding en voltooit',async()=>{
  const {data,manifest}=fixture(),{env,sqlite}=harness();
  const html=renderImport(),{document}=parseHTML(html),get=id=>document.getElementById(id);
  let fail=true,saved='';const file=startPage(data,token);
  Object.defineProperty(get('file'),'files',{value:[{size:Buffer.byteLength(file),text:async()=>file}]});
  runInNewContext(document.querySelector('script').textContent,{document,DOMParser,URLSearchParams,AbortSignal,
    location:{hash:'#sleutel='+token,pathname:'/overzetten'},history:{replaceState(){}},sessionStorage:{getItem(){return null;},setItem(k,v){saved=v;}},
    fetch:async(path,options)=>{const body=JSON.parse(options.body);if(body.index===1 && fail)throw new TypeError('Offline');return Response.json(await browserImport(env.DB,body,manifest));}});
  await get('start').onclick();assert.match(get('status').textContent,/verbinding is onderbroken/);assert.equal(get('start').disabled,false);
  fail=false;await get('start').onclick();assert.match(get('status').textContent,/volledig overgezet/);assert.equal(saved,token);
  assert.equal(sqlite.prepare('SELECT count(*) AS n FROM calendar_items').get().n,37);
});

const privateSource=new URL('../private-import/import.sql',import.meta.url);
test('aangeleverde kalender: alle 401 regels, 7 links en 152 datums exact overgezet',{skip:!existsSync(privateSource)},async()=>{
  const {manifest,data}=buildBrowserPackage(readFileSync(privateSource,'utf8'));
  assert.deepEqual(manifest,JSON.parse(readFileSync(new URL('../src/import-manifest.json',import.meta.url))));
  const direct=harness(),browser=harness();direct.sqlite.exec(readFileSync(privateSource,'utf8'));
  for(const chunk of data.chunks){assert.ok(Buffer.byteLength(JSON.stringify(chunk))<=16384);assert.ok(chunk.statements.length<=35);await browserImport(browser.env.DB,chunk);}
  for(const table of ['calendar_items','calendar_links','calendar_settings'])assert.deepEqual(browser.sqlite.prepare('SELECT * FROM '+table).all(),direct.sqlite.prepare('SELECT * FROM '+table).all());
  assert.equal(browser.sqlite.prepare('SELECT count(*) AS n FROM calendar_items').get().n,401);
  assert.equal(browser.sqlite.prepare('SELECT count(*) AS n FROM calendar_links').get().n,7);
  assert.equal(JSON.parse(browser.sqlite.prepare("SELECT value FROM calendar_settings WHERE key='layout'").get().value).dates.length,152);
});
