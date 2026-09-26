import {serveCalendar} from './read-calendar.mjs';
import {manageLinks} from './links.mjs';
import {parseInstruction} from './parser.mjs';
import {CATEGORIES, renderManager} from './pages.mjs';

const json = (data, status=200) => new Response(JSON.stringify(data), {status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}});
export const html = (data, isCalendar=false) => new Response(data, {headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Robots-Tag':'noindex, nofollow',
  // The calendar keeps the proven Smartschool iframe contract. The management page cannot be framed.
  'Content-Security-Policy':`default-src 'none'; style-src 'unsafe-inline'; ${isCalendar ? "script-src 'none';" : "script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none';"} font-src 'self'; img-src 'self' https://telescoop-sgr8.smartschool.be; base-uri 'none'; form-action 'self'`}});

async function authorized(request, env) {
  const expected = env.EDITOR_TOKEN_SHA256;
  const bearer = request.headers.get('Authorization')?.match(/^Bearer ([A-Za-z0-9_-]{32,128})$/)?.[1];
  if (!expected || !/^[a-f0-9]{64}$/i.test(expected) || !bearer) return false;
  const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(bearer)));
  const actual = Array.from(bytes, b=>b.toString(16).padStart(2,'0')).join('');
  let difference=0;
  for(let i=0;i<64;i++) difference |= actual.charCodeAt(i) ^ expected.toLowerCase().charCodeAt(i);
  return difference === 0;
}

async function payload(request) {
  if (Number(request.headers.get('content-length') || 0) > 16_384) throw new Error('Invoer te groot.');
  if (!request.body) throw new Error('Ongeldige invoer.');
  const reader=request.body.getReader(), chunks=[];
  let size=0;
  while (true) {
    const {done,value}=await reader.read();
    if(done) break;
    size+=value.byteLength;
    if(size>16_384) {await reader.cancel();throw new Error('Invoer te groot.');}
    chunks.push(value);
  }
  const bytes=new Uint8Array(size);let offset=0;
  for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.byteLength;}
  const body=new TextDecoder().decode(bytes);
  try {return JSON.parse(body);} catch {throw new Error('Ongeldige invoer.');}
}

