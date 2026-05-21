-- Phase 3a: store per-message classifications produced by the LLM.

CREATE TABLE message_classifications (
    message_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    confidence REAL NOT NULL,
    reason TEXT NOT NULL,
    classified_at TEXT NOT NULL,
    model TEXT NOT NULL,
    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE INDEX idx_classifications_category ON message_classifications(category);
CREATE INDEX idx_classifications_classified_at ON message_classifications(classified_at);
