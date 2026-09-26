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
