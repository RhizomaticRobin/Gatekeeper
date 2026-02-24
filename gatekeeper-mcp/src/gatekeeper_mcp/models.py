"""
Python data models for Gatekeeper MCP database tables.

These dataclasses map directly to the SQLite schema defined in token_schema.sql.
Each model provides from_row() for database result conversion and to_dict() for serialization.
"""

from dataclasses import dataclass, asdict
from typing import Optional, Any
from datetime import datetime
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
        # Convert context_json dict to string for database storage
        if self.context_json is not None:
            result['context_json'] = json.dumps(self.context_json)
        return result


@dataclass
class EvolutionAttempt:
    """Represents an evolution/retry attempt for a task."""
    id: Optional[int]
    session_id: Optional[str]
    task_id: str
    attempt_number: int
    metrics_json: Optional[dict]
    outcome: Optional[str]
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> 'EvolutionAttempt':
        """Create EvolutionAttempt from sqlite3.Row or dict."""
        metrics = None
        if row['metrics_json']:
            metrics = json.loads(row['metrics_json'])

        return cls(
            id=row['id'],
            session_id=row['session_id'],
            task_id=row['task_id'],
            attempt_number=row['attempt_number'],
            metrics_json=metrics,
            outcome=row['outcome'],
            created_at=row['created_at']
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = asdict(self)
        # Convert metrics_json dict to string for database storage
        if self.metrics_json is not None:
            result['metrics_json'] = json.dumps(self.metrics_json)
        return result


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
