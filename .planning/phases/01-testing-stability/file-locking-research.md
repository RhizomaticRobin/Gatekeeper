# File Locking and Atomic Operations for plan.yaml

**Requirement:** R-005 (harden Gatekeeper loop edge cases -- concurrent writes, race conditions)
**Phase:** 01 -- Testing & Stability
**Date:** 2026-02-11

---

## 1. Overview

### The Problem

Multiple executor sub-orchestrators may call `transition-task.sh` simultaneously.
Each invocation reads `plan.yaml`, modifies a task status, and writes it back.
This is a classic **read-modify-write race condition**:

```
Process A: read plan.yaml   (task 1.1 = pending, task 1.2 = pending)
Process B: read plan.yaml   (task 1.1 = pending, task 1.2 = pending)
Process A: set 1.1=completed, write plan.yaml
Process B: set 1.2=completed, write plan.yaml   <-- OVERWRITES A's change!
```

Result: task 1.1 is reverted to `pending` -- data corruption.

### Current Write Path

All writes to `plan.yaml` funnel through a single function:

- **`scripts/plan_utils.py` :: `save_plan(path, plan)`** (line 57-62)
  - Called by `update_task_status()` (line 84-94)
  - Called from CLI via `--complete-task` (line 240)
- **`scripts/transition-task.sh`** (line 45) invokes `plan_utils.py --complete-task`

The current `save_plan()` implementation is:

```python
def save_plan(path, plan):
    with open(path, "w") as f:
        yaml.dump(plan, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
```

This has two problems:
1. **No locking** -- concurrent writers can interleave.
2. **Non-atomic write** -- if the process crashes mid-write, `plan.yaml` is left truncated/corrupt because `open(path, "w")` truncates the file before writing begins.

---

## 2. flock Usage in Bash

### What is flock?

`flock` (from util-linux) manages **advisory file locks** from shell scripts. It operates on file descriptors, not filenames, and uses the kernel's `flock(2)` system call.

### Pattern 1: Wrap Entire Command (simplest)

```bash
flock /tmp/plan.lock python3 plan_utils.py plan.yaml --complete-task 1.1
```

This acquires an exclusive lock on `/tmp/plan.lock` before running the command, and releases it when the command exits. Simple but coarse-grained.

### Pattern 2: File Descriptor + Subshell (critical section)

```bash
(
  flock -x 200           # acquire exclusive lock on fd 200
  # --- critical section ---
  python3 plan_utils.py "$PLAN_FILE" --complete-task "$TASK_ID"
  python3 next-task.py "$PLAN_FILE"
  # --- end critical section ---
) 200>"${PLAN_FILE}.lock"  # fd 200 -> lock file
```

The `200>` redirect opens fd 200 for writing to the lock file. `flock -x 200` acquires an exclusive lock on that fd. When the subshell exits, fd 200 is closed and the lock is automatically released.

### Pattern 3: Named File Descriptor (modern bash 4.1+)

```bash
lock_acquire() {
    exec {LOCKFD}>"${1}.lock" || return 1
    flock -x "$LOCKFD"
}

lock_release() {
    [[ -n "${LOCKFD:-}" ]] || return 1
    exec {LOCKFD}>&-
    unset LOCKFD
}

lock_acquire "$PLAN_FILE"
# ... critical section ...
lock_release
```

### Pattern 4: Non-blocking with Timeout

```bash
flock -x -w 10 200 || { echo "Lock timeout" >&2; exit 1; }
```

The `-w 10` flag waits at most 10 seconds. The `-n` flag fails immediately if the lock cannot be acquired.

### Key Properties of flock

| Property | Value |
|----------|-------|
| Lock type | Advisory (cooperative) |
| Scope | Entire file (not byte-range) |
| Release | Automatic on fd close / process exit |
| Stale lock risk | **None** -- kernel cleans up on process death |
| NFS support | Yes, since Linux 2.6.12 (emulated via fcntl) |
| Deadlock protection | None built-in; use timeouts |

---

## 3. Python fcntl.flock

### Basic Usage

```python
import fcntl
import os

def acquire_lock(lock_path, timeout=30):
    """Acquire an exclusive lock, blocking up to timeout seconds."""
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)  # blocks until acquired
        return fd
    except:
        os.close(fd)
        raise

def release_lock(fd):
    """Release and close lock file descriptor."""
    fcntl.flock(fd, fcntl.LOCK_UN)
    os.close(fd)
```

### Context Manager Pattern (recommended)

```python
import fcntl
import os
from contextlib import contextmanager

@contextmanager
def file_lock(lock_path):
    """Context manager for advisory file locking."""
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield fd
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)

# Usage:
with file_lock("/path/to/plan.yaml.lock"):
    plan = load_plan(path)
    # ... modify plan ...
    save_plan(path, plan)
```

