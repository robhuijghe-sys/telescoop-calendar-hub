import {normalizeLink} from './links.mjs';
export const REFRESH_SECONDS = 30 * 60;
export const CATEGORIES = {
  ouders:['#99CA3B','Ouders'], personeel:['#C614A1','Personeel'],
  uitstap:['#F09009','Uitstap / activiteit'], waarschuwing:['#D32F2F','Afwezig / waarschuwing'],
  algemeen:['#2F2926','Algemeen']
};
const MONTHS = ['','JANUARI','FEBRUARI','MAART','APRIL','MEI','JUNI','JULI','AUGUSTUS','SEPTEMBER','OKTOBER','NOVEMBER','DECEMBER'];
const MONTH_COLOR = ['','#5F7F9F','#748CB7','#79A36B','#76AD66','#5FA66E','#D7A83E','#D9904F','#CF895C','#D39A5F','#C86F54','#A85B52','#6F87A8'];
const esc = value => String(value ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const BASE_CSS = `*{box-sizing:border-box}html,body{margin:0;background:#fff;color:#2e2926;font-family:Inter,Aptos,"Segoe UI",Arial,sans-serif;line-height:1.5}a{color:#203555}.wrap{max-width:1180px;margin:auto;padding:18px 12px 30px}.top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:16px}.brand{font-size:1.15rem;font-weight:700;color:#203555}.small{font-size:.9rem;color:#665c56}.month{border:1px solid #ece7e1;border-radius:16px;overflow:hidden;margin:0 0 18px;box-shadow:0 5px 18px #28211c0c}.month h2{margin:0;padding:9px 17px;color:#fff;font-size:1.15rem;letter-spacing:.015em}.day{display:grid;grid-template-columns:115px 1fr;border-top:1px solid #f0ebe6}.date{background:#fff5eb;padding:12px 14px;font-weight:700}.entries{padding:12px 16px;overflow-wrap:anywhere}.item{margin:0 0 7px}.item:last-child{margin:0}.detail{white-space:pre-line}.empty{padding:14px 16px;color:#665c56}@media(max-width:550px){.day{display:block}.date{padding:7px 12px}.entries{padding:9px 12px}.wrap{padding:10px 7px}.month{border-radius:12px}}`;

function formatDate(date) {
  const [y,m,d] = date.split('-').map(Number);
  const weekday = ['zo','ma','di','woe','do','vr','za'][new Date(Date.UTC(y,m-1,d)).getUTCDay()];
  return `${weekday} ${String(d).padStart(2,'0')}/${String(m).padStart(2,'0')}`;
}

export function renderCalendar(items, options={}) {
  const byMonth = new Map();
  for(const date of options.layout?.dates || []) {
    const ym=date.slice(0,7);if(!byMonth.has(ym)) byMonth.set(ym,new Map());byMonth.get(ym).set(date,[]);
  }
  for (const item of items) {
    const month = item.date_local.slice(0,7);
    if (!byMonth.has(month)) byMonth.set(month,new Map());
    const days = byMonth.get(month);
    if (!days.has(item.date_local)) days.set(item.date_local,[]);
    days.get(item.date_local).push(item);
  }
  const months = [...byMonth].sort(([a],[b])=>a.localeCompare(b)).map(([ym,days])=>{
    const month = Number(ym.slice(5,7));
    const rows = [...days].sort(([a],[b])=>a.localeCompare(b)).map(([date,entries])=>`<div class="day"><div class="date">${esc(formatDate(date))}</div><div class="entries">${entries.map(item=>{
      const color = CATEGORIES[item.category]?.[0] ?? CATEGORIES.algemeen[0];
      const time = item.start_time ? `${esc(item.start_time)}${item.end_time ? `–${esc(item.end_time)}`:''} · ` : '';
      if(item.source==='legacy' && item.display_html) return `<div class="item">${item.display_html}</div>`;
      return `<p class="item" style="color:${color}">${time}${esc(item.title)}${item.description ? `<br><span class="detail">${esc(item.description)}</span>`:''}</p>`;
    }).join('')}</div></div>`).join('');
    return `<section class="month"><h2 style="background:${esc(options.layout?.months?.[ym]?.gradient || MONTH_COLOR[month])}">${MONTHS[month]} ${esc(ym.slice(0,4))}<span class="season">${esc(options.layout?.months?.[ym]?.season || '')}</span></h2>${options.layout?.focus?.[ym] ? `<div class="focus">${esc(options.layout.focus[ym])}</div>` : ''}${rows}</section>`;
  }).join('');
  const content = months || '<div class="month"><div class="empty">Er zijn nog geen kalenderitems.</div></div>';
  const links=(options.links || []).map(link=>{
    let href;try {href=normalizeLink(link.url);}catch{return '';}
    return `<p><a href="${esc(href)}" target="_blank" rel="noopener noreferrer"><span aria-hidden="true">🔗</span> ${esc(link.description)}</a></p>`;
  }).join('');
  return `<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="${REFRESH_SECONDS}"><title>Schoolkalender · De Telescoop</title><style>${BASE_CSS}.wrap{max-width:1280px;font-size:12px}.logo{display:block;width:100%;max-width:210px;height:auto;margin:0 auto 12px}.reference-links{margin-bottom:20px}.reference-links p{margin:0 0 6px}.reference-links a{color:#6b5f59;text-decoration:none;border-bottom:1px solid #d8cfc8;overflow-wrap:anywhere}.reference-links a:hover{text-decoration:underline}.focus{padding:10px 16px;background:#fbfaf8;color:#605651}.month{border-radius:20px}.season{float:right;font-size:10px;letter-spacing:.14em;font-weight:400;padding:3px 9px;border-radius:999px;background:#ffffff2e}</style></head><body><main class="wrap"><header><img class="logo" src="https://telescoop-sgr8.smartschool.be/public/telescoop-sgr8/Images/P8JUKt6zzs28fnA9LjPg2owGK1768144749.PNG" alt="De Telescoop"><nav class="reference-links" aria-label="Verwijslinks">${links}</nav></header>${content}</main></body></html>`;
}

export function renderManager() {
  // The editor key is only ever read from the URL fragment. Fragments never reach HTTP logs.
  return `<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>Kalender beheren · De Telescoop</title><style>${BASE_CSS}body{background:#f7f5f1}.wrap{max-width:800px}.panel{background:#fff;border:1px solid #e5dfd8;border-radius:14px;padding:18px;margin:16px 0}.panel h2{margin:0 0 10px;font-size:1.2rem}.fields{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}label{display:block;font-size:.9rem;margin:9px 0 4px}input,textarea,select{font:inherit;width:100%;padding:10px;border:1px solid #c9c2bd;border-radius:7px;background:#fff}textarea{min-height:82px}button{font:inherit;background:#203555;color:white;padding:10px 14px;border:0;border-radius:8px;cursor:pointer}button.danger{background:#8a2f2f}button:disabled{opacity:.5}.result{padding:10px 12px;margin:10px 0;border-radius:8px;background:#f0f4fa}.row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:9px 0;border-top:1px solid #eee}.row span{overflow-wrap:anywhere;min-width:0;flex:1}.row button{flex-shrink:0}@media(max-width:550px){.fields{grid-template-columns:1fr}.row{align-items:flex-start;flex-wrap:wrap}.row span{flex-basis:100%}}
  </style></head><body><main class="wrap"><header class="top"><span class="brand">Kalender beheren</span><a href="/smartschool-calendar">Bekijk kalender</a></header><section class="panel" id="keyPanel"><h2>Beheersleutel</h2><p>Open de beheerlink of vul de sleutel hier in.</p><label for="key">Beheersleutel</label><input id="key" type="password" autocomplete="off"><p><button id="useKey">Verder</button></p></section><div id="app" hidden><section class="panel"><h2>Links beheren</h2><p>Deze links verschijnen onder het logo, steeds met hetzelfde linkicoontje.</p><form id="linkForm"><label for="linkDescription">Omschrijving</label><input id="linkDescription" maxlength="200" required><label for="linkUrl">Link</label><input id="linkUrl" type="text" placeholder="https://… of /deeplink/…" maxlength="4096" required><p><button id="linkSave" type="submit">Link toevoegen</button> <button id="linkCancel" type="button" hidden>Annuleren</button></p></form><div id="links"></div></section><section class="panel"><h2>Kalenderitem toevoegen</h2><label for="prompt">Beschrijf de afspraak in gewone taal</label><textarea id="prompt" placeholder="Bijvoorbeeld: Voeg op 6 oktober om 15.30 teamvergadering toe"></textarea><p><button id="interpret">Interpreteren</button></p><div id="preview" hidden><p id="assumptions" class="result"></p><div class="fields"><div><label for="date">Datum</label><input id="date" type="date"></div><div><label for="title">Tekst in kalender</label><input id="title" maxlength="500"></div><div><label for="start">Beginuur (optioneel)</label><input id="start" type="time"></div><div><label for="end">Einduur (optioneel)</label><input id="end" type="time"></div><div><label for="category">Kleur</label><select id="category">${Object.entries(CATEGORIES).map(([k,v])=>`<option value="${k}">${v[1]}</option>`).join('')}</select></div><div><label for="description">Extra regel (optioneel)</label><textarea id="description"></textarea></div></div><p><button id="save">Na controle toevoegen</button></p></div></section><section class="panel"><h2>Kalenderitems verwijderen</h2><p>Zoek een item, kies de juiste regel en bevestig het verwijderen. De wijziging blijft in het auditlog.</p><label for="search">Zoek op datum of tekst</label><input id="search" placeholder="Bijvoorbeeld: 01/12 of directie"><div id="items"></div></section></div><p id="notice" role="status" aria-live="polite"></p></main><script type="module">${MANAGER_JS}</script></body></html>`;
}

export function filterItems(items,query) {
  const normalize=s=>String(s).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/afwezigheid/g,'afwezig');
  const terms=normalize(query).trim().split(/\s+/).filter(Boolean);
  return items.filter(item=>{
    const [,month,day]=item.date_local.split('-');
    const haystack=normalize(`${item.date_local} ${day}/${month} ${Number(day)}/${Number(month)} ${item.title} ${item.description}`);
    return terms.every(term=>haystack.includes(term));
  });
}

