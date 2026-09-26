"""Apply an authorized private HTML export once, preserving public edits."""
import base64
import gzip
import json
import os
import re
import sqlite3
from datetime import date
from pathlib import Path
import app.main as core


def apply_latest_source(original_snapshot, split_lines, clean_html, plain, safe_url):
    encoded = os.getenv('CALENDAR_SOURCE_GZ_B64', '')
    if not encoded:
        return
    seed = json.loads(gzip.decompress(base64.b64decode(encoded)))
    digest = seed['digest']
    if not re.fullmatch('[a-f0-9]{64}', digest):
        raise ValueError('Invalid source digest')
    for entry in seed['layout']['entries']:
        date.fromisoformat(entry['date'])
        entry['html'] = ''
    incoming = []
    for row in seed['lines']:
        date.fromisoformat(row['date_local'])
        body = clean_html(row['body_html'])
        incoming.append((row['date_local'], body, row['title']))
    links = [(r['description'], safe_url(r['url'])) for r in seed['links']]
    con = core.db()
    try:
        previous = con.execute("SELECT value FROM settings WHERE key='editor_source_digest'").fetchone()
        if previous and previous[0] == digest:
            return
        backup_path = str(core.DB_PATH) + '.before-source-' + digest[:12] + '.bak'
        if not Path(backup_path).exists():
            backup = sqlite3.connect(backup_path)
            con.backup(backup)
            backup.close()
        con.executescript('''CREATE TABLE IF NOT EXISTS editor_source_rows(id INTEGER PRIMARY KEY,date_local TEXT,body_html TEXT,title TEXT);
          CREATE TABLE IF NOT EXISTS editor_source_links(id INTEGER PRIMARY KEY,description TEXT,url TEXT);''')
        con.execute('BEGIN IMMEDIATE')
        if not previous:
            ident = 0
            for entry in original_snapshot().get('entries', []):
                for body in split_lines(entry.get('html', '')):
                    ident += 1
                    con.execute('INSERT OR IGNORE INTO editor_source_rows VALUES(?,?,?,?)', (ident, entry['date'], body, plain(body)))
            old_seed = os.getenv('CALENDAR_LINKS_GZ_B64', '')
            if old_seed:
                old_links = json.loads(gzip.decompress(base64.b64decode(old_seed)))
                for ident, row in enumerate(old_links, 1):
                    con.execute('INSERT OR IGNORE INTO editor_source_links VALUES(?,?,?)', (ident, row['description'], safe_url(row['url'])))
        suppressed = set()
        for source in con.execute('SELECT * FROM editor_source_rows').fetchall():
            current = con.execute('SELECT * FROM editor_lines WHERE id=?', (source['id'],)).fetchone()
            if current and current['version'] == 1 and not current['deleted'] and all(current[k] == source[k] for k in ('date_local', 'body_html', 'title')):
                con.execute('UPDATE editor_lines SET deleted=1,version=version+1 WHERE id=?', (source['id'],))
                con.execute('DELETE FROM editor_source_rows WHERE id=?', (source['id'],))
            else:
                suppressed.add((source['date_local'], source['title']))
        hidden = {r[0] for r in con.execute('SELECT date_local FROM editor_days WHERE hidden=1')}
        for day, body, title in incoming:
            if day in hidden or (day, title) in suppressed:
                continue
            if con.execute('SELECT 1 FROM editor_lines WHERE deleted=0 AND date_local=? AND title=?', (day, title)).fetchone():
                continue
            ident = con.execute('INSERT INTO editor_lines(date_local,body_html,title) VALUES(?,?,?)', (day, body, title)).lastrowid
            con.execute('INSERT INTO editor_source_rows VALUES(?,?,?,?)', (ident, day, body, title))
        suppressed_links = set()
        for source in con.execute('SELECT * FROM editor_source_links').fetchall():
            current = con.execute('SELECT * FROM editor_links WHERE id=?', (source['id'],)).fetchone()
            if current and current['version'] == 1 and not current['deleted'] and all(current[k] == source[k] for k in ('description', 'url')):
                con.execute('UPDATE editor_links SET deleted=1,version=version+1 WHERE id=?', (source['id'],))
                con.execute('DELETE FROM editor_source_links WHERE id=?', (source['id'],))
            else:
                suppressed_links.add(source['description'])
        for description, url in links:
            if description in suppressed_links or con.execute('SELECT 1 FROM editor_links WHERE deleted=0 AND description=? AND url=?', (description, url)).fetchone():
                continue
            ident = con.execute('INSERT INTO editor_links(description,url) VALUES(?,?)', (description, url)).lastrowid
            con.execute('INSERT INTO editor_source_links VALUES(?,?,?)', (ident, description, url))
        for key, value in [('editor_layout', json.dumps(seed['layout'], ensure_ascii=False)), ('editor_source_digest', digest)]:
            con.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
        con.execute('INSERT INTO audit_log(actor_email,action,payload,created_at) VALUES(?,?,?,?)', ('source-import', 'calendar.source_imported', json.dumps({'digest': digest, 'lines': len(incoming), 'days': len(seed['layout']['entries'])}), core.now_iso()))
        con.commit()
    finally:
        con.close()
