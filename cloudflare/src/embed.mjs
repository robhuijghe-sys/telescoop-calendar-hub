export function smartschoolCode(origin) {
  const url=new URL('/smartschool-calendar',origin);
  if(!['https:','http:'].includes(url.protocol)) throw new Error('Ongeldig kalenderadres.');
  return `<iframe src="${url.href}" title="Schoolkalender De Telescoop" width="100%" height="1600" style="width:100%;height:1600px;border:0;background:#fff;" loading="lazy" referrerpolicy="no-referrer"></iframe>`;
}
