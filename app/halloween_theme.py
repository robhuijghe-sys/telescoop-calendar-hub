"""A display-only Halloween costume, limited to 30–31 October 2026 in Brussels."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Brussels')
START = datetime(2026, 10, 30, tzinfo=TZ)
END = datetime(2026, 11, 1, tzinfo=TZ)
STATIC = Path(__file__).parent / 'static'
CSS = (STATIC / 'halloween-2026.css').read_text()
SCRIPT = (STATIC / 'halloween-2026.js').read_text()


def halloween_active(now=None):
    return START <= (now if now is not None else datetime.now(TZ)).astimezone(TZ) < END


def halloween_document(document, now=None):
    # Keep normal responses byte-for-byte identical outside the one-off window.
    # No calendar records, editor fields or stored names are ever rewritten.
    if not halloween_active(now):
        return document
    hero = '''<section id="halloween-hero" aria-label="Halloweeneditie">
      <img class="halloween-art" src="/calendar-editor/halloween-school-2026.webp" alt="" width="1536" height="512" fetchpriority="high">
      <div class="halloween-copy"><p class="halloween-kicker">30 &amp; 31 oktober · Halloweeneditie</p>
      <h1>De Telescoop<br><span>spookt!</span></h1>
      <p>De planning is behekst. Het team ook.</p></div>
      <button type="button" id="halloween-motion" aria-pressed="false">Spookjes pauzeren</button>
    </section>'''
    decorations = '''<div id="halloween-decorations" aria-hidden="true">
      <span class="hw-float hw-ghost">👻</span><span class="hw-float hw-bat">🦇</span>
      <span class="hw-float hw-pumpkin">🎃</span><span class="hw-float hw-star">✦</span>
      <div class="halloween-cat"><svg viewBox="0 0 150 90" focusable="false" aria-hidden="true">
        <g fill="#100d18" stroke="#b78dd7" stroke-width="1.2" stroke-linejoin="round">
          <path class="hw-cat-tail" d="M46 49C19 51 8 27 17 12C23 3 32 9 26 17C17 30 33 39 49 37" stroke-width="2"/>
          <path class="hw-cat-leg hw-cat-leg-a" d="M50 51L43 77Q43 83 56 81L62 52Z"/>
          <path class="hw-cat-leg hw-cat-leg-b" d="M88 51L87 78Q88 83 101 81L102 50Z"/>
          <ellipse cx="73" cy="47" rx="39" ry="23"/>
          <path class="hw-cat-leg hw-cat-leg-c" d="M42 51L54 78Q55 83 67 80L62 51Z"/>
          <path class="hw-cat-leg hw-cat-leg-d" d="M88 52L104 79Q106 83 117 79L106 50Z"/>
          <path d="M95 39L94 11L109 20L126 10L129 34Q139 39 130 51Q112 65 96 51Z"/>
        </g>
        <g fill="#ffce50"><ellipse cx="106" cy="36" rx="4.3" ry="3.2"/><ellipse cx="121" cy="34" rx="4.3" ry="3.2"/></g>
        <g stroke="#100d18" stroke-width="2"><path d="M107 33V39M122 31V37"/></g>
        <path d="M114 43L118 42L116 46Z" fill="#e7a4a8"/>
        <path d="M103 44L87 40M103 48L85 48M127 42L143 36M128 46L146 44" stroke="#dfc4e9" stroke-width="1.2"/>
      </svg></div>
    </div>'''
    document = document.replace('<html lang="nl">', '<html lang="nl" class="halloween-2026">', 1)
    document = document.replace('</head>', '<style id="halloween-style">' + CSS + '</style></head>', 1)
    document = document.replace('<div class="links">', hero + '<div class="links">', 1)
    return document.replace('</body>', decorations + '<script id="halloween-script">' + SCRIPT + '</script></body>', 1)
