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
  let date = '', dateText = '', assumptions = [];
  const written = lower.match(new RegExp(`\\b(\\d{1,2})\\s+(${monthPattern})(?:\\s+(\\d{4}))?\\b`, 'i'));
  const numeric = lower.match(/\b(\d{1,2})\s*[/-]\s*(\d{1,2})(?:\s*[/-]\s*(\d{2,4}))?\b/);
  if (written || numeric) {
    const day = Number((written || numeric)[1]);
    const month = written ? months.indexOf(written[2].toLowerCase()) + 1 : Number(numeric[2]);
    let year = Number((written || numeric)[3] || thisYear);
    if (year < 100) year += 2000;
    if (!(written || numeric)[3] && (month < thisMonth || (month === thisMonth && day < thisDay))) {
      year++;
      assumptions.push(`Jaartal geïnterpreteerd als ${year}`);
    }
    if (validDay(year,month,day)) date = `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
    dateText = (written || numeric)[0];
  } else if (/\b(vandaag|morgen)\b/.test(lower)) {
    dateText = lower.match(/\b(vandaag|morgen)\b/)[0];
    const d = new Date(Date.UTC(thisYear,thisMonth-1,thisDay + (dateText === 'morgen' ? 1 : 0)));
    date = d.toISOString().slice(0,10);
  }
  // Only explicit clock notation is a time; bare dates and class numbers are never mistaken for one.
  const times = [...raw.matchAll(/\b([01]?\d|2[0-3])\s*(?:[:.]|u)\s*([0-5]\d)?\b/gi)]
    .map(match => ({raw:match[0], value:`${match[1].padStart(2,'0')}:${(match[2] || '00').padStart(2,'0')}`}));
  let title = raw.replace(/^(?:voeg|plan|zet|verwijder|wis)\b\s*/i,'')
    .replace(/\b(?:toe|in de kalender|in de agenda|op de kalender)\b/gi,' ')
    .replace(/\b(?:maandag|dinsdag|woensdag|donderdag|vrijdag|zaterdag|zondag)\b/gi,' ');
  if (dateText) title = title.replace(new RegExp(dateText.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'i'),' ');
  for (const time of times) title = title.replace(time.raw,' ');
  title = title.replace(/\b(?:op|om|van|tot)\b/gi,' ').replace(/\s+/g,' ').trim().replace(/^[,.;:\-\s]+|[,.;:\-\s]+$/g,'');
  if (title) title = title[0].toUpperCase() + title.slice(1);
  return {title,date,start_time:times[0]?.value || '',end_time:times[1]?.value || '',
    category:categoryFor(raw),missing:date ? [] : ['datum'],assumptions};
}

export function isDeleteCommand(text) {
  return /^\s*(?:verwijder|wis)\b/i.test(text) || /^\s*haal\b.+\bweg\s*$/i.test(text);
}
