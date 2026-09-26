"""Consistent outing labels without inventing missing times or class groups."""
import re
from datetime import datetime
from fastapi import HTTPException


def outing_label(moment, group, location, start='', end=''):
    if moment == 'uren':
        try:
            a, b = datetime.strptime(start, '%H:%M'), datetime.strptime(end, '%H:%M')
            if b <= a:
                raise ValueError()
            moment = a.strftime('%H:%M') + ' tot ' + b.strftime('%H:%M')
        except ValueError:
            raise HTTPException(400, 'Vul voor de uitstap een geldig begin- en einduur in.')
    elif moment not in ('VM', 'NM', 'hele dag'):
        raise HTTPException(400, 'Kies VM, NM, hele dag of een begin- en einduur.')
    group, location = group.strip(), location.strip()
    if not group or not location:
        raise HTTPException(400, 'Vul de klasgroep en de locatie van de uitstap in.')
    location = re.sub(r'^(?:uitstap\s+)?naar\s+|^uitstap\s+', '', location, flags=re.I).strip()
    if not location or len(group) > 100 or len(location) > 700:
        raise HTTPException(400, 'Controleer de klasgroep en de locatie.')
    return f'{moment}, {group.upper()}, {location}'


def bulk_outing(line):
    parts = re.split(r':\s+|\s+-\s+|,\s*', line, maxsplit=2)
    if len(parts) != 3:
        raise HTTPException(400, 'Gebruik voor uitstappen: VM/NM/hele dag of beginuur tot einduur, klas, locatie uitstap.')
    moment, group, location = [p.strip() for p in parts]
    moment = {'vm':'VM','nm':'NM','voormiddag':'VM','namiddag':'NM','hele dag':'hele dag'}.get(moment.lower(), moment)
    match = re.fullmatch(r'(\d{1,2})[u:.h](\d{2})\s*(?:tot|-)\s*(\d{1,2})[u:.h](\d{2})', moment)
    if match:
        a,b,c,d = match.groups()
        return outing_label('uren',group,location,f'{int(a):02d}:{b}',f'{int(c):02d}:{d}')
    return outing_label(moment,group,location)
