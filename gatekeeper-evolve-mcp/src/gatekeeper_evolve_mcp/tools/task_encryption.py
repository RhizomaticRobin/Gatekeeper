"""
Task encryption MCP tools for Gatekeeper Evolve server.

Provides tools for progressive task decryption during /cross-team execution:
- encrypt_task_files: Encrypt all task specs and skeleton files at session start
- decrypt_task_file: Decrypt a task's files after verifying dependency completion
"""

import base64
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, TYPE_CHECKING

from fastmcp import FastMCP
from gatekeeper_evolve_mcp.database import DatabaseManager
from gatekeeper_evolve_mcp.validators import validate_session_id, ValidationError

if TYPE_CHECKING:
    from gatekeeper_evolve_mcp.state_writer import StateWriter

logger = logging.getLogger(__name__)

_db: Optional[DatabaseManager] = None
_state_writer: Optional["StateWriter"] = None


def register_tools(mcp: FastMCP, db: DatabaseManager, state_writer: Optional["StateWriter"] = None) -> None:
    """Register task encryption tools with FastMCP server."""
    global _db, _state_writer
    _db = db
    _state_writer = state_writer
    mcp.tool()(encrypt_task_files)
    mcp.tool()(decrypt_task_file)
    logger.info("Task encryption tools registered", extra={'tool_name': 'task_encryption'})


def _encrypt_content(content: str, key_hex: str) -> str:
    """Encrypt content using openssl AES-256-CBC. Returns base64-encoded ciphertext."""
    result = subprocess.run(
        ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-base64", "-pass", f"pass:{key_hex}"],
        input=content.encode("utf-8"),
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Encryption failed: {result.stderr.decode()}")
    return result.stdout.decode("utf-8").strip()


def _decrypt_content(encrypted_b64: str, key_hex: str) -> str:
    """Decrypt base64-encoded AES-256-CBC ciphertext. Returns plaintext."""
    result = subprocess.run(
        ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-base64", "-pass", f"pass:{key_hex}"],
        input=encrypted_b64.encode("utf-8"),
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Decryption failed: {result.stderr.decode()}")
    return result.stdout.decode("utf-8")


def _generate_key() -> str:
    """Generate a random 256-bit hex key."""
    return os.urandom(32).hex()


def encrypt_task_files(
    session_id: str,
    project_dir: str,
    plan_path: str = ".claude/plan/plan.yaml",
) -> Dict[str, Any]:
    """
    Encrypt all task spec files and skeleton files at /cross-team start.

    Reads plan.yaml, encrypts each task-*.md and its file_scope.owns files,
    stores encrypted content + keys in the database, and replaces originals
    with placeholder markers.

    Args:
        session_id: Active session ID
        project_dir: Absolute path to project directory
        plan_path: Relative path to plan.yaml (default: .claude/plan/plan.yaml)

    Returns:
        Dict with encrypted_count, task_count, skeleton_count
    """
    try:
        validate_session_id(session_id)
    except ValidationError as e:
        raise ValueError(str(e))

    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "scripts"))
    try:
        from plan_utils import load_plan
    except ImportError:
        # Fallback: load YAML directly
        import yaml
        def load_plan(p):
            with open(p) as f:
                return yaml.safe_load(f)

    full_plan_path = os.path.join(project_dir, plan_path)
    plan = load_plan(full_plan_path)

    # Validate encryption plan before proceeding
    try:
        from validate_encryption import validate_encryption_plan
        validation = validate_encryption_plan(plan)
        skip_set = set(validation.get("skip_encryption", []))
        if validation.get("issues"):
            logger.warning(f"Encryption validation issues: {validation['issues']}")
    except ImportError:
        logger.warning("validate_encryption not available, encrypting all files")
        skip_set = set()

    created_at = datetime.now(timezone.utc).isoformat()
    task_count = 0
    skeleton_count = 0

    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            task_id = str(task.get("id", ""))
            depends_on = [str(d) for d in task.get("depends_on", [])]
            depends_json = json.dumps(depends_on)

            # Encrypt task spec file
            prompt_file = task.get("prompt_file", "")
            if prompt_file:
                spec_path = os.path.join(project_dir, ".claude/plan", prompt_file)
                if os.path.isfile(spec_path):
                    with open(spec_path, "r") as f:
                        content = f.read()

                    key = _generate_key()
                    encrypted = _encrypt_content(content, key)

                    _db.insert("encrypted_tasks", {
                        "session_id": session_id,
                        "task_id": task_id,
                        "file_type": "task_spec",
                        "encrypted_content": encrypted,
                        "encryption_key": key,
                        "depends_on_tasks": depends_json,
                        "original_path": os.path.join(".claude/plan", prompt_file),
                        "created_at": created_at,
                        "decrypted": 0,
                    })

                    # Replace original with placeholder
                    with open(spec_path, "w") as f:
                        f.write(f"ENCRYPTED — use MCP decrypt_task_file(session_id, task_id=\"{task_id}\") to access\n")

                    task_count += 1

            # Encrypt skeleton files (file_scope.owns) — skip files flagged by validator
            scope = task.get("file_scope", {})
            owns = scope.get("owns", []) if isinstance(scope, dict) else []
            for owned_path in owns:
                if owned_path in skip_set:
                    logger.info(f"Skipping encryption of {owned_path} (shared/concurrent read dependency)")
                    continue
                full_path = os.path.join(project_dir, owned_path)
                if os.path.isfile(full_path):
                    with open(full_path, "r") as f:
                        content = f.read()

                    key = _generate_key()
                    encrypted = _encrypt_content(content, key)

                    _db.insert("encrypted_tasks", {
                        "session_id": session_id,
                        "task_id": task_id,
                        "file_type": "skeleton",
                        "encrypted_content": encrypted,
                        "encryption_key": key,
                        "depends_on_tasks": depends_json,
                        "original_path": owned_path,
                        "created_at": created_at,
                        "decrypted": 0,
                    })

                    # Replace with locked placeholder
                    with open(full_path, "w") as f:
                        f.write(f"LOCKED — owned by task {task_id}, decrypted on dependency completion\n")

                    skeleton_count += 1

    return {
        "status": "encrypted",
        "session_id": session_id,
        "task_specs_encrypted": task_count,
        "skeletons_encrypted": skeleton_count,
        "total_encrypted": task_count + skeleton_count,
    }


