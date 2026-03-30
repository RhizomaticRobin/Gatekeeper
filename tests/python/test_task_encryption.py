"""Tests for task encryption round-trip: encrypt → decrypt → verify content match."""

import json
import os
import sys
import yaml
import pytest

# Add both scripts/ and the evolve-mcp source to sys.path
REPO_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
sys.path.insert(0, os.path.join(REPO_ROOT, 'scripts'))
sys.path.insert(0, os.path.join(REPO_ROOT, 'gatekeeper-evolve-mcp', 'src'))

from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.tools import task_encryption


@pytest.fixture
def db(tmp_path):
    """Create a fresh database with the unified schema."""
    db_path = str(tmp_path / "test.db")
    schema_path = os.path.join(REPO_ROOT, 'gatekeeper-evolve-mcp', 'unified_schema.sql')
    return DatabaseManager(db_path, schema_path=schema_path)


@pytest.fixture
def session_id():
    return "gk_20260329_abcdef"


@pytest.fixture
def project(tmp_path):
    """Create a fake project directory with plan, task specs, and skeleton files."""
    project_dir = tmp_path / "project"
    plan_dir = project_dir / ".claude" / "plan" / "tasks"
    plan_dir.mkdir(parents=True)

    # Task spec files
    task_1_1 = plan_dir / "task-1.1.md"
    task_1_1.write_text("# Task 1.1\nImplement user authentication with bcrypt hashing.\n")

    task_1_2 = plan_dir / "task-1.2.md"
    task_1_2.write_text("# Task 1.2\nAdd API routes for login and registration.\n")

    # Skeleton source files
    src_dir = project_dir / "src" / "auth"
    src_dir.mkdir(parents=True)
    (src_dir / "handler.py").write_text("# auth handler skeleton\ndef login(): pass\n")
    (src_dir / "routes.py").write_text("# routes skeleton\ndef register(): pass\n")

    # Plan YAML
    plan = {
        "metadata": {"project": "test-project"},
        "phases": [{
            "id": 1,
            "name": "Auth",
            "tasks": [
                {
                    "id": "1.1",
                    "name": "Auth handler",
                    "status": "pending",
                    "depends_on": [],
                    "prompt_file": "tasks/task-1.1.md",
                    "file_scope": {"owns": ["src/auth/handler.py"]},
                },
                {
                    "id": "1.2",
                    "name": "API routes",
                    "status": "pending",
                    "depends_on": ["1.1"],
                    "prompt_file": "tasks/task-1.2.md",
                    "file_scope": {"owns": ["src/auth/routes.py"]},
                },
            ],
        }],
    }
    plan_path = project_dir / ".claude" / "plan" / "plan.yaml"
    with open(plan_path, "w") as f:
        yaml.dump(plan, f)

    return str(project_dir)


def _setup_module(db):
    """Wire up the task_encryption module's global _db."""
    task_encryption._db = db


def _create_session(db, session_id, project_dir):
    """Insert a session row so decrypt can resolve project_dir."""
    db.insert("sessions", {
        "session_id": session_id,
        "project_dir": project_dir,
        "test_command": "echo ok",
        "verifier_model": "sonnet",
        "started_at": "2026-03-29T00:00:00Z",
        "active": 1,
    })


class TestLowLevelCrypto:
    """Test _encrypt_content / _decrypt_content round-trip."""

    def test_round_trip_short_string(self):
        key = task_encryption._generate_key()
        plaintext = "hello world"
        encrypted = task_encryption._encrypt_content(plaintext, key)
        decrypted = task_encryption._decrypt_content(encrypted, key)
        assert decrypted == plaintext

    def test_round_trip_multiline(self):
        key = task_encryption._generate_key()
        plaintext = "# Task 1.1\n\nImplement auth.\n\n```python\ndef login(): pass\n```\n"
        encrypted = task_encryption._encrypt_content(plaintext, key)
        decrypted = task_encryption._decrypt_content(encrypted, key)
        assert decrypted == plaintext

    def test_round_trip_unicode(self):
        key = task_encryption._generate_key()
        plaintext = "Unicode test: \u00e9\u00e8\u00ea \u2014 \u2192 \u2603"
        encrypted = task_encryption._encrypt_content(plaintext, key)
        decrypted = task_encryption._decrypt_content(encrypted, key)
        assert decrypted == plaintext

    def test_wrong_key_fails(self):
        key1 = task_encryption._generate_key()
        key2 = task_encryption._generate_key()
        encrypted = task_encryption._encrypt_content("secret", key1)
        with pytest.raises(RuntimeError, match="Decryption failed"):
            task_encryption._decrypt_content(encrypted, key2)

    def test_different_keys_produce_different_ciphertext(self):
        key1 = task_encryption._generate_key()
        key2 = task_encryption._generate_key()
        plaintext = "same content"
        enc1 = task_encryption._encrypt_content(plaintext, key1)
        enc2 = task_encryption._encrypt_content(plaintext, key2)
        assert enc1 != enc2


