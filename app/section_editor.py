"""Save the five day panels atomically while retaining untouched records."""
from difflib import SequenceMatcher
from urllib.parse import urlencode

from fastapi.responses import RedirectResponse

from app.day_cards import MOMENT, PANEL_LABELS, PANEL_TYPES, TYPE_PANELS, render_calendar


def save_sections(s, date, version, values, error_page, signature):
    cleaned={key:s.without_bold(s.clean_html(value or '')) for key,value in values.items()}
    if any(value is None for value in values.values()):
        return error_page(date,version,cleaned,'Niet alle vakken zijn ontvangen. Open de dag opnieuw.',400)
    if sum(len(value) for value in values.values())>100000 or sum(len(value) for value in cleaned.values())>100000:
        return error_page(date,version,cleaned,'Gebruik maximaal 100.000 tekens voor de hele dag.',400)
    if not any(s.plain(value) for value in cleaned.values()):
        return error_page(date,version,cleaned,'Vul minstens één vak in. Gebruik “Dag wissen” om de volledige dag te verwijderen.',400)
    submitted={key:s.split_lines(cleaned[key]) for key in PANEL_LABELS}
    con=s.core.db()
    try:
        con.execute('BEGIN IMMEDIATE')
        before,current,_=s.day_records(con,date)
        if current!=version:
            return error_page(date,version,cleaned,'Deze dag is ondertussen gewijzigd. Je eigen tekst blijft in de vakken staan. Open de dag opnieuw om de nieuwste versie te bewerken.',409,True)
        data=render_calendar(s,hide_past=False,dates=[date],cards_only=True,connection=con,editor_data=True)
        original=data['sections'].get(date,{key:[] for key in PANEL_LABELS})
        unchanged={key for key in PANEL_LABELS if list(map(signature,submitted[key]))==[signature(item['rich']) for item in original[key]]}
        if len(unchanged)==len(PANEL_LABELS):
            return RedirectResponse('/kalender-wijzigen?'+urlencode({'date':date,'saved':1}),303)
        remaining={key:list(fragments) for key,fragments in submitted.items()}
        by_record={}
        for key,items in original.items():
            for item in items:by_record.setdefault(item['record'],[]).append((key,item))
        kept=set()

        def consume(entries):
            indices={key:[] for key in PANEL_LABELS}
            for key,item in entries:
                found=next((i for i,fragment in enumerate(remaining[key])
                            if i not in indices[key] and signature(fragment)==signature(item['rich'])),None)
                if found is None:return False
                indices[key].append(found)
            for key,positions in indices.items():
                for position in sorted(positions,reverse=True):remaining[key].pop(position)
            return True

        for record,entries in by_record.items():
            if record[0]=='event' or all(key in unchanged for key,_ in entries):
                if consume(entries):kept.add(record)
        for row in before['basis']:
            if ('basis',row['id']) not in kept:
                con.execute('UPDATE editor_lines SET deleted=1,version=version+1 WHERE id=?',(row['id'],))
        for event in before['events']:
            if ('event',event['id']) not in kept:
                con.execute("UPDATE events SET visible_in_embed=0,status='deleted',updated_at=? WHERE id=?",(s.core.now_iso(),event['id']))
        candidates=[(key,item) for key,items in original.items() for item in items if item['record'] not in kept]
        for key,fragments in remaining.items():
            bundles=[]
            for fragment in fragments:
                text=s.plain(fragment)
                exact=[i for i,(old_key,item) in enumerate(candidates) if s.plain(item['rich'])==text]
                match=next((i for i in exact if candidates[i][0]==key),exact[0] if exact else None)
                if match is None and candidates:
                    score,index=max((SequenceMatcher(None,text,s.plain(item['rich']),autojunk=False).ratio(),i) for i,(_,item) in enumerate(candidates))
                    if score>=.65:match=index
                previous=candidates.pop(match)[1] if match is not None else None
                category=previous['type'] if previous and TYPE_PANELS.get(previous['type'])==key else PANEL_TYPES[key]
                moment=MOMENT.match(text)
                whole_day=(int(moment[1].lower() in ('dag','hele dag')) if moment else int(previous['whole_day']) if previous else 0)
                source=previous['record'] if previous else ('new',key)
                group=(source,category,whole_day)
                if bundles and bundles[-1][0]==group:bundles[-1][1].append(fragment)
                else:bundles.append((group,[fragment]))
            for (_,category,whole_day),fragments in bundles:
                rich='<br/>'.join(fragments)
                con.execute('INSERT INTO editor_lines(date_local,body_html,title,custom_format,activity_type,whole_day) VALUES(?,?,?,?,?,?)',
                            (date,rich,s.plain(rich),int(s.has_custom_color(rich)),category,whole_day))
        con.execute('DELETE FROM editor_days WHERE date_local=?',(date,))
        s.audit(con,'calendar.day_changed',{'date':date,'before':before,'sections':cleaned})
        con.commit()
    finally:
        con.close()
    return RedirectResponse('/kalender-wijzigen?'+urlencode({'date':date,'saved':1}),303)
