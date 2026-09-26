-- A separate calendar item is one independently removable line, including imported HTML lines.
CREATE TABLE IF NOT EXISTS calendar_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date_local TEXT NOT NULL CHECK(length(date_local) = 10),
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  start_time TEXT NOT NULL DEFAULT '',
  end_time TEXT NOT NULL DEFAULT '',
  category TEXT NOT NULL DEFAULT 'algemeen',
  source TEXT NOT NULL DEFAULT 'manual' CHECK(source IN ('manual','legacy')),
  -- Reserved for the trusted, reviewed conversion of Rob's final HTML.
  display_html TEXT,
  created_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS items_visible_date ON calendar_items(deleted_at,date_local,id);
CREATE UNIQUE INDEX IF NOT EXISTS items_visible_duplicate ON calendar_items(date_local,title COLLATE NOCASE) WHERE deleted_at IS NULL AND source='manual';

CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  item_id INTEGER,
  details TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS audit_newest ON audit_log(id DESC);
CREATE TRIGGER IF NOT EXISTS audit_item_insert AFTER INSERT ON calendar_items BEGIN
  INSERT INTO audit_log(actor,action,item_id,details,created_at)
  VALUES(CASE WHEN NEW.source='legacy' THEN 'import' ELSE 'beheerlink' END,
         'item.created',NEW.id,json_object('date',NEW.date_local,'title',NEW.title),NEW.created_at);
END;
CREATE TRIGGER IF NOT EXISTS audit_item_delete AFTER UPDATE OF deleted_at ON calendar_items
WHEN OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL BEGIN
  INSERT INTO audit_log(actor,action,item_id,details,created_at)
  VALUES('beheerlink','item.deleted',NEW.id,json_object('date',NEW.date_local,'title',NEW.title),NEW.deleted_at);
END;
