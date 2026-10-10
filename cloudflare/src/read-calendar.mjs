import {renderCalendar} from './pages.mjs';
// Revision is read from the primary database on every request. Mutations invalidate the
// cached representation in the same transaction, with no cross-region purge race.
export async function serveCalendar(request,env,ctx,html,cache=globalThis.caches?.default) {
  const state=await env.DB.prepare('SELECT epoch,revision FROM calendar_state WHERE id=1').bind().first();
  if(!state) throw new Error('Kalenderversie ontbreekt.');
  const version=env.WORKER_VERSION?.id || 'local-v3';
  const etag=`"${version}-${state.epoch}-${state.revision}"`;
  const cacheControl='private, no-cache, must-revalidate';
  const matches=request.headers.get('If-None-Match')?.split(',').some(value=>value.trim().replace(/^W\//,'')===etag || value.trim()==='*');
  if(matches) return new Response(null,{status:304,headers:{ETag:etag,'Cache-Control':cacheControl,'X-Robots-Tag':'noindex, nofollow'}});
  // Never key on user query parameters, cookies or bearer headers.
  const key=new Request(new URL('/__calendar_render/'+encodeURIComponent(etag),request.url));
  let response;
  try {response=await cache?.match(key);}catch { /* cache is an optional optimization */ }
  const hit=!!response;
  if(!response) {
    const [items,links,settings]=await env.DB.batch([
      env.DB.prepare('SELECT id,date_local,title,description,start_time,end_time,category,source,display_html FROM calendar_items WHERE deleted_at IS NULL ORDER BY date_local,start_time,id').bind(),
      env.DB.prepare('SELECT id,description,url FROM calendar_links WHERE deleted_at IS NULL ORDER BY id').bind(),
      env.DB.prepare("SELECT value FROM calendar_settings WHERE key='layout'").bind()
    ]);
    response=html(renderCalendar(items.results || [],{links:links.results || [],layout:settings.results?.[0] ? JSON.parse(settings.results[0].value) : {}}),true);
    response.headers.set('Cache-Control','public, max-age=1800');
    response.headers.set('ETag',etag);
    if(cache && ctx?.waitUntil) ctx.waitUntil(cache.put(key,response.clone()).catch(()=>{}));
  }
  const outgoing=new Response(request.method==='HEAD' ? null : response.body,response);
  outgoing.headers.set('Cache-Control',cacheControl);
  outgoing.headers.set('X-Calendar-Cache',hit ? 'HIT':'MISS');
  return outgoing;
}
