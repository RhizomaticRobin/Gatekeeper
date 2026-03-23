-- SQLite Schema for Gatekeeper Evolve MCP Server
-- Version: 2
-- Description: Unified schema merging gatekeeper-mcp (sessions, tokens, signals)
--              and evolve-mcp (MAP-Elites population) into a single database.

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

CREATE INDEX idx_phase_tokens_session_id ON phase_tokens(session_id);
CREATE INDEX idx_phase_tokens_phase_id ON phase_tokens(phase_id);
CREATE INDEX idx_phase_tokens_created_at ON phase_tokens(created_at);

-- =============================================================================
-- Table: agent_signals
-- Purpose: Stores agent-emitted signals for workflow coordination
-- =============================================================================
CREATE TABLE agent_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,                       -- optional FK to sessions
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

CREATE INDEX idx_agent_signals_session_id ON agent_signals(session_id);
CREATE INDEX idx_agent_signals_signal_type ON agent_signals(signal_type);
CREATE INDEX idx_agent_signals_pending ON agent_signals(pending);
CREATE INDEX idx_agent_signals_task_id ON agent_signals(task_id);
CREATE INDEX idx_agent_signals_created_at ON agent_signals(created_at);

-- =============================================================================
-- Table: approaches
-- Purpose: Unified MAP-Elites population table for evolutionary optimization.
--          Replaces both the old evolution_attempts table and the JSONL-based
--          Approach storage from evolve-mcp.
-- =============================================================================
CREATE TABLE approaches (
    id TEXT PRIMARY KEY,                    -- UUID
    prompt_addendum TEXT NOT NULL DEFAULT '',  -- evolved strategy text
    parent_id TEXT,                         -- FK to self (parent approach)
    generation INTEGER NOT NULL DEFAULT 0,  -- evolution generation number
    metrics_json TEXT,                      -- JSON: {test_pass_rate, speedup_ratio, duration_s, complexity, ...}
    island INTEGER NOT NULL DEFAULT 0,      -- island index (0 to num_islands-1)
    feature_coords TEXT,                    -- JSON array of ints for MAP-Elites grid
    task_id TEXT NOT NULL,                  -- task identifier
    task_type TEXT DEFAULT '',              -- inferred task type (backend, frontend, speed_optimization, etc.)
    file_patterns TEXT,                     -- JSON array of file scope patterns
    artifacts_json TEXT,                    -- JSON: {test_output, error_trace, ...}
    timestamp REAL NOT NULL,               -- time.time() when created
    iteration INTEGER NOT NULL DEFAULT 0,   -- gatekeeper iteration number
    session_id TEXT,                        -- optional FK to sessions
    outcome TEXT,                           -- SUCCESS/FAILURE/PARTIAL
    attempt_number INTEGER,                 -- sequential attempt number (for evolution tracking)
    created_at TEXT NOT NULL               -- ISO 8601 timestamp
);

CREATE INDEX idx_approaches_task_id ON approaches(task_id);
CREATE INDEX idx_approaches_island ON approaches(island);
CREATE INDEX idx_approaches_session_id ON approaches(session_id);
CREATE INDEX idx_approaches_generation ON approaches(generation);
CREATE INDEX idx_approaches_created_at ON approaches(created_at);

-- =============================================================================
-- Table: population_metadata
-- Purpose: Key-value store for MAP-Elites population configuration
-- =============================================================================
CREATE TABLE population_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Insert default population metadata
INSERT INTO population_metadata (key, value) VALUES ('num_islands', '5');
INSERT INTO population_metadata (key, value) VALUES ('grid_dims', '[10, 10]');

-- =============================================================================
-- Table: usage_metrics
-- Purpose: Stores token usage and cost tracking per session for monitoring
-- =============================================================================
CREATE TABLE usage_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,              -- required FK to sessions
    tool_name TEXT NOT NULL,               -- MCP tool name
    input_tokens INTEGER,                  -- number of input tokens
    output_tokens INTEGER,                 -- number of output tokens
    cost_estimate REAL,                    -- estimated cost in dollars
    created_at TEXT NOT NULL,              -- ISO 8601 timestamp
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX idx_usage_metrics_session_id ON usage_metrics(session_id);
CREATE INDEX idx_usage_metrics_tool_name ON usage_metrics(tool_name);
CREATE INDEX idx_usage_metrics_created_at ON usage_metrics(created_at);

-- =============================================================================
-- Table: verification_results
-- Purpose: Stores formal verification tool execution results (Prusti, Kani, semver, CrossHair, composability)
-- =============================================================================
CREATE TABLE verification_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,              -- FK to sessions
    tool TEXT NOT NULL,                    -- 'prusti', 'kani', 'semver', 'crosshair', 'composability'
    status TEXT NOT NULL,                  -- 'pass', 'fail', 'error'
    result_json TEXT,                      -- JSON blob: {errors, counterexamples, checks, raw_output}
    created_at TEXT NOT NULL,              -- ISO 8601 timestamp
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX idx_verification_results_session_id ON verification_results(session_id);
CREATE INDEX idx_verification_results_tool ON verification_results(tool);
CREATE INDEX idx_verification_results_status ON verification_results(status);
CREATE INDEX idx_verification_results_created_at ON verification_results(created_at);

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

-- Insert version record
INSERT INTO schema_version (version, applied_at, description)
VALUES (3, datetime('now'), 'Unified schema: sessions, tokens, signals, approaches (MAP-Elites), population_metadata, usage_metrics, verification_results');
