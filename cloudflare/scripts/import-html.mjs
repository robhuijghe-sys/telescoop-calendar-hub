import {parseHTML} from 'linkedom';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {normalizeLink} from '../src/links.mjs';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const text=s=>s.replace(/\s+/g,' ').trim();
const quote=s=>"'"+String(s).replace(/'/g,"''")+"'";
// Only text formatting and ordinary web links survive the import. No source scripts or CSS URLs.
function inline(node) {
  if(node.nodeType===3) return esc(node.textContent);
  if(node.nodeType!==1 || ['SCRIPT','STYLE','IFRAME','OBJECT','IMG'].includes(node.tagName)) return '';
  const inner=Array.from(node.childNodes).map(inline).join('');
  if(node.tagName==='BR') return '<br>';
  if(node.tagName==='A') {try{return `<a href="${esc(normalizeLink(node.getAttribute('href')))}" target="_blank" rel="noopener noreferrer">${inner}</a>`;}catch{return inner;}}
  const styles=[];
  for(const key of ['color','font-weight','font-style','text-decoration']) {
    const value=node.style?.getPropertyValue(key)?.trim();
    if(value && /^(#[a-f\d]{3,8}|rgba?\([\d.,%\s]+\)|[a-z]+|[1-9]00)$/i.test(value)) styles.push(key+':'+value);
  }
  if(['B','STRONG'].includes(node.tagName)) styles.push('font-weight:bold');
  if(['I','EM'].includes(node.tagName)) styles.push('font-style:italic');
  const content=styles.length ? `<span style="${esc(styles.join(';'))}">${inner}</span>` : inner;
  return ['P','DIV','LI'].includes(node.tagName) ? '<br>'+content+'<br>' : content;
}
function splitLines(node) {
  // Walk with ancestor wrappers so styles remain balanced across each line break.
  let lines=[''];
  function walk(n,wrappers=[]) {
    if(n.nodeType===3){lines[lines.length-1]+=wrappers.reduceRight((s,w)=>w[0]+s+w[1],esc(n.textContent));return;}
    if(n.nodeType!==1 || ['SCRIPT','STYLE','IFRAME','OBJECT','IMG'].includes(n.tagName)) return;
    if(n.tagName==='BR'){lines.push('');return;}
    const block=['P','DIV','LI'].includes(n.tagName);
    if(block && lines.at(-1)) lines.push('');
    const clone=n.cloneNode(false);clone.textContent='IMPORT_MARKER';
    const rendered=inline(clone), parts=rendered.split('IMPORT_MARKER');
    const next=parts.length===2 ? [...wrappers,[parts[0].replace(/^<br>/,''),parts[1].replace(/<br>$/,'')]] : wrappers;
    for(const child of n.childNodes) walk(child,next);
    if(block && lines.at(-1)) lines.push('');
  }
  for(const child of node.childNodes) walk(child);
  return lines.map(html=>({html,title:text(parseHTML('<div>'+html+'</div>').document.firstElementChild.textContent)})).filter(x=>x.title);
}
export function convert(source,startYear) {
  if(!Number.isInteger(startYear) || startYear<2000 || startYear>2100) throw new Error('Geef het startjaar van het schooljaar expliciet op.');
  const {document}=parseHTML(source), root=document.querySelector('.telescoop-kalender-webfont');
  if(!root) throw new Error('Kalendercontainer ontbreekt.');
  const rows=Array.from(root.querySelectorAll('tr')).filter(tr=>/^\s*[a-z]+\s+\d{1,2}\/\d{2}\s*$/i.test(tr.children[0]?.textContent || ''));
  if(!rows.length) throw new Error('Geen kalenderdagen gevonden.');
  const items=[],dates=[],focus={},months={},links=[];
  for(const row of rows) {
    const match=row.children[0].textContent.match(/(\d{1,2})\/(\d{2})/),day=Number(match[1]),month=Number(match[2]);
    const year=month>=9 ? startYear : startYear+1,date=`${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    if(new Date(date+'T00:00:00Z').toISOString().slice(0,10)!==date) throw new Error('Ongeldige datum '+date);
    const actualDay=new Intl.DateTimeFormat('nl-BE',{weekday:'short',timeZone:'UTC'}).format(new Date(date));
    if(row.children[0].textContent.trim().slice(0,2)!==actualDay.slice(0,2)) throw new Error('Weekdag past niet bij gekozen schooljaar: '+date);
    dates.push(date);
    const cell=row.children[1];if(!cell) throw new Error('Kalendercel ontbreekt.');
    const lines=splitLines(cell);
    // Verify every visible source character survived the line conversion.
    if(text(lines.map(x=>x.title).join('')).replace(/\s/g,'')!==text(cell.textContent).replace(/\s/g,'')) throw new Error('Tekstverlies op '+date);
    items.push(...lines.map(line=>({date,title:line.title,html:line.html})));
    const card=row.closest('table').parentElement;
    const header=card.firstElementChild;
    const gradient=header?.style?.background || '';
    const season=header?.querySelectorAll('td')?.[1]?.textContent?.trim() || '';
    months[date.slice(0,7)]={season,gradient:/^linear-gradient\([a-z0-9#%.,()\s-]+\)$/i.test(gradient) ? gradient : ''};
    const focusNode=Array.from(card.children).find(x=>x.tagName==='DIV' && (x.getAttribute('style') || '').includes('border-bottom'));
    if(focusNode) focus[date.slice(0,7)]=text(focusNode.textContent);
  }
  const container=rows[0].closest('table').parentElement.parentElement;
  for(const child of container.children) {
    if(child.querySelector('table')) break;
    const lines=splitLines(child);
    for(const line of lines) {
      const {document:doc}=parseHTML('<div>'+line.html+'</div>'),anchors=Array.from(doc.querySelectorAll('a'));
      const copy=doc.firstElementChild.cloneNode(true);for(const a of copy.querySelectorAll('a')) a.remove();
      const label=text(copy.textContent).replace(/🔗/g,'').trim();
      for(const a of anchors) {
        const url=normalizeLink(a.getAttribute('href'));
        let description=label || text(a.textContent).replace(/🔗/g,'').trim() || 'Link';
        if(anchors.length>1) description+=' ('+(new URL(url).hostname.endsWith('smartschool.be') ? 'Smartschool':'document')+')';
        links.push({description,url});
      }
    }
  }
  const digest=createHash('sha256').update(source+'\n'+startYear).digest('hex');
  const now=new Date().toISOString();
  // Only the first source import is accepted. Replaying it never restores deleted records or edits.
  const guard='NOT EXISTS(SELECT 1 FROM import_batches)';
  const sql=[]; // Wrangler D1 file import supplies the transaction; explicit BEGIN is unsupported.
  for(const i of items) sql.push(`INSERT INTO calendar_items(date_local,title,source,display_html,created_at) SELECT ${quote(i.date)},${quote(i.title)},'legacy',${quote(i.html)},${quote(now)} WHERE ${guard};`);
  for(const l of links) sql.push(`INSERT INTO calendar_links(description,url,updated_at) SELECT ${quote(l.description)},${quote(l.url)},${quote(now)} WHERE ${guard};`);
  sql.push(`INSERT INTO calendar_settings(key,value) SELECT 'layout',${quote(JSON.stringify({dates:[...new Set(dates)].sort(),focus,months}))} WHERE ${guard};`);
  sql.push(`INSERT INTO import_batches(digest,created_at) SELECT ${quote(digest)},${quote(now)} WHERE ${guard};`);
  return {items,links,dates,focus,digest,sql:sql.join('\n')};
}
if(process.argv[1] && import.meta.url===pathToFileURL(process.argv[1]).href) {
  const [file,year,output]=process.argv.slice(2);
  if(!file || !output) throw new Error('Gebruik: node scripts/import-html.mjs bron.html startjaar private-import');
  const result=convert(readFileSync(file,'utf8'),Number(year));
  mkdirSync(output,{recursive:true});writeFileSync(output+'/import.sql',result.sql);
  writeFileSync(output+'/report.json',JSON.stringify({days:result.dates.length,items:result.items.length,links:result.links.map(x=>x.description),digest:result.digest},null,2));
  console.log(JSON.stringify({days:result.dates.length,items:result.items.length,links:result.links.length}));
}
