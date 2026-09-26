// Only the exact, previously reviewed import chunks are accepted. School data
// stays in the owner's download; this public manifest contains SHA-256 hashes.
import manifest from './import-manifest.json' with {type:'json'};

const chunkKey = (spec,index) => `browser:${spec.digest}:${index}`;
const sha256 = async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),b=>b.toString(16).padStart(2,'0')).join('');

export async function browserImport(DB, body, spec=manifest) {
  const complete=await DB.prepare('SELECT digest FROM import_batches WHERE digest=?').bind(spec.digest).first();
  if(body===undefined) return {complete:!!complete,total:spec.hashes.length};
  if(!body || !Number.isInteger(body.index) || body.index<0 || body.index>=spec.hashes.length || !Array.isArray(body.statements) || !body.statements.length || body.statements.length>35 || body.statements.some(s=>typeof s!=='string')) throw new Error('Ongeldige invoer: kies het originele kalenderbestand.');
  if(await sha256(JSON.stringify(body.statements))!==spec.hashes[body.index]) throw new Error('Ongeldige invoer: dit kalenderbestand is gewijzigd of hoort bij een andere versie.');
  if(complete) return {complete:true,total:spec.hashes.length};
  const marker=chunkKey(spec,body.index);
  if(await DB.prepare('SELECT digest FROM import_batches WHERE digest=?').bind(marker).first()) return {complete:false,total:spec.hashes.length,imported:body.index+1};
  if(body.index>0 && !await DB.prepare('SELECT digest FROM import_batches WHERE digest=?').bind(chunkKey(spec,body.index-1)).first()) throw new Error('Ongeldige invoer: begin het overzetten opnieuw met hetzelfde bestand.');
  // A chunk and its marker are one transaction. Every reviewed statement also
  // checks this marker, so simultaneous retries cannot create duplicate rows.
  await DB.batch([
    ...body.statements.map(sql=>DB.prepare(sql).bind()),
    DB.prepare('INSERT OR IGNORE INTO import_batches(digest,created_at) VALUES(?,?)').bind(marker,new Date().toISOString())
  ]);
  return {complete:body.index===spec.hashes.length-1,total:spec.hashes.length,imported:body.index+1};
}

export function renderImport() {
  return `<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kalender overzetten</title><style>@font-face{font-family:Roboto;src:url(/fonts/roboto-latin-400.woff2)}body{font:16px/1.6 Aptos,Roboto,Arial,sans-serif;background:#f5f6f8;color:#203555;margin:0}main{max-width:720px;margin:40px auto;padding:28px;background:white;border-radius:16px}input,button{font:inherit;padding:12px;box-sizing:border-box}input{width:100%;margin:8px 0 18px}button{background:#203555;color:white;border:0;border-radius:8px;cursor:pointer}button:disabled{opacity:.5}a{color:#203555}label{display:block}#status{white-space:pre-line}h1{font-size:1.5rem}@media(max-width:760px){main{margin:10px;padding:20px}}</style></head><body><main><h1>Je kalender overzetten</h1><p>Selecteer het gedownloade bestand <em>Kalender-start.html</em>. Hiermee worden de bestaande kalenderregels en verwijslinks één keer overgezet.</p><label for="key">Beheersleutel</label><input id="key" type="password" autocomplete="off"><label for="file">Kalenderbestand</label><input id="file" type="file" accept=".html,.json"><button id="start">Kalender overzetten</button><p id="status" role="status" aria-live="polite"></p><p><a href="/beheer">Kalender wijzigen en Smartschool-code bekijken</a></p></main><script>${importBootstrap.toString()};importBootstrap();</script></body></html>`;
}

function importBootstrap() {
  const $=id=>document.getElementById(id);
  const say=text=>{$('status').textContent=text;};
  let key=new URLSearchParams(location.hash.slice(1)).get('sleutel') || '';
  try{key=key || sessionStorage.getItem('calendarKey') || '';}catch{}
  if(location.hash) history.replaceState(null,'',location.pathname);
  $('key').value=key;
  $('start').onclick=async()=>{
    if($('start').disabled) return;
    const file=$('file').files?.[0];key=$('key').value.trim();
    if(!/^[A-Za-z0-9_-]{32,128}$/.test(key)) return say('Vul de beheersleutel uit je startbestand in.');
    if(!file || file.size>1000000) return say('Selecteer het originele startbestand (maximaal 1 MB).');
    $('start').disabled=true;$('key').disabled=true;$('file').disabled=true;
    try {
      const text=await file.text();
      const raw=text.trim().startsWith('{') ? text : new DOMParser().parseFromString(text,'text/html').getElementById('calendar-data')?.textContent;
      const data=JSON.parse(raw || 'null');
      if(data?.format!=='telescoop-calendar-import-v1' || !Array.isArray(data.chunks) || !data.chunks.length || data.chunks.length>100) throw new Error('Kies het originele kalenderbestand.');
      for(let i=0;i<data.chunks.length;i++) {
        if(data.chunks[i].index!==i) throw new Error('Het kalenderbestand is onvolledig.');
        say('Kalender overzetten: deel '+(i+1)+' van '+data.chunks.length+'…');
        const response=await fetch('/api/manage/import',{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},body:JSON.stringify(data.chunks[i]),signal:AbortSignal.timeout(15000)});
        const result=await response.json();
        if(!response.ok) throw new Error(result.error || 'Het overzetten is mislukt.');
        if(result.complete){try{sessionStorage.setItem('calendarKey',key);}catch{}say('Je kalender is volledig overgezet. Open hieronder Kalender wijzigen voor je beheerpagina en Smartschool-code.');return;}
      }
      throw new Error('De afronding is niet bevestigd.');
    }catch(error){say((error.name==='TimeoutError' || error.name==='TypeError' ? 'De verbinding is onderbroken.' : error.message)+' Je kunt hetzelfde bestand opnieuw overzetten; voltooide delen worden overgeslagen.');}
    finally{$('start').disabled=false;$('key').disabled=false;$('file').disabled=false;}
  };
}