class TestEncryptTaskFiles:
    """Test the encrypt_task_files MCP tool."""

    def test_encrypts_task_specs_and_skeletons(self, db, session_id, project):
        _setup_module(db)
        _create_session(db, session_id, project)

        result = encrypt_task_files(session_id, project)

        assert result["status"] == "encrypted"
        assert result["task_specs_encrypted"] == 2
        assert result["skeletons_encrypted"] == 2
        assert result["total_encrypted"] == 4

    def test_originals_replaced_with_placeholders(self, db, session_id, project):
        _setup_module(db)
        _create_session(db, session_id, project)

        encrypt_task_files(session_id, project)

        spec_path = os.path.join(project, ".claude/plan/tasks/task-1.1.md")
        content = open(spec_path).read()
        assert "ENCRYPTED" in content

        skeleton_path = os.path.join(project, "src/auth/handler.py")
        content = open(skeleton_path).read()
        assert "LOCKED" in content

    def test_encrypted_content_stored_in_db(self, db, session_id, project):
        _setup_module(db)
        _create_session(db, session_id, project)

        encrypt_task_files(session_id, project)

        rows = db.fetchall(
            "SELECT * FROM encrypted_tasks WHERE session_id = ?",
            (session_id,),
        )
        assert len(rows) == 4

        # Each row should have non-empty encrypted content and key
        for row in rows:
            assert row["encrypted_content"]
            assert row["encryption_key"]
            assert len(row["encryption_key"]) == 64  # 32 bytes = 64 hex chars
            assert row["decrypted"] == 0

    def test_invalid_session_id_raises(self, db, project):
        _setup_module(db)
        with pytest.raises(ValueError, match="Invalid session ID"):
            encrypt_task_files("bad-session", project)


class TestDecryptTaskFile:
    """Test the decrypt_task_file MCP tool."""

    def _encrypt_first(self, db, session_id, project):
        _setup_module(db)
        _create_session(db, session_id, project)
        return encrypt_task_files(session_id, project)

    def test_decrypt_no_deps_succeeds(self, db, session_id, project):
        """Task 1.1 has no dependencies — should decrypt immediately."""
        self._encrypt_first(db, session_id, project)

        result = decrypt_task_file(session_id, "1.1")

        assert result["status"] == "decrypted"
        assert result["task_id"] == "1.1"
        assert "# Task 1.1" in result["task_spec"]
        assert "bcrypt" in result["task_spec"]
        assert len(result["skeleton_files"]) == 1
        assert result["skeleton_files"][0]["path"] == "src/auth/handler.py"
        assert "def login" in result["skeleton_files"][0]["content"]

    def test_decrypt_restores_files_on_disk(self, db, session_id, project):
        """After decrypt, the original file content should be restored."""
        self._encrypt_first(db, session_id, project)

        decrypt_task_file(session_id, "1.1")

        spec_path = os.path.join(project, ".claude/plan/tasks/task-1.1.md")
        assert "# Task 1.1" in open(spec_path).read()

        handler_path = os.path.join(project, "src/auth/handler.py")
        assert "def login" in open(handler_path).read()

    def test_decrypt_marks_rows_decrypted(self, db, session_id, project):
        self._encrypt_first(db, session_id, project)

        decrypt_task_file(session_id, "1.1")

        rows = db.fetchall(
            "SELECT decrypted FROM encrypted_tasks WHERE task_id = '1.1'",
        )
        for row in rows:
            assert row["decrypted"] == 1

    def test_decrypt_blocked_by_unmet_dependency(self, db, session_id, project):
        """Task 1.2 depends on 1.1 — should fail without GK_COMPLETE token."""
        self._encrypt_first(db, session_id, project)

        with pytest.raises(ValueError, match="dependency task 1.1.*not yet completed"):
            decrypt_task_file(session_id, "1.2")

    def test_decrypt_succeeds_after_dependency_completed(self, db, session_id, project):
        """Task 1.2 should decrypt after 1.1 gets a GK_COMPLETE token."""
        self._encrypt_first(db, session_id, project)

        # Simulate task 1.1 completion by inserting a GK_COMPLETE token
        db.insert("completion_tokens", {
            "session_id": session_id,
            "token_type": "GK_COMPLETE",
            "token_value": "GK_COMPLETE_" + "a" * 32,
            "task_id": "1.1",
            "created_at": "2026-03-29T00:00:00Z",
        })

        result = decrypt_task_file(session_id, "1.2")

        assert result["status"] == "decrypted"
        assert "# Task 1.2" in result["task_spec"]
        assert "API routes" in result["task_spec"]

    def test_decrypt_nonexistent_task_raises(self, db, session_id, project):
        self._encrypt_first(db, session_id, project)

        with pytest.raises(ValueError, match="No encrypted files found"):
            decrypt_task_file(session_id, "9.9")

    def test_full_round_trip_content_integrity(self, db, session_id, project):
        """Verify exact content match: original → encrypt → decrypt."""
        # Read originals before encrypting
        spec_path = os.path.join(project, ".claude/plan/tasks/task-1.1.md")
        handler_path = os.path.join(project, "src/auth/handler.py")
        original_spec = open(spec_path).read()
        original_handler = open(handler_path).read()

        self._encrypt_first(db, session_id, project)
        result = decrypt_task_file(session_id, "1.1")

        assert result["task_spec"] == original_spec
        assert result["skeleton_files"][0]["content"] == original_handler

        # Also verify disk files match originals
        assert open(spec_path).read() == original_spec
        assert open(handler_path).read() == original_handler


# Import the functions under test at module level for direct use in tests
encrypt_task_files = task_encryption.encrypt_task_files
decrypt_task_file = task_encryption.decrypt_task_file
