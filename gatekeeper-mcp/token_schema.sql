-- SQLite Schema for Gatekeeper MCP Server
-- Version: 1
-- Description: Comprehensive schema supporting token management, agent signals,
--              evolution tracking, and usage metrics for the Gatekeeper verification system.

-- Enable foreign key constraints
PRAGMA foreign_keys = ON;

-- =============================================================================
-- Table: sessions
-- Purpose: Tracks active verification loops and session state
-- =============================================================================
CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,          -- format: gk_TIMESTAMP_RANDOMHEX
    task_id TEXT,                          -- optional, for plan mode
    iteration INTEGER NOT NULL DEFAULT 1,  -- current iteration number
    max_iterations INTEGER NOT NULL DEFAULT 10,  -- maximum allowed iterations
    project_dir TEXT NOT NULL,             -- absolute path to project directory
    test_command TEXT NOT NULL,            -- command to run tests (e.g., "pytest")
    verifier_model TEXT NOT NULL DEFAULT 'sonnet',  -- model for verification
    started_at TEXT NOT NULL,              -- ISO 8601 timestamp when session started
    ended_at TEXT,                         -- NULL if active, ISO 8601 if ended
    plan_mode INTEGER DEFAULT 0,           -- 0=false, 1=true (SQLite doesn't have BOOLEAN)
    active INTEGER NOT NULL DEFAULT 1      -- 0=inactive, 1=active
);

-- Indexes for sessions table
CREATE INDEX idx_sessions_task_id ON sessions(task_id);
CREATE INDEX idx_sessions_active ON sessions(active);

-- =============================================================================
-- Table: completion_tokens
-- Purpose: Stores GK_COMPLETE_*, TQG_PASS_*, and TPG_COMPLETE_* tokens for verification, test quality, and task plan quality
-- =============================================================================
CREATE TABLE completion_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    token_type TEXT NOT NULL,              -- 'GK_COMPLETE', 'TQG_PASS', or 'TPG_COMPLETE'
    token_value TEXT NOT NULL UNIQUE,      -- full token including prefix (128-bit entropy)
    task_id TEXT,                          -- optional, extracted from context
    created_at TEXT NOT NULL,              -- ISO 8601 timestamp
    validated INTEGER DEFAULT 0,           -- 0=pending, 1=validated
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Indexes for completion_tokens table
CREATE INDEX idx_completion_tokens_session_id ON completion_tokens(session_id);
CREATE INDEX idx_completion_tokens_token_value ON completion_tokens(token_value);
CREATE INDEX idx_completion_tokens_created_at ON completion_tokens(created_at);

-- =============================================================================
-- Table: phase_tokens
-- Purpose: Stores PVG_COMPLETE_* and PPG_COMPLETE_* tokens for phase verification and phase plan gates
-- =============================================================================
CREATE TABLE phase_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    token_value TEXT NOT NULL UNIQUE,      -- full token PVG_COMPLETE_[32hex] or PPG_COMPLETE_[32hex]
    phase_id INTEGER NOT NULL,             -- phase number (1, 2, 3, etc.)
    integration_check_passed INTEGER DEFAULT 0,  -- 0=failed, 1=passed
    created_at TEXT NOT NULL,              -- ISO 8601 timestamp
    validated INTEGER DEFAULT 0,           -- 0=pending, 1=validated
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Indexes for phase_tokens table
CREATE INDEX idx_phase_tokens_session_id ON phase_tokens(session_id);
CREATE INDEX idx_phase_tokens_phase_id ON phase_tokens(phase_id);
CREATE INDEX idx_phase_tokens_created_at ON phase_tokens(created_at);

