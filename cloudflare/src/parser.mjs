// Deterministic Dutch parsing: no AI service, usage credits, or network call.
const months = ['januari','februari','maart','april','mei','juni','juli','augustus','september','oktober','november','december'];
const monthPattern = months.join('|');

export function categoryFor(text) {
  const s = ` ${text.toLowerCase()} `;
  if (/afwezig|afw\.|afgelast|annul|gesloten|geen opvang|waarschuwing/.test(s)) return 'waarschuwing';
  if (/ouders?|oudercontact|ouderavond|infomoment/.test(s)) return 'ouders';
  if (/uitstap|gwp|bosklas|zeeklas|schoolreis|museum|zwemmen|theater|toneel/.test(s)) return 'uitstap';
  if (/personeel|team|leerkracht|zorgoverleg|vakgroep|directie|vergadering|overleg|studiedag/.test(s)) return 'personeel';
  return 'algemeen';
}

function validDay(y, m, d) {
  const date = new Date(Date.UTC(y, m - 1, d));
  return date.getUTCFullYear() === y && date.getUTCMonth() === m - 1 && date.getUTCDate() === d;
}

export function parseInstruction(input, today = new Date()) {
  const raw = String(input ?? '').trim();
  const lower = raw.toLowerCase();
  const now = new Intl.DateTimeFormat('en-CA', {timeZone:'Europe/Brussels', year:'numeric',month:'2-digit',day:'2-digit'}).format(today);
  const [thisYear,thisMonth,thisDay] = now.split('-').map(Number);
  let date = '', dateText = '', dateStart=-1, assumptions = [], missing = [];
  const deleting = isDeleteCommand(raw);
  const iso = lower.match(/\b(\d{4})-(\d{2})-(\d{2})\b/);
  const written = lower.match(new RegExp(`\\b(\\d{1,2})\\s+(${monthPattern})(?:\\s+(\\d{4}))?\\b`, 'i'));
  const numeric = lower.match(/\b(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{2,4}))?\b/);
  if (iso) {
    if (validDay(Number(iso[1]),Number(iso[2]),Number(iso[3]))) date=iso[0];
    dateText=iso[0];
  } else if (written || numeric) {
    const day = Number((written || numeric)[1]);
    const month = written ? months.indexOf(written[2].toLowerCase()) + 1 : Number(numeric[2]);
    let year = Number((written || numeric)[3] || thisYear);
    if (year < 100) year += 2000;
    if (!(written || numeric)[3] && !deleting && (month < thisMonth || (month === thisMonth && day < thisDay))) {
      year++;
    }
    if (!(written || numeric)[3]) assumptions.push(`Jaartal geïnterpreteerd als ${year}`);
    if (validDay(year,month,day)) date = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    dateText = (written || numeric)[0];
  } else if (/^(?:(?:voeg(?: toe)?|plan|zet|verwijder|wis|haal)\s+)?(?:vandaag|morgen)\b/.test(lower) || /(?<!van )\b(?:vandaag|morgen)(?:\s+(?:toe|weg))?[.!]?$/i.test(lower)) {
    const relative=lower.match(/^(?:(?:voeg(?: toe)?|plan|zet|verwijder|wis|haal)\s+)?(vandaag|morgen)\b/) || lower.match(/(?<!van )\b(vandaag|morgen)(?:\s+(?:toe|weg))?[.!]?$/);
    dateText=relative[1];dateStart=relative.index+relative[0].indexOf(dateText);
    const d = new Date(Date.UTC(thisYear,thisMonth-1,thisDay + (dateText === 'morgen' ? 1 : 0)));
    date = d.toISOString().slice(0,10);
  }
  // Capture invalid clocks too: 15.99 must never silently become 15:00.
  const range=raw.match(/(?<![\d.:])\b(?:van\s+)?(\d{1,2})\s*(?:tot|-|–)\s*(\d{1,2})\s*(?:uur|u)\b/i);
  const times = range ? [range[1],range[2]].map(hour=>({value:Number(hour)<24 ? hour.padStart(2,'0')+':00' : ''})) : [...raw.matchAll(/(?<![\d.:])\b(\d{1,2})(?:[:.](\d{1,2})(?:\s*u(?:ur)?)?|\s*u(?:ur)?(?:\s*(\d{1,2}))?)(?!\w)/gi)]
    .map(match => {const minutes=match[2] || match[3] || '00';return {raw:match[0],value:Number(match[1])<24 && Number(minutes)<60 && minutes.length===2 ? `${match[1].padStart(2,'0')}:${minutes}` : ''};});
  if (times.some(t=>!t.value) || times.length>2) missing.push('geldige tijd');
  let title = (dateStart>=0 ? raw.slice(0,dateStart)+'⟦datum⟧'+raw.slice(dateStart+dateText.length) : raw).replace(/^(?:voeg(?:\s+toe)?|plan|zet|verwijder|wis|haal)\b\s*/i,'')
    .replace(/\s+(?:toe|weg)\s*[.!]?$/i,'').replace(/\s+(?:in de kalender|in de agenda|op de kalender)\s*$/i,'');
  if (dateText && dateStart<0) title=title.replace(new RegExp(dateText.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'i'),'⟦datum⟧');
  if(range) title=title.replace(range[0],'⟦tijd⟧');
  else for (const time of times) title=title.replace(time.raw,'⟦tijd⟧');
  title=title.replace(/\b(?:(?:op|voor)\s+)?(?:(?:maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag|ma|di|woe?|do|vr|vrij|za|zo)\s+)?(?=⟦datum⟧)/gi,'')
    .replace(/\b(?:om|van|tot)\s+(?=⟦tijd⟧)/gi,'').replace(/⟦(?:datum|tijd)⟧/g,' ')
    .replace(/\s+/g,' ').trim().replace(/^[,.;:\-\s]+|[,.;:\-\s]+$/g,'');
  if (title) title = title[0].toUpperCase() + title.slice(1);
  if(!date) missing.push('datum');
  if(!title) missing.push('titel');
  if(times[1]?.value && times[0]?.value && times[1].value<=times[0].value) missing.push('eindtijd na begintijd');
  return {title,date,start_time:times[0]?.value || '',end_time:times[1]?.value || '',
    category:categoryFor(raw),missing,assumptions,action:deleting?'delete':'create'};
}

export function isDeleteCommand(text) {
  return /^\s*(?:verwijder|wis)\b/i.test(text) || /^\s*haal\b.+\bweg\s*[.!]?\s*$/i.test(text);
}