def decrypt_task_file(
    session_id: str,
    task_id: str,
) -> Dict[str, Any]:
    """
    Decrypt a task's files after verifying all dependency tasks are GK-complete.

    Checks the completion_tokens table for GK_COMPLETE tokens for each dependency.
    Only returns decrypted content if ALL dependencies are satisfied.

    Args:
        session_id: Active session ID
        task_id: Task ID to decrypt files for

    Returns:
        Dict with task_spec (decrypted content), skeleton_files (list of decrypted paths),
        and status

    Raises:
        ValueError: If dependencies not met or task not found
    """
    try:
        validate_session_id(session_id)
    except ValidationError as e:
        raise ValueError(str(e))

    # Get all encrypted entries for this task
    rows = _db.fetchall(
        "SELECT * FROM encrypted_tasks WHERE session_id = ? AND task_id = ?",
        (session_id, task_id),
    )
    if not rows:
        raise ValueError(f"No encrypted files found for task {task_id} in session {session_id}")

    # Check dependencies (same for all files in this task)
    depends_json = rows[0]["depends_on_tasks"]
    depends = json.loads(depends_json) if depends_json else []

    for dep_task_id in depends:
        token = _db.fetchone(
            "SELECT id FROM completion_tokens WHERE task_id = ? AND token_type = 'GK_COMPLETE'",
            (dep_task_id,),
        )
        if not token:
            raise ValueError(
                f"Cannot decrypt task {task_id}: dependency task {dep_task_id} "
                f"not yet completed (no GK_COMPLETE token found)"
            )

    # All dependencies satisfied — decrypt
    task_spec = None
    skeleton_files = []

    for row in rows:
        content = _decrypt_content(row["encrypted_content"], row["encryption_key"])

        if row["file_type"] == "task_spec":
            task_spec = content
        else:
            skeleton_files.append({
                "path": row["original_path"],
                "content": content,
            })

        # Mark as decrypted
        _db.execute(
            "UPDATE encrypted_tasks SET decrypted = 1 WHERE id = ?",
            (row["id"],),
        )

    # Restore original files on disk
    for row in rows:
        content = _decrypt_content(row["encrypted_content"], row["encryption_key"])
        original_path = row["original_path"]
        # Resolve relative to project dir from session
        session_row = _db.fetchone(
            "SELECT project_dir FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        if session_row:
            full_path = os.path.join(session_row["project_dir"], original_path)
            parent = os.path.dirname(full_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(full_path, "w") as f:
                f.write(content)

    return {
        "status": "decrypted",
        "task_id": task_id,
        "task_spec": task_spec,
        "skeleton_files": skeleton_files,
        "files_restored": len(rows),
    }
