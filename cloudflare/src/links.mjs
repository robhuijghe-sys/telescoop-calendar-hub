export const SMARTSCHOOL_ORIGIN='https://telescoop-sgr8.smartschool.be';
export function normalizeLink(value) {
  if(typeof value!=='string' || value.length>4096 || /[\u0000-\u0020\u007f]/.test(value.trim())) throw new Error('Controleer het linkadres.');
  let url;
  try {url=new URL(value.trim().startsWith('/') && !value.trim().startsWith('//') ? SMARTSCHOOL_ORIGIN+value.trim() : value.trim());} catch {throw new Error('Controleer het linkadres: gebruik https://.');}
  if(!['https:','http:'].includes(url.protocol) || url.username || url.password) throw new Error('Controleer het linkadres: alleen http en https zijn toegestaan.');
  return url.href;
}
export function validateLink(body) {
  if(!body || typeof body.description!=='string' || !body.description.trim() || body.description.trim().length>200) throw new Error('Controleer de omschrijving (maximaal 200 tekens).');
  return {description:body.description.trim(),url:normalizeLink(body.url)};
}
export async function listLinks(db) {
  const {results=[]}=await db.prepare('SELECT id,description,url,version FROM calendar_links WHERE deleted_at IS NULL ORDER BY id').bind().all();return results;
}
export async function manageLinks(request,db,path,payload) {
  if(path==='/api/manage/links' && request.method==='GET') return {links:await listLinks(db)};
  const match=path.match(/^\/api\/manage\/links\/(\d+)$/), now=new Date().toISOString();
  if(path==='/api/manage/links' && request.method==='POST') {
    const link=validateLink(await payload(request));
    try {return await db.prepare('INSERT INTO calendar_links(description,url,updated_at) VALUES(?,?,?) RETURNING id,description,url,version').bind(link.description,link.url,now).first();} catch(error) {if(/UNIQUE constraint failed/i.test(String(error))) return {duplicate:true};throw error;}
  }
  if(match && ['PUT','DELETE'].includes(request.method)) {
    const id=Number(match[1]);if(!Number.isSafeInteger(id) || id<1) throw new Error('Controleer de gekozen link.');
    const version=Number(request.headers.get('If-Match')?.replace(/^"|"$/g,''));
    if(!Number.isSafeInteger(version) || version<1) return {conflict:true};
    if(request.method==='PUT') {
      const link=validateLink(await payload(request));
      try {
        const result=await db.prepare('UPDATE calendar_links SET description=?,url=?,updated_at=?,version=version+1 WHERE id=? AND version=? AND deleted_at IS NULL RETURNING id,description,url,version').bind(link.description,link.url,now,id,version).first();
        if(result) return result;
      }catch(error){if(/UNIQUE constraint failed/i.test(String(error))) return {duplicate:true};throw error;}
    } else {
      const result=await db.prepare('UPDATE calendar_links SET deleted_at=?,updated_at=?,version=version+1 WHERE id=? AND version=? AND deleted_at IS NULL').bind(now,now,id,version).run();
      if(result.meta?.changes) return {deleted:true,id};
    }
    const current=await db.prepare('SELECT id FROM calendar_links WHERE id=? AND deleted_at IS NULL').bind(id).first();
    return current ? {conflict:true} : {missing:true};
  }
  return null;
}
