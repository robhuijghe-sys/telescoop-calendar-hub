import {parseInstruction} from './parser.mjs';
import {CATEGORIES, renderCalendar, renderManager} from './pages.mjs';

const json = (data, status=200) => new Response(JSON.stringify(data), {status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer'}});
const html = (data, isCalendar=false) => new Response(data, {headers:{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Robots-Tag':'noindex, nofollow',
  // The calendar keeps the proven Smartschool iframe contract. The management page cannot be framed.
  'Content-Security-Policy':`default-src 'none'; style-src 'unsafe-inline'; ${isCalendar ? "script-src 'none';" : "script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none';"} img-src 'self' https://telescoop-sgr8.smartschool.be; base-uri 'none'; form-action 'self'`}});

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
  const body = await request.text();
  if (body.length > 16_384) throw new Error('Invoer te groot.');
  try {return JSON.parse(body);} catch {throw new Error('Ongeldige invoer.');}
}

function validItem(item) {
  if (!item || typeof item!=='object' || Array.isArray(item)) throw new Error('Ongeldige invoer.');
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
  if (!(category in CATEGORIES)) throw new Error('Kies een geldige kleurcategorie.');
  return {title,description,date,start,end,category};
}

async function visibleItems(db, limit=2000) {
  const result = await db.prepare('SELECT id,date_local,title,description,start_time,end_time,category,source FROM calendar_items WHERE deleted_at IS NULL ORDER BY date_local,start_time,id LIMIT ?').bind(limit).all();
  return result.results || [];
}

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    const method = request.method;
    if (!env.DB) return json({error:'Database nog niet ingesteld.'},503);
    try {
      if (method==='GET' && path==='/health') return json({ok:true});
      if (method==='GET' && path==='/smartschool-calendar') return html(renderCalendar(await visibleItems(env.DB)),true);
      if (method==='GET' && (path==='/beheer' || path==='/')) return html(renderManager());
      if (!path.startsWith('/api/manage/')) return json({error:'Niet gevonden.'},404);
      if (!(await authorized(request,env))) return json({error:'Ongeldige of ontbrekende beheersleutel.'},401);
      if (method==='GET' && path==='/api/manage/items') return json({items:await visibleItems(env.DB)});
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
