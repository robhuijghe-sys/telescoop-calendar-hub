import test from 'node:test';
import assert from 'node:assert/strict';
import {harness} from './support.mjs';
import {convert} from '../scripts/import-html.mjs';
import {parseHTML} from 'linkedom';

test('link API: beveiliging, validatie, wijzigen, verwijderen en publieke opmaak',async()=>{
  const {call,sqlite}=harness();
  const token='a'.repeat(64);
  assert.equal((await call('/api/manage/links','POST',{description:'x',url:'https://example.org'},'')).status,401);
  for(const url of ['javascript:alert(1)','data:text/html,foo','//evil.org','https://user:pass@example.org','https://exam\nple.org']) assert.equal((await call('/api/manage/links','POST',{description:'x',url})).status,400);
  const response=await call('/api/manage/links','POST',{description:'<script>test</script>',url:'/deeplink/1?a=1&b=2'});assert.equal(response.status,201);const link=await response.json();
  assert.match(link.url,/^https:\/\/telescoop-sgr8.smartschool.be/);
  let html=await (await call('/smartschool-calendar')).text();const {document}=parseHTML(html);
  const a=document.querySelector('.reference-links p:nth-child(2) a');assert.equal(a.getAttribute('href'),link.url);assert.match(a.textContent,/🔗/);assert.equal(a.querySelector('script'),null);
  assert.equal((await call('/api/manage/links/'+link.id,'PUT',{description:'Aangepast',url:'https://example.org'},token,{'If-Match':'1'})).status,200);
  html=await (await call('/smartschool-calendar')).text();assert.match(html,/Aangepast/);
  assert.equal((await call('/api/manage/links/'+link.id,'DELETE',undefined,token,{'If-Match':'2'})).status,200);
  assert.equal((await call('/api/manage/links/'+link.id,'DELETE',undefined,token,{'If-Match':'2'})).status,404);
  assert.equal((await call('/api/manage/links/'+link.id,'PUT',{description:'x',url:'https://example.org'},token,{'If-Match':'2'})).status,404);
  assert.equal((await (await call('/api/manage/links')).json()).links.length,0);
  assert.equal(sqlite.prepare("SELECT COUNT(*) AS n FROM audit_log WHERE action LIKE 'link.%'").get().n,3);
});

test('HTML import: aparte regels, stijl, relatieve links, jaargrens en herhalen na verwijdering',async()=>{
  const source=`<div class="telescoop-kalender-webfont"><div><p>Document <a href="/deeplink/123">🔗 openen</a></p><div><div>JANUARI</div><div style="border-bottom:1px solid">Focus</div><table><tr><td>ma 04/01</td><td><span style="color:#d32f2f" onclick="bad()">Eerste<br>Tweede</span><p><a href="javascript:alert(1)">Derde</a></p></td></tr></table></div></div></div>`;
  const result=convert(source,2026);assert.equal(result.items.length,3);assert.equal(result.items[0].date,'2027-01-04');assert.match(result.items[1].html,/color:#d32f2f/);assert.doesNotMatch(result.sql,/onclick|javascript:/);
  const {sqlite,call}=harness();sqlite.exec(result.sql);const item=sqlite.prepare('SELECT id FROM calendar_items LIMIT 1').get();
  await call('/api/manage/items/'+item.id,'DELETE');sqlite.exec(result.sql);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM calendar_items').get().n,3);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM calendar_items WHERE deleted_at IS NULL').get().n,2);
  assert.equal(sqlite.prepare('SELECT COUNT(*) AS n FROM calendar_links').get().n,1);
  const html=await (await call('/smartschool-calendar')).text();assert.match(html,/Focus/);assert.doesNotMatch(html,/Eerste/);assert.match(html,/Tweede/);
});
