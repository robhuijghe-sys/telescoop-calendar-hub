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
  const {results=[]}=await db.prepare('SELECT id,description,url FROM calendar_links WHERE deleted_at IS NULL ORDER BY id').bind().all();return results;
}
export async function manageLinks(request,db,path,payload) {
  if(path==='/api/manage/links' && request.method==='GET') return {links:await listLinks(db)};
  const match=path.match(/^\/api\/manage\/links\/(\d+)$/), now=new Date().toISOString();
  if(path==='/api/manage/links' && request.method==='POST') {
    const link=validateLink(await payload(request));
    return db.prepare('INSERT INTO calendar_links(description,url,updated_at) VALUES(?,?,?) RETURNING id,description,url').bind(link.description,link.url,now).first();
  }
  if(match && ['PUT','DELETE'].includes(request.method)) {
    const id=Number(match[1]);if(!Number.isSafeInteger(id) || id<1) throw new Error('Controleer de gekozen link.');
    if(request.method==='PUT') {
      const link=validateLink(await payload(request));
      return await db.prepare('UPDATE calendar_links SET description=?,url=?,updated_at=? WHERE id=? AND deleted_at IS NULL RETURNING id,description,url').bind(link.description,link.url,now,id).first() || {missing:true};
    }
    const result=await db.prepare('UPDATE calendar_links SET deleted_at=?,updated_at=? WHERE id=? AND deleted_at IS NULL').bind(now,now,id).run();
    return result.meta?.changes ? {deleted:true,id} : {missing:true};
  }
  return null;
}