### Non-blocking Variant

```python
import errno

try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError as e:
    if e.errno in (errno.EACCES, errno.EAGAIN):
        print("File is locked by another process")
    raise
```

### Compatibility with Bash flock

Both Python's `fcntl.flock()` and Bash's `flock` command use the same underlying `flock(2)` system call. **They are interoperable** -- a lock acquired in Bash is visible to Python and vice versa, provided they lock the **same file** (not just the same path -- the inode must match).

This is critical: the Bash script and Python script **must use the same lock file** for mutual exclusion to work.

---

## 4. Atomic Write Pattern (tmp + mv)

### The Problem with Direct Writes

```python
with open(path, "w") as f:   # File is TRUNCATED here -- contents gone
    yaml.dump(plan, f)         # If crash occurs during dump, file is corrupt
```

### The Atomic Solution

```python
import os
import tempfile
import yaml

def save_plan_atomic(path, plan):
    """Write plan dict to YAML atomically via tmp + rename."""
    dir_name = os.path.dirname(os.path.abspath(path))

    # 1. Write to a temp file in the SAME directory (same filesystem)
    fd, tmp_path = tempfile.mkstemp(
        dir=dir_name,
        prefix=".plan_",
        suffix=".yaml.tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(plan, f, default_flow_style=False,
                      sort_keys=False, allow_unicode=True)
            f.flush()
            os.fsync(f.fileno())  # 2. Flush to disk

        os.replace(tmp_path, path)  # 3. Atomic rename (POSIX guarantee)
    except:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

### Why This Works

1. **`tempfile.mkstemp(dir=...)`** -- creates the temp file in the **same directory** as the target. This guarantees same-filesystem, which is required for `rename(2)` to be atomic.
2. **`os.fsync()`** -- ensures data is flushed from OS buffers to disk before the rename.
3. **`os.replace()`** -- calls POSIX `rename(2)`, which is atomic. The target file is either the old version or the new version, never a partial write. `os.replace()` is preferred over `os.rename()` because it works cross-platform (on Windows, `os.rename` fails if the target exists).

### Bash Equivalent

```bash
TMP=$(mktemp "${PLAN_FILE}.XXXXXX")
# ... write content to $TMP ...
sync "$TMP"
mv -f "$TMP" "$PLAN_FILE"   # atomic rename on same filesystem
```

---

## 5. Lock File (.lock) Pattern

### How It Works

A sidecar `.lock` file (e.g., `plan.yaml.lock`) is used purely as a locking semaphore. The lock file's contents don't matter -- its existence on a file descriptor is what provides mutual exclusion.

### Two Approaches

#### Approach A: Existence-Based (fragile, NOT recommended)

```bash
while [ -f "$PLAN_FILE.lock" ]; do sleep 0.1; done
touch "$PLAN_FILE.lock"
# ... critical section ...
rm -f "$PLAN_FILE.lock"
```

**Problems:**
- **Race condition** between the `test` and `touch` -- two processes can both pass the check.
- **Stale locks** if the process crashes before `rm`.
- **No kernel cleanup** -- requires manual stale-lock detection.

#### Approach B: flock on .lock File (robust, RECOMMENDED)

```bash
exec 200>"${PLAN_FILE}.lock"
flock -x 200
# ... critical section (read-modify-write plan.yaml) ...
# Lock auto-released when fd 200 is closed (script exit)
```

This combines the `.lock` naming convention with kernel-level `flock(2)`. The `.lock` file is a stable sentinel that survives across invocations. flock handles all atomicity and cleanup.

### Why Not Lock the Data File Directly?

Locking `plan.yaml` directly with `flock` is problematic because:
- `open(path, "w")` **truncates** the file, destroying existing lock state.
- `os.replace()` creates a **new inode**, invalidating locks held on the old inode.
- A separate `.lock` file avoids these issues because it is never truncated or replaced.

---

## 6. Advisory vs. Mandatory Locking on Linux

### Advisory Locks (what we use)

- Processes must **cooperatively** check for locks.
- Unaware processes can read/write locked files freely.
- Used by `flock(2)` and `fcntl(2)` by default.
- **All our scripts are under our control**, so advisory locking is sufficient.

### Mandatory Locks

- Kernel enforces locks at the syscall level (`read(2)`, `write(2)` block).
- Requires: filesystem mounted with `mand`, set-group-ID bit set, group-execute bit cleared.
- **Deprecated in Linux 4.5+**, removed from default kernel configs.
- Prone to race conditions in the kernel implementation itself.
- **Not recommended and not needed for our use case.**

### Summary

Advisory locking is the correct choice here. All writers to `plan.yaml` go through our code (`plan_utils.py`), so we control all participants.

---

## 7. Recommended Approach for plan.yaml

### Strategy: flock on .lock file + atomic writes

Combine both techniques for defense in depth:

1. **Exclusive flock** on `plan.yaml.lock` to serialize read-modify-write cycles.
2. **Atomic writes** (tmp + `os.replace()`) to prevent corruption from crashes.

### Implementation in plan_utils.py

```python
import fcntl
import os
import tempfile
from contextlib import contextmanager

