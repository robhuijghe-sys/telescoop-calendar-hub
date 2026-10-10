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
  -- Sanitized by scripts/import-html.mjs; never accepted by management APIs.
  display_html TEXT,
  created_at TEXT NOT NULL,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS items_visible_date ON calendar_items(deleted_at,date_local,start_time,id);
CREATE INDEX IF NOT EXISTS items_visible_id ON calendar_items(deleted_at,id);
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

CREATE TABLE IF NOT EXISTS calendar_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  description TEXT NOT NULL,
  url TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  deleted_at TEXT
);
CREATE INDEX IF NOT EXISTS links_visible ON calendar_links(deleted_at,id);
CREATE TRIGGER IF NOT EXISTS audit_link_insert AFTER INSERT ON calendar_links BEGIN
  INSERT INTO audit_log(actor,action,item_id,details,created_at)
  VALUES('beheerlink','link.created',NEW.id,json_object('description',NEW.description,'url',NEW.url),NEW.updated_at);
END;
CREATE TRIGGER IF NOT EXISTS audit_link_update AFTER UPDATE ON calendar_links BEGIN
  INSERT INTO audit_log(actor,action,item_id,details,created_at)
  VALUES('beheerlink',CASE WHEN NEW.deleted_at IS NOT NULL THEN 'link.deleted' ELSE 'link.updated' END,NEW.id,
    json_object('before_description',OLD.description,'before_url',OLD.url,'description',NEW.description,'url',NEW.url),NEW.updated_at);
END;
CREATE TABLE IF NOT EXISTS calendar_settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_batches (digest TEXT PRIMARY KEY,created_at TEXT NOT NULL);

CREATE UNIQUE INDEX IF NOT EXISTS links_visible_duplicate ON calendar_links(description COLLATE NOCASE,url) WHERE deleted_at IS NULL;
-- Changes invalidate public render caches atomically, including imports and SQL maintenance.
CREATE TABLE IF NOT EXISTS calendar_state (id INTEGER PRIMARY KEY CHECK(id=1),revision INTEGER NOT NULL DEFAULT 0,epoch TEXT NOT NULL);
INSERT OR IGNORE INTO calendar_state(id,epoch) VALUES(1,lower(hex(randomblob(16))));
CREATE TRIGGER IF NOT EXISTS revision_calendar_items_insert AFTER INSERT ON calendar_items BEGIN UPDATE calendar_state SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER IF NOT EXISTS revision_calendar_items_update AFTER UPDATE ON calendar_items BEGIN UPDATE calendar_state SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER IF NOT EXISTS revision_calendar_items_delete AFTER DELETE ON calendar_items BEGIN UPDATE calendar_state SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER IF NOT EXISTS revision_calendar_links_insert AFTER INSERT ON calendar_links BEGIN UPDATE calendar_state SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER IF NOT EXISTS revision_calendar_links_update AFTER UPDATE ON calendar_links BEGIN UPDATE calendar_state SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER IF NOT EXISTS revision_calendar_links_delete AFTER DELETE ON calendar_links BEGIN UPDATE calendar_state SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER IF NOT EXISTS revision_calendar_settings_insert AFTER INSERT ON calendar_settings BEGIN UPDATE calendar_state SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER IF NOT EXISTS revision_calendar_settings_update AFTER UPDATE ON calendar_settings BEGIN UPDATE calendar_state SET revision=revision+1 WHERE id=1; END;
CREATE TRIGGER IF NOT EXISTS revision_calendar_settings_delete AFTER DELETE ON calendar_settings BEGIN UPDATE calendar_state SET revision=revision+1 WHERE id=1; END;
