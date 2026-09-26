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
  for (const item of items) {
    const month = item.date_local.slice(0,7);
    if (!byMonth.has(month)) byMonth.set(month,new Map());
    const days = byMonth.get(month);
    if (!days.has(item.date_local)) days.set(item.date_local,[]);
    days.get(item.date_local).push(item);
  }
  const months = [...byMonth].map(([ym,days])=>{
    const month = Number(ym.slice(5,7));
    const rows = [...days].map(([date,entries])=>`<div class="day"><div class="date">${esc(formatDate(date))}</div><div class="entries">${entries.map(item=>{
      const color = CATEGORIES[item.category]?.[0] ?? CATEGORIES.algemeen[0];
      const time = item.start_time ? `${esc(item.start_time)}${item.end_time ? `–${esc(item.end_time)}`:''} · ` : '';
      return `<p class="item" style="color:${color}">${time}${esc(item.title)}${item.description ? `<br><span class="detail">${esc(item.description)}</span>`:''}</p>`;
    }).join('')}</div></div>`).join('');
    return `<section class="month"><h2 style="background:${MONTH_COLOR[month]}">${MONTHS[month]} ${esc(ym.slice(0,4))}</h2>${rows}</section>`;
  }).join('');
  const content = months || '<div class="month"><div class="empty">De kalenderinhoud wordt toegevoegd zodra de actuele HTML is ontvangen.</div></div>';
  // Keep this route and its iframe contract stable. The final supplied HTML replaces the renderer later.
  return `<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="${REFRESH_SECONDS}"><title>Schoolkalender · De Telescoop</title><style>${BASE_CSS}</style></head><body><main class="wrap"><header class="top"><span class="brand">De Telescoop · schoolkalender</span><span class="small">Verversing om de 30 minuten</span></header>${content}</main></body></html>`;
}

export function renderManager() {
  // The editor key is only ever read from the URL fragment. Fragments never reach HTTP logs.
  return `<!doctype html><html lang="nl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="referrer" content="no-referrer"><title>Kalender beheren · De Telescoop</title><style>${BASE_CSS}body{background:#f7f5f1}.wrap{max-width:800px}.panel{background:#fff;border:1px solid #e5dfd8;border-radius:14px;padding:18px;margin:16px 0}.panel h2{margin:0 0 10px;font-size:1.2rem}.fields{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}label{display:block;font-size:.9rem;margin:9px 0 4px}input,textarea,select{font:inherit;width:100%;padding:10px;border:1px solid #c9c2bd;border-radius:7px;background:#fff}textarea{min-height:82px}button{font:inherit;background:#203555;color:white;padding:10px 14px;border:0;border-radius:8px;cursor:pointer}button.danger{background:#8a2f2f}button:disabled{opacity:.5}.result{padding:10px 12px;margin:10px 0;border-radius:8px;background:#f0f4fa}.row{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:9px 0;border-top:1px solid #eee}.row span{overflow-wrap:anywhere}@media(max-width:550px){.fields{grid-template-columns:1fr}.row{align-items:flex-start}}
  </style></head><body><main class="wrap"><header class="top"><span class="brand">Kalender beheren</span><a href="/smartschool-calendar">Bekijk kalender</a></header><section class="panel" id="keyPanel"><h2>Beheersleutel</h2><p>Open de beheerlink of vul de sleutel hier in.</p><label for="key">Beheersleutel</label><input id="key" type="password" autocomplete="off"><p><button id="useKey">Verder</button></p></section><div id="app" hidden><section class="panel"><h2>Kalenderitem toevoegen</h2><label for="prompt">Beschrijf de afspraak in gewone taal</label><textarea id="prompt" placeholder="Bijvoorbeeld: Voeg op 6 oktober om 15.30 teamvergadering toe"></textarea><p><button id="interpret">Interpreteren</button></p><div id="preview" hidden><p id="assumptions" class="result"></p><div class="fields"><div><label for="date">Datum</label><input id="date" type="date"></div><div><label for="title">Tekst in kalender</label><input id="title" maxlength="500"></div><div><label for="start">Beginuur (optioneel)</label><input id="start" type="time"></div><div><label for="end">Einduur (optioneel)</label><input id="end" type="time"></div><div><label for="category">Kleur</label><select id="category">${Object.entries(CATEGORIES).map(([k,v])=>`<option value="${k}">${v[1]}</option>`).join('')}</select></div><div><label for="description">Extra regel (optioneel)</label><textarea id="description"></textarea></div></div><p><button id="save">Na controle toevoegen</button></p></div></section><section class="panel"><h2>Kalenderitems verwijderen</h2><p>Zoek een item, kies de juiste regel en bevestig het verwijderen. De wijziging blijft in het auditlog.</p><label for="search">Zoek op datum of tekst</label><input id="search" placeholder="Bijvoorbeeld: 01/12 of directie"><div id="items"></div></section></div><p id="notice" role="status" aria-live="polite"></p></main><script type="module">${MANAGER_JS}</script></body></html>`;
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
  let items=[], visibleCount=100;
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
      items=collected;sortItems();
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
  $('search').oninput=()=>{visibleCount=100;showItems();};
}

const MANAGER_JS=`const filterItems=${filterItems.toString()}; (${managerBootstrap.toString()})();`;
