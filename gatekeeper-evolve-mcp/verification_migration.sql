-- Migration: Add verification_results table (schema version 2 -> 3)
-- Applied automatically by server.py if the table does not exist.

CREATE TABLE IF NOT EXISTS verification_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    tool TEXT NOT NULL,
    status TEXT NOT NULL,
    result_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_verification_results_session_id ON verification_results(session_id);
CREATE INDEX IF NOT EXISTS idx_verification_results_tool ON verification_results(tool);
CREATE INDEX IF NOT EXISTS idx_verification_results_status ON verification_results(status);
CREATE INDEX IF NOT EXISTS idx_verification_results_created_at ON verification_results(created_at);

-- Update schema version
INSERT OR REPLACE INTO schema_version (version, applied_at, description)
VALUES (3, datetime('now'), 'Added verification_results table for formal verification tools');