function managerBootstrap() {
  const $=id=>document.getElementById(id);
  let key=new URLSearchParams(location.hash.slice(1)).get('sleutel') || '';
  try {key=key || sessionStorage.getItem('calendarKey') || '';} catch {}
  if(location.hash) history.replaceState(null,'',location.pathname);
  let items=[], visibleCount=100, links=[], editingLink=null;
  const say=message=>{$('notice').textContent=message;};
  const api=async(path,options={})=>{
    const response=await fetch(path,{...options,headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'}});
    if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(data.error || 'De aanvraag is mislukt.');}
    return response.json();
  };
  const sortItems=()=>items.sort((a,b)=>a.date_local.localeCompare(b.date_local) || a.start_time.localeCompare(b.start_time) || a.id-b.id);
  async function open() {
    $('useKey').disabled=true;
    try {
      let after=0, collected=[];
      do {
        const result=await api('/api/manage/items?after='+after);
        collected.push(...result.items);
        if(result.next_cursor===null) break;
        if(!Number.isSafeInteger(result.next_cursor) || result.next_cursor<=after) throw new Error('De lijst kon niet volledig worden geladen.');
        after=result.next_cursor;
      } while(true);
      items=collected;sortItems();links=(await api('/api/manage/links')).links;showLinks();
      try {sessionStorage.setItem('calendarKey',key);} catch {}
      $('keyPanel').hidden=true;$('app').hidden=false;showItems();say('');
    } catch(e){$('keyPanel').hidden=false;$('app').hidden=true;say(e.message);}
    finally {$('useKey').disabled=false;}
  }
  $('useKey').onclick=()=>{key=$('key').value.trim();open();};
  if(key) open();
  $('interpret').onclick=async()=>{
    const prompt=$('prompt').value.trim();
    if(!prompt) return say('Schrijf eerst wat je wilt doen.');
    $('interpret').disabled=true;$('preview').hidden=true;
    try {
      const parsed=await api('/api/manage/interpret',{method:'POST',body:JSON.stringify({text:prompt})});
      if(parsed.action==='delete') {
        $('search').value=[parsed.date,parsed.title].filter(Boolean).join(' ');visibleCount=100;
        showItems();$('search').scrollIntoView({behavior:'smooth'});
        say([...(parsed.assumptions || []),'Kies hieronder het juiste item en bevestig de verwijdering.'].join('. '));return;
      }
      $('preview').hidden=false;$('title').value=parsed.title;$('date').value=parsed.date;
      $('start').value=parsed.start_time;$('end').value=parsed.end_time;$('category').value=parsed.category;$('description').value='';
      $('assumptions').textContent=[parsed.missing.length ? 'Vul nog aan: '+parsed.missing.join(', ') : 'Controleer de gegevens vóór het toevoegen.',...(parsed.assumptions || [])].join(' ');
      say('');
    } catch(e){say(e.message);}
    finally {$('interpret').disabled=false;}
  };
  $('save').onclick=async()=>{
    $('save').disabled=true;
    try {
      const item={title:$('title').value.trim(),date_local:$('date').value,start_time:$('start').value,end_time:$('end').value,category:$('category').value,description:$('description').value.trim()};
      const result=await api('/api/manage/items',{method:'POST',body:JSON.stringify(item)});
      items.push({...item,id:result.id,source:'manual'});sortItems();
      $('preview').hidden=true;$('prompt').value='';$('description').value='';showItems();
      say('Kalenderitem opgeslagen. Openstaande kalenders verversen binnen 30 minuten.');
    } catch(e){say(e.message);}
    finally {$('save').disabled=false;}
  };
  function showItems() {
    const list=filterItems(items,$('search').value), box=$('items');box.replaceChildren();
    const status=document.createElement('p');status.className='small';
    status.textContent=list.length ? `${Math.min(visibleCount,list.length)} van ${list.length} items` : 'Geen overeenkomende items.';box.append(status);
    for(const item of list.slice(0,visibleCount)) {
      const row=document.createElement('div');row.className='row';
      const name=document.createElement('span');name.textContent=item.date_local+' · '+(item.start_time ? item.start_time+' · ':'')+item.title;
      const button=document.createElement('button');button.className='danger';button.textContent='Verwijderen';
      button.onclick=async()=>{
        if(!confirm('Verwijder "'+item.title+'" op '+item.date_local+' uit de kalender?')) return;
        button.disabled=true;
        try {await api('/api/manage/items/'+item.id,{method:'DELETE'});items=items.filter(x=>x.id!==item.id);showItems();say('Item verwijderd. Openstaande kalenders verversen binnen 30 minuten.');}
        catch(e){button.disabled=false;say(e.message);}
      };
      row.append(name,button);box.append(row);
    }
    if(list.length>visibleCount){const more=document.createElement('button');more.textContent='Toon meer';more.onclick=()=>{visibleCount+=100;showItems();};box.append(more);}
  }
  function resetLink() {
    editingLink=null;$('linkDescription').value='';$('linkUrl').value='';$('linkSave').textContent='Link toevoegen';$('linkCancel').hidden=true;
  }
  $('linkCancel').onclick=resetLink;
  $('linkForm').onsubmit=async(event)=>{
    event.preventDefault();$('linkSave').disabled=true;$('linkCancel').disabled=true;
    try {
      const result=await api('/api/manage/links'+(editingLink ? '/'+editingLink : ''),{method:editingLink ? 'PUT':'POST',body:JSON.stringify({description:$('linkDescription').value.trim(),url:$('linkUrl').value.trim()})});
      if(editingLink) links=links.map(x=>x.id===editingLink ? result : x);else links.push(result);
      resetLink();showLinks();say('Link opgeslagen. Openstaande kalenders verversen binnen 30 minuten.');
    }catch(e){say(e.message);}finally{$('linkSave').disabled=false;$('linkCancel').disabled=false;}
  };
  function showLinks() {
    const box=$('links');box.replaceChildren();
    for(const link of links) {
      const row=document.createElement('div');row.className='row';
      const text=document.createElement('span');text.textContent='🔗 '+link.description+' — '+link.url;
      const edit=document.createElement('button');edit.textContent='Aanpassen';edit.onclick=()=>{
        if($('linkSave').disabled) return;
        editingLink=link.id;$('linkDescription').value=link.description;$('linkUrl').value=link.url;$('linkSave').textContent='Wijzigingen opslaan';$('linkCancel').hidden=false;
      };
      const remove=document.createElement('button');remove.className='danger';remove.textContent='Verwijderen';remove.onclick=async()=>{
        if($('linkSave').disabled || !confirm('Verwijder de link "'+link.description+'"?')) return;
        remove.disabled=true;
        try{await api('/api/manage/links/'+link.id,{method:'DELETE'});links=links.filter(x=>x.id!==link.id);if(editingLink===link.id) resetLink();showLinks();say('Link verwijderd. Openstaande kalenders verversen binnen 30 minuten.');}
        catch(e){remove.disabled=false;say(e.message);}
      };
      row.append(text,edit,remove);box.append(row);
    }
    if(!links.length) box.textContent='Er zijn nog geen links. Voeg hierboven een link toe.';
  }
  $('search').oninput=()=>{visibleCount=100;showItems();};
}

const MANAGER_JS=`const filterItems=${filterItems.toString()}; (${managerBootstrap.toString()})();`;
