#!/usr/bin/env python3
"""Generate skeleton files for all file_scope.owns entries in a plan.

Reads plan.yaml, extracts every file path from file_scope.owns across all tasks,
and creates minimal skeleton files at those paths. Directories are created as needed.

Usage:
  python3 generate-skeletons.py <plan.yaml> [--dry-run]

Output:
  JSON mapping: {file_path: task_id} for downstream consumption (encryption step).
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan_utils import load_plan

SKELETON_TEMPLATES = {
    ".py": "# Skeleton — implementation by task {task_id}\n",
    ".ts": "// Skeleton — implementation by task {task_id}\n",
    ".tsx": "// Skeleton — implementation by task {task_id}\n",
    ".js": "// Skeleton — implementation by task {task_id}\n",
    ".jsx": "// Skeleton — implementation by task {task_id}\n",
    ".rs": "// Skeleton — implementation by task {task_id}\n",
    ".go": "// Skeleton — implementation by task {task_id}\n",
    ".rb": "# Skeleton — implementation by task {task_id}\n",
    ".java": "// Skeleton — implementation by task {task_id}\n",
    ".css": "/* Skeleton — implementation by task {task_id} */\n",
    ".scss": "/* Skeleton — implementation by task {task_id} */\n",
    ".html": "<!-- Skeleton — implementation by task {task_id} -->\n",
    ".md": "<!-- Skeleton — implementation by task {task_id} -->\n",
    ".yaml": "# Skeleton — implementation by task {task_id}\n",
    ".yml": "# Skeleton — implementation by task {task_id}\n",
    ".toml": "# Skeleton — implementation by task {task_id}\n",
    ".sql": "-- Skeleton — implementation by task {task_id}\n",
    ".sh": "#!/usr/bin/env bash\n# Skeleton — implementation by task {task_id}\n",
}

DEFAULT_SKELETON = "# Skeleton — implementation by task {task_id}\n"


def extract_file_map(plan):
    """Extract mapping of file paths to owning task IDs.

    Returns:
        dict: {file_path: task_id} for all file_scope.owns entries
    """
    file_map = {}
    for phase in plan.get("phases", []):
        for task in phase.get("tasks", []):
            task_id = str(task.get("id", ""))
            scope = task.get("file_scope", {})
            if not isinstance(scope, dict):
                continue
            owns = scope.get("owns", [])
            if not isinstance(owns, list):
                continue
            for path in owns:
                if isinstance(path, str) and path.strip():
                    file_map[path.strip()] = task_id
    return file_map


def extract_file_map_from_outline(outline):
    """Extract file map from project_files in high-level outline.

    Returns:
        dict: {file_path: "phase-{N}"} for all project_files entries
    """
    file_map = {}
    for entry in outline.get("project_files", []):
        path = entry.get("path", "")
        phase = entry.get("phase", "unknown")
        if isinstance(path, str) and path.strip():
            file_map[path.strip()] = f"phase-{phase}"
    return file_map


def generate_skeleton(file_path, task_id):
    """Generate skeleton content for a file based on its extension."""
    _, ext = os.path.splitext(file_path)
    template = SKELETON_TEMPLATES.get(ext, DEFAULT_SKELETON)
    return template.format(task_id=task_id)


def create_skeletons(plan, dry_run=False):
    """Create skeleton files for all file_scope.owns entries.

    Args:
        plan: Parsed plan.yaml
        dry_run: If True, only print what would be created

    Returns:
        dict: {file_path: task_id} mapping of created files
    """
    file_map = extract_file_map(plan)
    return _create_files(file_map, dry_run)


def create_skeletons_from_outline(outline, dry_run=False):
    """Create skeleton files from project_files in a high-level outline.

    Args:
        outline: Parsed high-level-outline.yaml with project_files
        dry_run: If True, only print what would be created

    Returns:
        dict: {file_path: "phase-{N}"} mapping of created files
    """
    file_map = extract_file_map_from_outline(outline)
    if not file_map:
        print("Warning: no project_files found in outline", file=sys.stderr)
        return {}
    return _create_files(file_map, dry_run)


def _create_files(file_map, dry_run=False):
    """Shared implementation for creating skeleton files from a file map."""
    created = {}
    for file_path in sorted(file_map.keys()):
        owner = file_map[file_path]

        if file_path.endswith("/"):
            if dry_run:
                print(f"  mkdir: {file_path} ({owner})")
            else:
                os.makedirs(file_path, exist_ok=True)
            created[file_path] = owner
            continue

        if os.path.exists(file_path):
            print(f"  skip: {file_path} (already exists)", file=sys.stderr)
            created[file_path] = owner
            continue

        if dry_run:
            print(f"  create: {file_path} ({owner})")
        else:
            parent = os.path.dirname(file_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            content = generate_skeleton(file_path, owner)
            with open(file_path, "w") as f:
                f.write(content)

        created[file_path] = owner

    return created


def main():
    dry_run = "--dry-run" in sys.argv
    from_outline = "--from-outline" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    if len(args) != 1:
        print("Usage: python3 generate-skeletons.py <plan_or_outline.yaml> [--from-outline] [--dry-run]", file=sys.stderr)
        sys.exit(1)

    path = args[0]
    if not os.path.isfile(path):
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    data = load_plan(path)

    if from_outline:
        created = create_skeletons_from_outline(data, dry_run=dry_run)
    else:
        created = create_skeletons(data, dry_run=dry_run)

    print(json.dumps(created, indent=2))
    print(f"\n{len(created)} skeleton files {'would be ' if dry_run else ''}created", file=sys.stderr)


if __name__ == "__main__":
    main()