LOCK_TIMEOUT = 30  # seconds

@contextmanager
def plan_lock(plan_path):
    """Acquire exclusive advisory lock on plan.yaml.lock."""
    lock_path = plan_path + ".lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)  # blocks until acquired
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def save_plan(path, plan):
    """Write plan dict back to YAML file atomically."""
    if yaml is None:
        raise RuntimeError("PyYAML is required for writing.")
    abs_path = os.path.abspath(path)
    dir_name = os.path.dirname(abs_path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, prefix=".plan_", suffix=".yaml.tmp")
    try:
        with os.fdopen(fd, "w") as f:
            yaml.dump(plan, f, default_flow_style=False,
                      sort_keys=False, allow_unicode=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, abs_path)
    except:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def update_task_status(path, task_id, status):
    """Update a task's status with locking and atomic write."""
    with plan_lock(path):
        plan = load_plan(path)
        task_id = str(task_id)
        for phase in plan.get("phases", []):
            for task in phase.get("tasks", []):
                if str(task["id"]) == task_id:
                    task["status"] = status
                    save_plan(path, plan)
                    return True
    return False
```

### Implementation in transition-task.sh

Wrap the entire read-modify-write-find-next sequence in a flock:

```bash
LOCK_FILE="${PLAN_FILE}.lock"

