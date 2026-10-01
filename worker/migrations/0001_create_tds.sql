CREATE TABLE IF NOT EXISTS tds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    level INTEGER NOT NULL,
    exp REAL NOT NULL,
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tds_user_timestamp
ON tds (user_id, timestamp);