-- =============================================================================
-- Table: agent_signals
-- Purpose: Stores agent-emitted signals for workflow coordination
-- Supported signal types: TESTS_WRITTEN, VERIFICATION_PASS, VERIFICATION_FAIL,
--                        ASSESSMENT_PASS, ASSESSMENT_FAIL, IMPLEMENTATION_READY,
--                        PHASE_ASSESSMENT_PASS, PHASE_VERIFICATION_PASS
-- =============================================================================
CREATE TABLE agent_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,                       -- optional FK to sessions (some signals may not have sessions)
    signal_type TEXT NOT NULL,             -- enum: TESTS_WRITTEN, VERIFICATION_PASS, etc.
    task_id TEXT,                          -- optional task identifier
    phase_id INTEGER,                      -- optional phase identifier
    agent_id TEXT,                         -- optional agent identifier
    context_json TEXT,                     -- JSON blob with additional context
    pending INTEGER NOT NULL DEFAULT 1,    -- 1=pending, 0=processed
    created_at TEXT NOT NULL,              -- ISO 8601 timestamp
    processed_at TEXT,                     -- NULL if pending, ISO 8601 if processed
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Indexes for agent_signals table
CREATE INDEX idx_agent_signals_session_id ON agent_signals(session_id);
CREATE INDEX idx_agent_signals_signal_type ON agent_signals(signal_type);
CREATE INDEX idx_agent_signals_pending ON agent_signals(pending);
CREATE INDEX idx_agent_signals_task_id ON agent_signals(task_id);
CREATE INDEX idx_agent_signals_created_at ON agent_signals(created_at);

-- =============================================================================
-- Table: evolution_attempts
-- Purpose: Stores evolution/retry attempt metrics for tracking task progress
-- =============================================================================
CREATE TABLE evolution_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,                       -- optional FK to sessions (can track attempts outside sessions)
    task_id TEXT NOT NULL,                 -- task identifier
    attempt_number INTEGER NOT NULL,       -- sequential attempt number
    metrics_json TEXT,                     -- JSON with tests_passed, coverage, errors, etc.
    outcome TEXT,                          -- 'SUCCESS', 'FAILURE', 'PARTIAL'
    created_at TEXT NOT NULL,              -- ISO 8601 timestamp
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    UNIQUE(task_id, attempt_number)        -- prevent duplicate attempt numbers per task
);

-- Indexes for evolution_attempts table
CREATE INDEX idx_evolution_attempts_session_id ON evolution_attempts(session_id);
CREATE INDEX idx_evolution_attempts_task_id ON evolution_attempts(task_id);
CREATE INDEX idx_evolution_attempts_created_at ON evolution_attempts(created_at);

-- =============================================================================
-- Table: usage_metrics
-- Purpose: Stores token usage and cost tracking per session for monitoring
-- =============================================================================
CREATE TABLE usage_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,              -- required FK to sessions
    tool_name TEXT NOT NULL,               -- MCP tool name (submit_token, record_signal, etc.)
    input_tokens INTEGER,                  -- number of input tokens
    output_tokens INTEGER,                 -- number of output tokens
    cost_estimate REAL,                    -- estimated cost in dollars
    created_at TEXT NOT NULL,              -- ISO 8601 timestamp
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

-- Indexes for usage_metrics table
CREATE INDEX idx_usage_metrics_session_id ON usage_metrics(session_id);
CREATE INDEX idx_usage_metrics_tool_name ON usage_metrics(tool_name);
CREATE INDEX idx_usage_metrics_created_at ON usage_metrics(created_at);

-- =============================================================================
-- Table: encrypted_tasks
-- Purpose: Stores encrypted task file contents and skeleton files for
--          progressive decryption during /cross-team execution.
--          Keys are only released after dependency tasks' GK tokens exist.
-- =============================================================================
CREATE TABLE encrypted_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    file_type TEXT NOT NULL,               -- 'task_spec' or 'skeleton'
    encrypted_content TEXT NOT NULL,        -- base64-encoded encrypted content
    encryption_key TEXT NOT NULL,           -- hex-encoded AES key (MCP-gated)
    depends_on_tasks TEXT,                 -- JSON array of task IDs that must be GK-complete
    original_path TEXT NOT NULL,           -- original file path relative to project root
    created_at TEXT NOT NULL,              -- ISO 8601 timestamp
    decrypted INTEGER DEFAULT 0,           -- 0=locked, 1=decrypted
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX idx_encrypted_tasks_session_id ON encrypted_tasks(session_id);
CREATE INDEX idx_encrypted_tasks_task_id ON encrypted_tasks(task_id);

-- =============================================================================
-- Table: schema_version
-- Purpose: Migration tracking for future schema changes
-- =============================================================================
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,              -- ISO 8601 timestamp
    description TEXT                       -- description of schema change
);

-- Insert initial version record
INSERT INTO schema_version (version, applied_at, description)
VALUES (1, datetime('now'), 'Initial schema with sessions, completion_tokens, phase_tokens, agent_signals, evolution_attempts, usage_metrics');