function validItem(item) {
  if (!item || typeof item!=='object' || Array.isArray(item)) throw new Error('Ongeldige invoer.');
  for (const field of ['title','description','date_local','start_time','end_time','category']) {
    if(item[field]!==undefined && typeof item[field]!=='string') throw new Error('Ongeldige invoer.');
  }
  const title = String(item.title ?? '').trim();
  const description = String(item.description ?? '').trim();
  const date = String(item.date_local ?? '');
  const start = String(item.start_time ?? '');
  const end = String(item.end_time ?? '');
  const category = String(item.category ?? 'algemeen');
  if (!title || title.length>500 || description.length>2000) throw new Error('Controleer de lengte van de tekst.');
  const parsedDate = /^\d{4}-\d{2}-\d{2}$/.test(date) ? new Date(`${date}T00:00:00Z`) : null;
  if (!parsedDate || Number.isNaN(parsedDate.getTime()) || parsedDate.toISOString().slice(0,10)!==date) throw new Error('Kies een geldige datum.');
  if ((start && !/^([01]\d|2[0-3]):[0-5]\d$/.test(start)) || (end && !/^([01]\d|2[0-3]):[0-5]\d$/.test(end)) || (end && (!start || end<=start))) throw new Error('Controleer de begin- en eindtijd.');
  if (!Object.hasOwn(CATEGORIES,category)) throw new Error('Kies een geldige kleurcategorie.');
  return {title,description,date,start,end,category};
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url), path=url.pathname;
    const method = request.method;
    if (!env.DB) return json({error:'Database nog niet ingesteld.'},503);
    try {
      if (method==='GET' && path==='/health') {
        try {const result=await env.DB.batch([
          env.DB.prepare('SELECT display_html FROM calendar_items LIMIT 1').bind(),
          env.DB.prepare('SELECT version FROM calendar_links LIMIT 1').bind(),
          env.DB.prepare('SELECT value FROM calendar_settings LIMIT 1').bind(),
          env.DB.prepare('SELECT epoch,revision FROM calendar_state WHERE id=1').bind()
        ]);if(result[3].results?.length!==1) throw new Error('Kalenderversie ontbreekt.');return json({ok:true});}
        catch {return json({ok:false,error:'Database niet gereed.'},503);}
      }
      if (['GET','HEAD'].includes(method) && path==='/smartschool-calendar') return await serveCalendar(request,env,ctx,html);
      if (method==='GET' && (path==='/beheer' || path==='/')) return html(renderManager({origin:url.origin}));
      if (!path.startsWith('/api/manage/')) return json({error:'Niet gevonden.'},404);
      if (!(await authorized(request,env))) return json({error:'Ongeldige of ontbrekende beheersleutel.'},401);
      if(path==='/api/manage/links' || path.startsWith('/api/manage/links/')) {
        const result=await manageLinks(request,env.DB,path,payload);
        if(result?.conflict) return json({error:'Deze link is ondertussen gewijzigd. Vernieuw de lijst en kies bij deze link opnieuw Aanpassen om de nieuwste versie te bekijken.'},409);
        if(result?.duplicate) return json({error:'Deze omschrijving en link bestaan al.'},409);
        if(result?.missing) return json({error:'Deze link is al verwijderd of bestaat niet.'},404);
        if(result) return json(result,method==='POST' ? 201 : 200);
      }
      if (method==='GET' && path==='/api/manage/items') {
        const cursor=Number(url.searchParams.get('after') || 0);
        if(!Number.isSafeInteger(cursor) || cursor<0) return json({error:'Ongeldige paginakeuze.'},400);
        const {results=[]}=await env.DB.prepare('SELECT id,date_local,title,description,start_time,end_time,category,source FROM calendar_items WHERE deleted_at IS NULL AND id>? ORDER BY id LIMIT 501').bind(cursor).all();
        const items=results.slice(0,500);
        return json({items,next_cursor:results.length>500 ? items.at(-1).id : null});
      }
      if (method==='POST' && path==='/api/manage/interpret') {
        const body = await payload(request);
        if (!body || typeof body !== 'object') return json({error:'Ongeldige invoer.'},400);
        if (typeof body.text!=='string' || body.text.length>2000) return json({error:'Schrijf een korte opdracht.'},400);
        return json(parseInstruction(body.text));
      }
      if (method==='POST' && path==='/api/manage/items') {
        const item=validItem(await payload(request)), now=new Date().toISOString();
        try {
          const result=await env.DB.prepare('INSERT INTO calendar_items(date_local,title,description,start_time,end_time,category,source,created_at) VALUES(?,?,?,?,?,?,?,?) RETURNING id')
            .bind(item.date,item.title,item.description,item.start,item.end,item.category,'manual',now).first();
          return json({id:result.id},201);
        } catch(error) {
          if (/UNIQUE constraint failed/i.test(String(error))) return json({error:'Er bestaat op die dag al een item met dezelfde titel.'},409);
          throw error;
        }
      }
      const match = path.match(/^\/api\/manage\/items\/(\d+)$/);
      if (method==='DELETE' && match) {
        const id=Number(match[1]), now=new Date().toISOString();
        if (!Number.isSafeInteger(id) || id<1) return json({error:'Ongeldig item.'},400);
        // The database trigger records the deletion in the same transaction as this update.
        const result=await env.DB.prepare('UPDATE calendar_items SET deleted_at=? WHERE id=? AND deleted_at IS NULL').bind(now,id).run();
        if (!result.meta?.changes) return json({error:'Dit item is al verwijderd of bestaat niet.'},404);
        return json({deleted:true,id});
      }
      return json({error:'Niet gevonden.'},404);
    } catch(error) {
      if (/^(Invoer te groot|Ongeldige invoer|Controleer|Kies een geldige|Schrijf een korte)/.test(String(error.message))) return json({error:error.message},400);
      console.error('Kalenderaanvraag mislukt',error);
      return json({error:'De kalender kon de aanvraag niet verwerken.'},500);
    }
  }
};
