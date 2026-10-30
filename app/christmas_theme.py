"""Display-only Christmas edition, 10–25 December 2026 in Brussels."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Europe/Brussels')
START = datetime(2026, 12, 10, tzinfo=TZ)
END = datetime(2026, 12, 26, tzinfo=TZ)
STATIC = Path(__file__).parent / 'static'
CSS = (STATIC / 'christmas-2026.css').read_text()
SCRIPT = (STATIC / 'christmas-2026.js').read_text()

# An already open normal calendar also picks up the theme at Belgian midnight.
# A minute-sized timer avoids browser timeout limits for a date weeks away.
START_WATCH = '''<script id="christmas-start-watch">
(() => {
  const start = Date.parse('2026-12-10T00:00:00+01:00');
  const end = Date.parse('2026-12-26T00:00:00+01:00');
  let timer;
  function check() {
    clearTimeout(timer);
    const now = Date.now();
    if (now >= start) {
      document.removeEventListener('visibilitychange', check);
      window.removeEventListener('pageshow', check);
      document.getElementById('christmas-start-watch')?.remove();
      if (now < end) window.location.reload();
      return;
    }
    timer = setTimeout(check, Math.min(start - now, 60000));
  }
  document.addEventListener('visibilitychange', check);
  window.addEventListener('pageshow', check);
  check();
})();
</script>'''


def christmas_active(now=None):
    return START <= (now if now is not None else datetime.now(TZ)).astimezone(TZ) < END


def christmas_document(document, now=None):
    local = (now if now is not None else datetime.now(TZ)).astimezone(TZ)
    if local < START:
        return document.replace('</body>', START_WATCH + '</body>', 1)
    if local >= END:
        return document
    # Only presentation changes: stored names, calendar data and editors stay intact.
    hero = '''<section id="christmas-hero" aria-label="Kersteditie">
      <img class="christmas-art" src="/calendar-editor/christmas-school-2026.webp" alt="" width="1536" height="512" fetchpriority="high">
      <div class="christmas-copy"><p class="christmas-kicker">10 – 25 december · Kersteditie</p>
      <h1>De Telescoop<br><span>fonkelt!</span></h1>
      <p>Ho ho ho… zelfs de planning heeft een kerstmuts.</p></div>
      <button type="button" id="christmas-motion" aria-pressed="false">Kerstpret pauzeren</button>
    </section>'''
    decorations = '''<div id="christmas-decorations" aria-hidden="true">
      <span class="xm-snow xm-snow-a">❄</span><span class="xm-snow xm-snow-b">❅</span>
      <span class="xm-snow xm-snow-c">❄</span><span class="xm-snow xm-snow-d">❅</span>
      <span class="xm-star xm-star-a">✦</span><span class="xm-star xm-star-b">✧</span>
      <div class="christmas-rudolph"><svg viewBox="0 0 180 135" focusable="false" aria-hidden="true">
        <g stroke="#f6d9a4" stroke-width="1.2" stroke-linejoin="round">
          <path class="xm-tail" d="M42 67Q23 52 20 65Q24 76 44 78" fill="#a45e30"/>
          <path class="xm-leg xm-leg-a" d="M54 77L44 118L55 119L69 79" fill="#6e3d23"/>
          <path class="xm-leg xm-leg-b" d="M101 79L99 119L110 119L117 80" fill="#6e3d23"/>
          <ellipse cx="78" cy="75" rx="42" ry="27" fill="#ac6737"/>
          <ellipse cx="76" cy="87" rx="26" ry="12" fill="#dca46a" stroke="none"/>
          <path class="xm-leg xm-leg-c" d="M46 77L60 120L71 120L62 78" fill="#a45e30"/>
          <path class="xm-leg xm-leg-d" d="M97 80L116 119L128 119L112 72" fill="#a45e30"/>
          <path d="M97 71L111 33L132 38L126 78Q113 94 97 71" fill="#ac6737"/>
          <path d="M114 36Q96 17 94 28Q96 39 116 44M131 35Q150 18 153 30Q147 42 133 43" fill="#ac6737"/>
          <path d="M117 37L112 15L100 7M112 16L118 5M128 35L135 14L148 5M135 14L132 3" fill="none" stroke="#d7ad75" stroke-width="4.5" stroke-linecap="round"/>
          <path d="M109 39Q110 27 130 30Q144 32 147 48L157 53Q160 69 144 72L121 67Q108 59 109 39" fill="#b77543"/>
          <ellipse cx="143" cy="60" rx="15" ry="11" fill="#e5b782" stroke="none"/>
          <path d="M102 62Q115 70 130 66L128 76Q113 78 100 71Z" fill="#ad233c" stroke="#ffc77a"/>
          <path class="xm-scarf" d="M104 68L81 64L74 80L88 79L110 73Z" fill="#bd2d48" stroke="#ffc77a"/>
        </g>
        <ellipse cx="133" cy="44" rx="3.5" ry="4.8" fill="#251813"/><circle cx="134" cy="42.5" r="1.2" fill="#fff"/>
        <path d="M146 66Q141 71 137 65" fill="none" stroke="#643521" stroke-width="1.6" stroke-linecap="round"/>
        <circle class="xm-nose-glow" cx="157" cy="54" r="16" fill="#ff6c65" opacity=".2"/>
        <circle cx="157" cy="54" r="8" fill="#ef334c" stroke="#ffc8a2" stroke-width="1.3"/>
        <ellipse cx="155" cy="51" rx="2.5" ry="1.7" fill="#fff1d1"/>
        <circle cx="119" cy="75" r="4" fill="#ffd57e"/><path d="M117 76H121" stroke="#967230"/>
      </svg></div>
    </div>'''
    document = document.replace('<html lang="nl">', '<html lang="nl" class="christmas-2026">', 1)
    document = document.replace('</head>', '<style id="christmas-style">' + CSS + '</style></head>', 1)
    document = document.replace('<div class="links">', hero + '<div class="links">', 1)
    return document.replace('</body>', decorations + '<script id="christmas-script">' + SCRIPT + '</script></body>', 1)