(
  flock -x -w 30 200 || { echo "Error: Could not acquire plan lock" >&2; exit 1; }

  # Mark current task as completed
  python3 "${SCRIPTS_DIR}/plan_utils.py" "$PLAN_FILE" --complete-task "$CURRENT_TASK_ID"

  # Find next task
  python3 "${SCRIPTS_DIR}/next-task.py" "$PLAN_FILE"

) 200>"$LOCK_FILE"
```

**Important:** The Bash flock and Python fcntl.flock both use `flock(2)`, so they interoperate correctly on the same `.lock` file. A lock held by the Bash subshell will block Python processes that also try to lock the same file, and vice versa.

### Why Both Layers?

| Layer | Protects Against |
|-------|-----------------|
| flock (serialization) | Lost updates from concurrent read-modify-write |
| Atomic write (tmp+mv) | Corrupted file from crash during write |

Either layer alone is insufficient:
- Atomic write without locking still allows lost updates (both read old state).
- Locking without atomic write still risks corruption if process is killed mid-write.

---

## 8. Gotchas and Edge Cases

### NFS

- `flock(2)` on NFS is emulated via `fcntl(2)` byte-range locks since Linux 2.6.12.
- Works but is **slower** and has **different semantics** in edge cases.
- If `.claude/plan/` is on NFS (unlikely for local dev), test thoroughly.
- **Mitigation:** Our lock file is in `.claude/plan/plan.yaml.lock`, same directory as the data, so same filesystem is guaranteed.

### Stale Locks

- **flock-based locks cannot go stale.** The kernel automatically releases the lock when the file descriptor is closed or the process exits/crashes. This is the primary advantage over existence-based lock files.
- The `.lock` file itself may persist on disk, but this is harmless -- its mere existence does not indicate a held lock.

### Deadlocks

- Risk: Process A locks plan.yaml.lock, then tries to lock another resource that Process B holds (and B is waiting on plan.yaml.lock).
- **Mitigation for our case:** We only have one shared resource (`plan.yaml`), so single-lock deadlock is impossible. If future resources are added, always acquire locks in a consistent global order.

### Signal Handling

- If a process receives SIGKILL (kill -9), the kernel still releases flock locks (fd cleanup on process teardown).
- SIGTERM/SIGINT are handled by Python's default signal handlers, which will run `finally` blocks in context managers.

### Temp File Cleanup

- If a crash occurs after `mkstemp()` but before `os.replace()`, orphan `.plan_*.yaml.tmp` files may accumulate in `.claude/plan/`.
- **Mitigation:** Periodic cleanup of `*.tmp` files older than 1 minute, or simply ignore (they are small).
- The `except` block in `save_plan()` already handles cleanup for non-crash failures.

### Child Process Inheritance

- File descriptors (and their locks) are inherited by child processes after `fork()`.
- If a child holds the fd open, the lock persists even after the parent exits.
- **Mitigation:** In the Bash pattern, the subshell `(...)` ensures fd 200 is closed when the subshell exits. In Python, `os.close(fd)` in the `finally` block ensures cleanup.

### Lock Granularity

- Our approach locks the entire `plan.yaml` for the whole read-modify-write cycle.
- This is appropriate because plan.yaml is small and operations are fast (< 100ms).
- If performance became a concern (unlikely), per-task locking could be considered, but the complexity is not justified.

### Race Window in transition-task.sh (Current Code)

The current `transition-task.sh` has an additional race: it calls `plan_utils.py --complete-task` (which writes) and then separately calls `next-task.py` (which reads). Between these two calls, another process could modify the plan. The fix is to **hold the lock across both operations**, as shown in the recommended implementation above.

---

## 9. Alternatives Considered

### 1. SQLite instead of YAML

- Would provide built-in transactional writes and WAL mode for concurrent access.
- **Rejected:** Over-engineered for a small config file. Would require rewriting all plan utilities.

### 2. Python `filelock` library (pip)

- Cross-platform, well-tested, context manager API.
- **Not recommended:** Adds an external dependency. `fcntl.flock` is stdlib and sufficient for Linux.

### 3. mkdir-based lock (atomic directory creation)

```bash
while ! mkdir "$LOCK_DIR" 2>/dev/null; do sleep 0.1; done
# critical section
rmdir "$LOCK_DIR"
```

- `mkdir` is atomic on POSIX, so no race between check and create.
- **Problem:** Stale locks if process crashes before `rmdir`. Requires PID-based cleanup.
- **Not recommended:** `flock` is strictly better (kernel cleanup, no stale locks).

### 4. Optimistic concurrency (version/checksum)

- Read plan, compute hash, write with hash check -- retry on mismatch.
- **Not recommended for YAML files:** No built-in CAS (compare-and-swap) mechanism. Would require custom protocol.

---

## 10. Summary of Recommendations

| Action | File | Change |
|--------|------|--------|
| Add `plan_lock()` context manager | `scripts/plan_utils.py` | New function using `fcntl.flock` |
| Make `save_plan()` atomic | `scripts/plan_utils.py` | tmp + `os.replace()` pattern |
| Wrap `update_task_status()` in lock | `scripts/plan_utils.py` | Use `plan_lock()` around read-modify-write |
| Add flock wrapper in transition-task.sh | `scripts/transition-task.sh` | Subshell with `flock -x 200` around complete + next |
| Use same lock file everywhere | Both files | `${PLAN_FILE}.lock` for Bash, `path + ".lock"` for Python |
| Add `.gitignore` entry | `.claude/plan/.gitignore` | Ignore `*.lock` and `.plan_*.yaml.tmp` |

**Estimated effort:** Small. Changes are isolated to `save_plan()`, `update_task_status()`, and the critical section of `transition-task.sh`. No API changes, no new dependencies.

---

## References

- [File Locking in Linux (gavv.net)](https://gavv.net/articles/file-locks/) -- comprehensive comparison of flock, fcntl, OFD locks
- [flock(2) man page](https://www.man7.org/linux/man-pages/man2/flock.2.html) -- Linux kernel documentation
- [Locking Critical Sections in Shell Scripts (stegard.net)](https://stegard.net/2022/05/locking-critical-sections-in-shell-scripts/) -- practical Bash flock patterns
- [Introduction to File Locking in Linux (Baeldung)](https://www.baeldung.com/linux/file-locking) -- advisory vs mandatory overview
- [Python fcntl module docs](https://docs.python.org/3/library/fcntl.html) -- stdlib reference
- [Python fcntl.flock example (GitHub Gist)](https://gist.github.com/lucaspar/a1f2457446ea57ea4341b73775026d38) -- practical Python locking
- [Atomic file writes in Python (ActiveState)](https://code.activestate.com/recipes/579097-safely-and-atomically-write-to-a-file/) -- tmp + rename pattern
- [Things UNIX can do atomically (rcrowley.org)](https://rcrowley.org/2010/01/06/things-unix-can-do-atomically.html) -- rename(2) atomicity
- [Linux-Fu: Critical Sections in Bash (Hackaday)](https://hackaday.com/2020/08/18/linux-fu-one-at-a-time-please-critical-sections-in-bash-scripts/) -- fd 200 pattern explained
- [2 Types of Linux File Locking (GeekStuff)](https://www.thegeekstuff.com/2012/04/linux-file-locking-types/) -- advisory vs mandatory examples
