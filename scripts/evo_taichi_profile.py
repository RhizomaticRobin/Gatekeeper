#!/usr/bin/env python3
"""Taichi GPU kernel profiling with ti.sync() bracketing.

CLI:
    python3 evo_taichi_profile.py --profile --setup-file F --call-code "fn(...)" [--warmup 3] [--trials 10]
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from gk_log import gk_error, gk_info


def cmd_profile(args):
    """Run GPU-aware kernel timing with ti.sync() bracketing.

    Writes a temporary runner script that:
      1. exec() the user setup file
      2. Warmup N iterations with ti.sync()
      3. Time M trials with ti.sync() bracketing
      4. Print JSON stats to stdout

    Runs the temp script as a subprocess for isolation.
    """
    setup_file = args.setup_file
    call_code = args.call_code
    warmup = args.warmup
    trials = args.trials

    if not os.path.isfile(setup_file):
        gk_error(f"Setup file not found: {setup_file}")
        print(json.dumps({
            "success": False,
            "error": f"Setup file not found: {setup_file}",
        }))
        sys.exit(1)

    abs_setup = os.path.abspath(setup_file)
    result_marker = "TAICHI_PROFILE_RESULT:"

    runner_code = textwrap.dedent(f"""\
        #!/usr/bin/env python3
        \"\"\"Auto-generated profiling runner.\"\"\"
        import json
        import os
        import sys
        import time
        import statistics

        _MARKER = {result_marker!r}

        def _emit(obj):
            \"\"\"Print JSON result with marker prefix so caller can find it.\"\"\"
            print(_MARKER + json.dumps(obj), flush=True)

        # Redirect Taichi banner output to stderr
        _real_stdout = sys.stdout
        sys.stdout = sys.stderr

        # ---- Import Taichi ----
        try:
            import taichi as ti
        except ImportError:
            sys.stdout = _real_stdout
            _emit({{"success": False, "error": "Taichi not installed"}})
            sys.exit(1)

        # ---- Run user setup in a clean namespace ----
        _setup_ns = {{}}
        try:
            exec(compile(open({abs_setup!r}).read(), {abs_setup!r}, "exec"), _setup_ns)
        except Exception as e:
            sys.stdout = _real_stdout
            _emit({{"success": False, "error": f"Setup failed: {{e}}"}})
            sys.exit(1)

        # Merge setup namespace into globals so call_code can reference
        # functions and fields defined in the setup file.
        globals().update(_setup_ns)

        # Restore stdout for our JSON output
        sys.stdout = _real_stdout

        # Check if ti.init() was called; try ti.sync() as a probe
        _ti_ready = True
        try:
            ti.sync()
        except Exception:
            _ti_ready = False

        call_code = {call_code!r}

        def _sync():
            \"\"\"Call ti.sync() if Taichi is initialized.\"\"\"
            if _ti_ready:
                ti.sync()

        # ---- Warmup ----
        warmup_t0 = time.perf_counter()
        for _w in range({warmup}):
            try:
                exec(call_code)
                _sync()
            except Exception as e:
                _emit({{"success": False, "error": f"Warmup failed: {{e}}"}})
                sys.exit(1)
        warmup_ms = (time.perf_counter() - warmup_t0) * 1000.0

        # ---- Timed trials ----
        timings = []
        for _t in range({trials}):
            try:
                _sync()
                t0 = time.perf_counter()
                exec(call_code)
                _sync()
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                timings.append(elapsed_ms)
            except Exception as e:
                _emit({{"success": False, "error": f"Trial {{_t}} failed: {{e}}"}})
                sys.exit(1)

        timings.sort()
        n = len(timings)
        median_ms = timings[n // 2]
        min_ms = timings[0]
        max_ms = timings[-1]
        std_ms = statistics.stdev(timings) if n > 1 else 0.0

        result = {{
            "median_ms": round(median_ms, 3),
            "min_ms": round(min_ms, 3),
            "max_ms": round(max_ms, 3),
            "std_ms": round(std_ms, 3),
            "trials": n,
            "warmup_ms": round(warmup_ms, 3),
            "success": True,
        }}
        _emit(result)
    """)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_ti_profile_runner.py", delete=False
    ) as f:
        f.write(runner_code)
        runner_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, runner_path],
            capture_output=True,
            text=True,
            timeout=600,
            cwd=os.path.dirname(abs_setup) or ".",
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stderr:
            gk_info(f"Profile runner stderr: {stderr[:1000]}")

        json_line = None
        for line in result.stdout.splitlines():
            if line.startswith(result_marker):
                json_line = line[len(result_marker):]
                break

        if json_line is None:
            if result.returncode != 0:
                print(json.dumps({
                    "success": False,
                    "error": f"Runner exited {result.returncode}",
                    "stderr": stderr[:1000] if stderr else "",
                    "stdout": stdout[:1000] if stdout else "",
                }))
            else:
                print(json.dumps({
                    "success": False,
                    "error": "No result marker found in runner output",
                    "stdout": stdout[:1000] if stdout else "",
                }))
            sys.exit(1)

        try:
            parsed = json.loads(json_line)
            print(json.dumps(parsed, indent=2))
            if not parsed.get("success", False):
                sys.exit(1)
        except json.JSONDecodeError:
            gk_error(f"Could not parse runner output as JSON: {json_line[:500]}")
            print(json.dumps({
                "success": False,
                "error": "Could not parse runner JSON output",
                "raw_output": json_line[:500],
            }))
            sys.exit(1)

    except subprocess.TimeoutExpired:
        print(json.dumps({
            "success": False,
            "error": "Profile runner timed out (600s limit)",
        }))
        sys.exit(1)
    finally:
        try:
            os.unlink(runner_path)
        except OSError:
            pass


def main():
    parser = argparse.ArgumentParser(description="Taichi GPU kernel profiling")
    parser.add_argument("--profile", action="store_true", required=True)
    parser.add_argument("--setup-file", required=True, help="Python setup file")
    parser.add_argument("--call-code", required=True, help="Kernel invocation expression")
    parser.add_argument("--warmup", type=int, default=3, help="Warmup iterations (default: 3)")
    parser.add_argument("--trials", type=int, default=10, help="Timing trials (default: 10)")
    args = parser.parse_args()
    cmd_profile(args)


if __name__ == "__main__":
    main()
