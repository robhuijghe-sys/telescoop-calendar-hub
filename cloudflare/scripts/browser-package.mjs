import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash,randomBytes} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {resolve} from 'node:path';

export const DEPLOY_URL='https://deploy.workers.cloudflare.com/?url='+encodeURIComponent('https://github.com/robhuijghe-sys/telescoop-calendar-hub/tree/calendar-browser/cloudflare');
export function buildBrowserPackage(sql) {
  // SQL export has no comments or triggers. Quoted strings can contain literal
  // semicolons and newlines, so splitting by lines or semicolons is unsafe.
  const statements=[];let start=0,quote='';
  for(let i=0;i<sql.length;i++) {
    const char=sql[i];
    if(quote){if(char===quote){if(sql[i+1]===quote)i++;else quote='';}}
    else if(char==="'" || char==='"') quote=char;
    else if(char===';'){statements.push(sql.slice(start,i+1).trim());start=i+1;}
  }
  if(quote || sql.slice(start).trim()) throw new Error('Onvolledige SQL-export.');
  const digest=statements.at(-1)?.match(/^INSERT INTO import_batches\(digest,created_at\) SELECT '([a-f0-9]{64})'/)?.[1];
  if(!digest) throw new Error('Geen geldige importidentiteit.');
  const guard='WHERE NOT EXISTS(SELECT 1 FROM import_batches)';
  const chunks=[];let current=[];
  for(const statement of statements) {
    if(!/^INSERT INTO (calendar_items|calendar_links|calendar_settings|import_batches)\(/.test(statement) || !statement.endsWith(guard+';')) throw new Error('Onverwachte SQL-export; controleer het bronbestand.');
    let index=chunks.length;
    const transform=i=>statement.slice(0,-guard.length-1)+`WHERE NOT EXISTS(SELECT 1 FROM import_batches WHERE digest='browser:${digest}:${i}');`;
    let next=transform(index);
    if(current.length && (current.length>=35 || Buffer.byteLength(JSON.stringify({index,statements:[...current,next]}))>14000)) {chunks.push({index,statements:current});current=[];index++;next=transform(index);}
    current.push(next);
    if(Buffer.byteLength(JSON.stringify({index,statements:current}))>14000) throw new Error('Een importregel is te groot.');
  }
  if(current.length) chunks.push({index:chunks.length,statements:current});
  const manifest={digest,hashes:chunks.map(chunk=>createHash('sha256').update(JSON.stringify(chunk.statements)).digest('hex'))};
  return {manifest,data:{format:'telescoop-calendar-import-v1',chunks}};
}

export function startPage(data,key) {
  if(!/^[a-f0-9]{64}$/.test(key)) throw new Error('Ongeldige beheersleutel.');
  return `<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>De Telescoop · Kalender starten</title><style>body{font:17px/1.6 Aptos,Roboto,"Segoe UI",Arial,sans-serif;background:#f3f6fa;color:#203555;margin:0}main{max-width:800px;margin:30px auto;padding:28px}section{background:#fff;border:1px solid #dce3ee;border-radius:16px;padding:24px;margin:20px 0}h1{font-size:1.8rem}h2{font-size:1.25rem}input{box-sizing:border-box;width:100%;font:inherit;padding:12px;border:1px solid #9aabc2;border-radius:7px}button,.button{display:inline-block;font:inherit;background:#203555;color:white;border:0;border-radius:8px;padding:11px 17px;cursor:pointer;text-decoration:none}label{display:block;margin:10px 0}a{color:#203555}.small{font-size:14px}#links{overflow-wrap:anywhere}#key{font-family:monospace;font-size:14px}@media(max-width:600px){main{margin:0;padding:12px}section{padding:18px}}</style></head><body><main><h1>Je kalender online zetten</h1><p>Alles gebeurt in je gewone browser. Je hoeft geen programma te installeren.</p><section><h2>1. Publiceer de kalender</h2><p>Kopieer eerst je persoonlijke beheersleutel. Open daarna de publicatiepagina, meld je aan bij Cloudflare en verbind GitHub als dat gevraagd wordt. Plak de sleutel in het veld <em>EDITOR_TOKEN</em> en kies <em>Deploy</em>.</p><label for="key">Je persoonlijke beheersleutel</label><input id="key" readonly value="${key}"><p><button id="copy">Sleutel kopiëren</button></p><p><a class="button" href="${DEPLOY_URL}" target="_blank" rel="noopener noreferrer">Kalender publiceren</a></p><p class="small">Gebruik het Workers Free-abonnement. Een betaald abonnement of eigen domeinnaam is niet nodig. De gratis dienst heeft gebruikslimieten; de voorwaarden kunnen later veranderen. Bewaar dit startbestand privé: het bevat je sleutel en de kalenderinhoud.</p></section><section><h2>2. Zet je bestaande inhoud over</h2><p>Na een geslaagde publicatie toont Cloudflare een adres dat eindigt op <em>.workers.dev</em>. Plak dat hieronder.</p><label for="origin">Adres van je gepubliceerde kalender</label><input id="origin" type="url" placeholder="https://jouw-kalender.jouw-account.workers.dev"><p><button id="prepare">Mijn links klaarzetten</button></p><div id="links" hidden><p><a id="import">Kalenderinhoud overzetten</a></p><p>Selecteer op die pagina ditzelfde bestand <em>Kalender-start.html</em> en klik op <em>Kalender overzetten</em>.</p><p><a id="manage">Kalender wijzigen</a></p><p>Na het overzetten vind je op de beheerpagina ook de code voor Smartschool.</p></div><p id="status" role="status"></p></section></main><script id="calendar-data" type="application/json">${JSON.stringify(data).replace(/</g,'\\u003c')}</script><script>const key=document.getElementById('key');document.getElementById('copy').onclick=async()=>{key.focus();key.select();try{await navigator.clipboard.writeText(key.value);document.getElementById('copy').textContent='Sleutel gekopieerd';}catch{document.getElementById('copy').textContent='Druk Ctrl+C om de geselecteerde sleutel te kopiëren';}};document.getElementById('prepare').onclick=()=>{const status=document.getElementById('status');document.getElementById('links').hidden=true;try{const url=new URL(document.getElementById('origin').value.trim());if(url.protocol!=='https:' || !/^[a-z0-9-]+\\.[a-z0-9-]+\\.workers\\.dev$/i.test(url.hostname) || url.username || url.password || url.port)throw new Error();document.getElementById('import').href=url.origin+'/overzetten#sleutel='+encodeURIComponent(key.value);document.getElementById('manage').href=url.origin+'/beheer#sleutel='+encodeURIComponent(key.value);document.getElementById('links').hidden=false;status.textContent='De links staan klaar. Zet eerst je kalenderinhoud over.';}catch{status.textContent='Plak het volledige https-adres uit Cloudflare dat eindigt op .workers.dev.';}};</script></body></html>`;
}

async function main() {
  const root=fileURLToPath(new URL('../',import.meta.url));
  const sql=await readFile(resolve(root,'private-import/import.sql'),'utf8');
  const {manifest,data}=buildBrowserPackage(sql);
  await mkdir(resolve(root,'private-import'),{recursive:true});
  const statePath=resolve(root,'private-import/browser-installation.json');
  let state;try{state=JSON.parse(await readFile(statePath,'utf8'));}catch(error){if(error.code!=='ENOENT')throw error;state={key:randomBytes(32).toString('hex')};await writeFile(statePath,JSON.stringify(state),{mode:0o600});}
  await writeFile(resolve(root,'src/import-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  const output=resolve(root,'private-import/Kalender-start.html');
  await writeFile(output,startPage(data,state.key),{mode:0o600});
  console.log(JSON.stringify({output,chunks:data.chunks.length,statements:data.chunks.reduce((n,c)=>n+c.statements.length,0)}));
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)) main().catch(error=>{console.error(error.message);process.exitCode=1;});
