import test from 'node:test';
import assert from 'node:assert/strict';
import {runInNewContext} from 'node:vm';
import {parseHTML} from 'linkedom';
import {renderManager} from '../src/pages.mjs';
import worker from '../src/worker.mjs';
import {harness} from './support.mjs';

test('beheerscherm: aanmaken, zoekopdracht, annuleren en bevestigen van verwijdering',async()=>{
  const {env,sqlite}=harness();
  const html=renderManager(),{document}=parseHTML(html), get=id=>document.getElementById(id);
  // Linkedom lacks browser scrolling and the select setter; these only provide native DOM behavior.
  get('search').scrollIntoView=()=>{};
  Object.defineProperty(get('category'),'value',{value:'algemeen',writable:true});
  let accept=false, offline=false;
  const context={document,URLSearchParams,location:{hash:'',pathname:'/beheer'},history:{replaceState(){}},sessionStorage:{getItem(){return null;},setItem(){}},confirm:()=>accept,
    fetch:(path,options)=>{if(offline)throw new Error('Verbinding verbroken.');return worker.fetch(new Request('https://example.workers.dev'+path,options),env);}};
  runInNewContext(html.match(/<script type="module">([\s\S]*?)<\/script>/)[1],context);
  get('key').value='a'.repeat(64);
  // The open handler starts an async task; wait until its expected DOM state has settled.
  get('useKey').onclick();
  for(let i=0;i<50 && get('app').hidden;i++) await new Promise(r=>setTimeout(r,2));
  assert.equal(get('app').hidden,false);
  get('prompt').value='Voeg op 1 december 2026 directie afwezig toe';
  await get('interpret').onclick();assert.equal(get('preview').hidden,false);
  await get('save').onclick();assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM calendar_items').get().n,1);
  get('prompt').value='Haal op 1 december 2026 directie afwezig weg';
  await get('interpret').onclick();
  let button=get('items').querySelector('button.danger');assert.ok(button,'verwijderzoekopdracht vindt het item');
  await button.onclick();assert.equal(sqlite.prepare('SELECT deleted_at FROM calendar_items').get().deleted_at,null);
  accept=true;await button.onclick();assert.ok(sqlite.prepare('SELECT deleted_at FROM calendar_items').get().deleted_at);
  assert.equal(get('items').querySelector('button.danger'),null);
  offline=true;get('prompt').value='Voeg morgen overleg toe';await get('interpret').onclick();
  assert.match(get('notice').textContent,/Verbinding verbroken/);assert.equal(get('interpret').disabled,false);
});

test('links beheren: toevoegen, aanpassen, annuleren, verwijderen en netwerkfout',async()=>{
  const {env,sqlite}=harness(),html=renderManager(),{document}=parseHTML(html),get=id=>document.getElementById(id);
  let accept=false,offline=false;
  runInNewContext(html.match(/<script type="module">([\s\S]*?)<\/script>/)[1],{document,URLSearchParams,location:{hash:'',pathname:'/beheer'},history:{replaceState(){}},sessionStorage:{getItem(){return null;},setItem(){}},confirm:()=>accept,fetch:(path,options)=>{if(offline)throw new Error('Offline');return worker.fetch(new Request('https://example.workers.dev'+path,options),env);}});
  get('key').value='a'.repeat(64);get('useKey').onclick();
  for(let i=0;i<50 && get('app').hidden;i++) await new Promise(r=>setTimeout(r,2));
  const submit=()=>get('linkForm').onsubmit({preventDefault(){}});
  get('linkDescription').value='Lesmateriaal';get('linkUrl').value='/deeplink/123';await submit();
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM calendar_links').get().n,1);
  get('links').querySelector('button').onclick();get('linkDescription').value='Nieuw';get('linkUrl').value='https://example.org/test';await submit();
  assert.equal(sqlite.prepare('SELECT description FROM calendar_links').get().description,'Nieuw');
  get('links').querySelector('button').onclick();get('linkCancel').onclick();assert.equal(get('linkDescription').value,'');
  await get('links').querySelector('.danger').onclick();assert.equal(sqlite.prepare('SELECT deleted_at FROM calendar_links').get().deleted_at,null);
  accept=true;await get('links').querySelector('.danger').onclick();assert.ok(sqlite.prepare('SELECT deleted_at FROM calendar_links').get().deleted_at);
  offline=true;get('linkDescription').value='Bewaard concept';get('linkUrl').value='https://example.org';await submit();
  assert.equal(get('linkDescription').value,'Bewaard concept');assert.match(get('notice').textContent,/Offline/);assert.equal(get('linkSave').disabled,false);
});
