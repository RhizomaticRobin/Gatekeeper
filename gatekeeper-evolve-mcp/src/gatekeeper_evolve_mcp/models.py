"""
Python data models for Gatekeeper Evolve MCP database tables.

These dataclasses map directly to the unified SQLite schema.
Each model provides from_row() for database result conversion and to_dict() for serialization.
"""

from dataclasses import dataclass, asdict
from typing import Optional, Any, Dict, List, Tuple
import json


@dataclass
class Session:
    """Represents a verification loop session."""
    session_id: str
    task_id: Optional[str]
    iteration: int
    max_iterations: int
    project_dir: str
    test_command: str
    verifier_model: str
    started_at: str  # ISO 8601 timestamp
    ended_at: Optional[str] = None
    plan_mode: bool = False
    active: bool = True

    @classmethod
    def from_row(cls, row: Any) -> 'Session':
        """Create Session from sqlite3.Row or dict."""
        return cls(
            session_id=row['session_id'],
            task_id=row['task_id'],
            iteration=row['iteration'],
            max_iterations=row['max_iterations'],
            project_dir=row['project_dir'],
            test_command=row['test_command'],
            verifier_model=row['verifier_model'],
            started_at=row['started_at'],
            ended_at=row['ended_at'],
            plan_mode=bool(row['plan_mode']),
            active=bool(row['active'])
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class CompletionToken:
    """Represents a GK_COMPLETE_* or TQG_PASS_* token."""
    id: Optional[int]
    session_id: str
    token_type: str  # 'GK_COMPLETE' or 'TQG_PASS'
    token_value: str
    task_id: Optional[str]
    created_at: str
    validated: bool = False

    @classmethod
    def from_row(cls, row: Any) -> 'CompletionToken':
        """Create CompletionToken from sqlite3.Row or dict."""
        return cls(
            id=row['id'],
            session_id=row['session_id'],
            token_type=row['token_type'],
            token_value=row['token_value'],
            task_id=row['task_id'],
            created_at=row['created_at'],
            validated=bool(row['validated'])
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class PhaseToken:
    """Represents a PVG_COMPLETE_* phase verification token."""
    id: Optional[int]
    session_id: str
    token_value: str
    phase_id: int
    integration_check_passed: bool
    created_at: str
    validated: bool = False

    @classmethod
    def from_row(cls, row: Any) -> 'PhaseToken':
        """Create PhaseToken from sqlite3.Row or dict."""
        return cls(
            id=row['id'],
            session_id=row['session_id'],
            token_value=row['token_value'],
            phase_id=row['phase_id'],
            integration_check_passed=bool(row['integration_check_passed']),
            created_at=row['created_at'],
            validated=bool(row['validated'])
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class AgentSignal:
    """Represents an agent-emitted signal (TESTS_WRITTEN, VERIFICATION_PASS, etc.)."""
    id: Optional[int]
    session_id: Optional[str]
    signal_type: str
    task_id: Optional[str]
    phase_id: Optional[int]
    agent_id: Optional[str]
    context_json: Optional[dict]
    pending: bool
    created_at: str
    processed_at: Optional[str] = None

    @classmethod
    def from_row(cls, row: Any) -> 'AgentSignal':
        """Create AgentSignal from sqlite3.Row or dict."""
        context = None
        if row['context_json']:
            context = json.loads(row['context_json'])

        return cls(
            id=row['id'],
            session_id=row['session_id'],
            signal_type=row['signal_type'],
            task_id=row['task_id'],
            phase_id=row['phase_id'],
            agent_id=row['agent_id'],
            context_json=context,
            pending=bool(row['pending']),
            created_at=row['created_at'],
            processed_at=row['processed_at']
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        if self.context_json is not None:
            result['context_json'] = json.dumps(self.context_json)
        return result


@dataclass
class Approach:
    """Unified MAP-Elites approach — replaces both EvolutionAttempt and JSONL Approach."""
    id: str                                    # UUID
    prompt_addendum: str                       # The evolved strategy text
    parent_id: Optional[str]                   # Parent approach ID (None for seed)
    generation: int                            # Evolution generation number
    metrics: Dict[str, Any]                    # {test_pass_rate, speedup_ratio, duration_s, ...}
    island: int                                # Island index (0 to num_islands-1)
    feature_coords: Tuple[int, ...]            # Binned coordinates in MAP-Elites grid
    task_id: str                               # Task this approach was generated for
    task_type: str                             # Inferred task type
    file_patterns: List[str]                   # File scope patterns
    artifacts: Dict[str, str]                  # {test_output, error_trace}
    timestamp: float                           # time.time()
    iteration: int                             # Gatekeeper iteration
    session_id: Optional[str] = None           # Optional session link
    outcome: Optional[str] = None              # SUCCESS/FAILURE/PARTIAL
    attempt_number: Optional[int] = None       # Sequential attempt number
    created_at: Optional[str] = None           # ISO 8601 timestamp

    @classmethod
    def from_row(cls, row: Any) -> 'Approach':
        """Create Approach from sqlite3.Row."""
        metrics = {}
        if row['metrics_json']:
            metrics = json.loads(row['metrics_json'])

        feature_coords = ()
        if row['feature_coords']:
            feature_coords = tuple(json.loads(row['feature_coords']))

        file_patterns = []
        if row['file_patterns']:
            file_patterns = json.loads(row['file_patterns'])

        artifacts = {}
        if row['artifacts_json']:
            artifacts = json.loads(row['artifacts_json'])

        return cls(
            id=row['id'],
            prompt_addendum=row['prompt_addendum'],
            parent_id=row['parent_id'],
            generation=row['generation'],
            metrics=metrics,
            island=row['island'],
            feature_coords=feature_coords,
            task_id=row['task_id'],
            task_type=row['task_type'] or '',
            file_patterns=file_patterns,
            artifacts=artifacts,
            timestamp=row['timestamp'],
            iteration=row['iteration'],
            session_id=row['session_id'],
            outcome=row['outcome'],
            attempt_number=row['attempt_number'],
            created_at=row['created_at'],
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'prompt_addendum': self.prompt_addendum,
            'parent_id': self.parent_id,
            'generation': self.generation,
            'metrics': self.metrics,
            'island': self.island,
            'feature_coords': list(self.feature_coords),
            'task_id': self.task_id,
            'task_type': self.task_type,
            'file_patterns': self.file_patterns,
            'artifacts': self.artifacts,
            'timestamp': self.timestamp,
            'iteration': self.iteration,
            'session_id': self.session_id,
            'outcome': self.outcome,
            'attempt_number': self.attempt_number,
            'created_at': self.created_at,
        }

    def to_db_dict(self) -> dict:
        """Convert to dictionary suitable for database insertion."""
        return {
            'id': self.id,
            'prompt_addendum': self.prompt_addendum,
            'parent_id': self.parent_id,
            'generation': self.generation,
            'metrics_json': json.dumps(self.metrics) if self.metrics else None,
            'island': self.island,
            'feature_coords': json.dumps(list(self.feature_coords)) if self.feature_coords else None,
            'task_id': self.task_id,
            'task_type': self.task_type,
            'file_patterns': json.dumps(self.file_patterns) if self.file_patterns else None,
            'artifacts_json': json.dumps(self.artifacts) if self.artifacts else None,
            'timestamp': self.timestamp,
            'iteration': self.iteration,
            'session_id': self.session_id,
            'outcome': self.outcome,
            'attempt_number': self.attempt_number,
            'created_at': self.created_at,
        }


@dataclass
class UsageMetric:
    """Represents token usage and cost tracking for a session."""
    id: Optional[int]
    session_id: str
    tool_name: str
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    cost_estimate: Optional[float]
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> 'UsageMetric':
        """Create UsageMetric from sqlite3.Row or dict."""
        return cls(
            id=row['id'],
            session_id=row['session_id'],
            tool_name=row['tool_name'],
            input_tokens=row['input_tokens'],
            output_tokens=row['output_tokens'],
            cost_estimate=row['cost_estimate'],
            created_at=row['created_at']
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class VerificationCheck:
    """Represents a single verification check result (e.g., one Kani proof harness check)."""
    check_name: str
    status: str  # 'SUCCESS', 'FAILURE', 'UNREACHABLE'
    message: str

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return asdict(self)


@dataclass
class VerificationResult:
    """Represents a verification tool execution result stored in verification_results table."""
    id: Optional[int]
    session_id: str
    tool: str  # 'prusti', 'kani', 'semver', 'crosshair', 'composability'
    status: str  # 'pass', 'fail', 'error'
    errors: list  # list[dict] with keys like 'code', 'message', 'file', 'line', 'col'
    counterexamples: list  # list[dict] with tool-specific counterexample data
    checks: list  # list[VerificationCheck] for per-check granularity
    raw_output: str  # full stdout+stderr for debugging
    created_at: str  # ISO 8601 timestamp

    @classmethod
    def from_row(cls, row: Any) -> 'VerificationResult':
        """Create VerificationResult from sqlite3.Row or dict."""
        result_data = json.loads(row['result_json']) if row['result_json'] else {}

        checks_data = result_data.get('checks', [])
        checks = [
            VerificationCheck(
                check_name=c.get('check_name', ''),
                status=c.get('status', ''),
                message=c.get('message', '')
            )
            for c in checks_data
        ]

        return cls(
            id=row['id'],
            session_id=row['session_id'],
            tool=row['tool'],
            status=row['status'],
            errors=result_data.get('errors', []),
            counterexamples=result_data.get('counterexamples', []),
            checks=checks,
            raw_output=result_data.get('raw_output', ''),
            created_at=row['created_at']
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result_json = json.dumps({
            'errors': self.errors,
            'counterexamples': self.counterexamples,
            'checks': [c.to_dict() for c in self.checks],
            'raw_output': self.raw_output,
        })
        return {
            'id': self.id,
            'session_id': self.session_id,
            'tool': self.tool,
            'status': self.status,
            'result_json': result_json,
            'created_at': self.created_at,
        }
