"""Shared De Telescoop palette, based on the school's navy, green and yellow logo."""

CSS = '''
:root{--school-navy:#232563;--school-green:#8bb43f;--school-green-ink:#48691e;--school-yellow:#f7bf23;--bg:#f6f8f1;--card:#fff;--ink:#252a40;--muted:#5c6453;--line:#d8e1c9;--accent:var(--school-navy);--soft:#f0f5e6}
html,body{background:var(--bg);color:var(--ink)}
header{background:var(--school-navy);border-bottom:3px solid var(--school-yellow)}
.card,.month-card{border-color:var(--line);box-shadow:0 6px 22px rgba(35,37,99,.05)}
button,.btn{background:var(--school-navy);color:#fff}
button:hover,.btn:hover{background:#34377a}
.btn.alt{background:var(--soft);color:var(--school-green-ink)}
.btn.alt:hover{background:#e2ebd1}
input,textarea,select,.editbox,.editor-tools{border-color:var(--line)}
.editor-tools{background:var(--soft)}
.editor-tools button[aria-pressed=true]{background:var(--school-green-ink)}
.editbox:empty:before,.muted{color:var(--muted)}
input:focus,textarea:focus,select:focus,button:focus-visible,a:focus-visible,[contenteditable]:focus{outline:3px solid var(--school-yellow);outline-offset:2px}
.ok{background:var(--soft);border-color:var(--school-green)}
.warn,.day-error{background:#fff9e5;border-color:var(--school-yellow)}
.danger{background:#fff;border:1px solid #8a2f2f;color:#8a2f2f}
.danger:hover{background:#fff0ed;color:#762525}
.day-dialog{border-color:var(--line);color:var(--ink)}
.day-dialog::backdrop{background:rgba(35,37,99,.55)}
.quick,.quick a{color:var(--school-navy)}.quick a{border-bottom-color:var(--school-green)}
.month-head{background:var(--school-navy)!important;border-bottom:3px solid var(--school-yellow)}
.season{background:var(--soft);border-color:var(--school-green);color:var(--school-green-ink)}
.focus{background:var(--soft);color:var(--school-green-ink);border-color:var(--line)}
.focus .dot{background:var(--school-green)!important}
.date-cell,.mobile-date{background:var(--soft);color:var(--school-navy)}
.date-cell,.event-cell,.mobile-day{border-bottom-color:var(--line)}
.event-cell,.mobile-events{color:var(--ink)}
'''


def themed_document(document):
    return document.replace('</head>', '<style id="school-theme">' + CSS + '</style></head>', 1)
