-- Phase 2 initial schema.
-- Forward-only migrations. Tracked by the _migrations table.

CREATE TABLE _migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE threads (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL DEFAULT '',
    snippet TEXT NOT NULL DEFAULT '',
    last_message_at TEXT NOT NULL,
    message_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    history_id TEXT NOT NULL DEFAULT '',
    from_addr TEXT NOT NULL DEFAULT '',
    from_name TEXT NOT NULL DEFAULT '',
    to_addrs TEXT NOT NULL DEFAULT '[]',
    cc_addrs TEXT NOT NULL DEFAULT '[]',
    subject TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    snippet TEXT NOT NULL DEFAULT '',
    labels TEXT NOT NULL DEFAULT '[]',
    is_unread INTEGER NOT NULL DEFAULT 0,
    is_sent INTEGER NOT NULL DEFAULT 0,
    body_text TEXT,
    fetched_body_at TEXT
);

CREATE INDEX idx_messages_thread_id ON messages(thread_id);
CREATE INDEX idx_messages_date ON messages(date DESC);
CREATE INDEX idx_messages_unread ON messages(is_unread) WHERE is_unread = 1;
CREATE INDEX idx_messages_sent ON messages(is_sent) WHERE is_sent = 1;
CREATE INDEX idx_messages_from_addr ON messages(from_addr);

CREATE VIRTUAL TABLE messages_fts USING fts5(
    subject,
    snippet,
    from_name,
    from_addr,
    body_text,
    content='messages',
    content_rowid='rowid'
);

CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, subject, snippet, from_name, from_addr, body_text)
    VALUES (new.rowid, new.subject, new.snippet, new.from_name, new.from_addr, COALESCE(new.body_text, ''));
END;

CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, subject, snippet, from_name, from_addr, body_text)
    VALUES ('delete', old.rowid, old.subject, old.snippet, old.from_name, old.from_addr, COALESCE(old.body_text, ''));
END;

CREATE TRIGGER messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, subject, snippet, from_name, from_addr, body_text)
    VALUES ('delete', old.rowid, old.subject, old.snippet, old.from_name, old.from_addr, COALESCE(old.body_text, ''));
    INSERT INTO messages_fts(rowid, subject, snippet, from_name, from_addr, body_text)
    VALUES (new.rowid, new.subject, new.snippet, new.from_name, new.from_addr, COALESCE(new.body_text, ''));
END;

CREATE TABLE sync_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    account_email TEXT,
    last_history_id TEXT,
    last_full_sync_at TEXT,
    last_incremental_sync_at TEXT
);

INSERT INTO sync_state (id) VALUES (1);
