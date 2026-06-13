
#!/usr/bin/env python3
"""
Compare all adapted TPC-H queries across CPU, RasterDB, and Sirius.
Reports execution status, timing, and optional correctness checking.

Usage:
  python compare_all_adapted.py
  python compare_all_adapted.py --check
  python compare_all_adapted.py --check --large
"""

import json
import subprocess
import os
import re
import time
import argparse
import statistics
import duckdb

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUERIES_JSON = os.path.join(SCRIPT_DIR, "tpch_queries.json")

# pick the tpch USE
DB = os.path.join(SCRIPT_DIR, "tpch_sf50.db")

SIRIUS_EXT = os.path.expanduser(
    "~/Device/IMPORTANT/sirius/build/release/extension/sirius/sirius.duckdb_extension"
)
SIRIUS_CLI = os.path.expanduser(
    "~/Device/IMPORTANT/sirius/build/release/duckdb"
)

RASTERDB_EXT = os.path.expanduser(
    "~/Device/IMPORTANT/rasterdb/build/release/extension/rasterdb/rasterdb.duckdb_extension"
)
RASTERDB_CLI = os.path.expanduser(
    "~/Device/IMPORTANT/rasterdb/build/release/duckdb"
)

TIMEOUT = 12000
FLOAT_RTOL = 1e-4

# Strip ANSI escape sequences (color codes etc.) from CLI output
ANSI_RE = re.compile(r'\x1b\[[0-9;]*m')

# Requested constants
WARM_UP = 1
RUNS = 3

RUN_CPU = False
RUN_SIRIUS = False
RUN_RASTERB = True

CPU_MAX_THREADS = 24
CPU_MEMORY_LIMIT = "24GB"


def build_env(overrides=None):
    env = os.environ.copy()
    env.pop("__EGL_VENDOR_LIBRARY_DIRS", None)
    if overrides:
        env.update(overrides)
    return env


def configure_cpu_duckdb(con):
    """Apply fair CPU baseline resource limits."""
    con.execute(f"PRAGMA threads={CPU_MAX_THREADS}")
    con.execute(f"PRAGMA memory_limit='{CPU_MEMORY_LIMIT}'")


def run_cpu(sql):
    """Run CPU query with warmup + median timing. Last run output retained."""
    try:
        con = duckdb.connect(DB, read_only=True)
        configure_cpu_duckdb(con)

        for _ in range(WARM_UP):
            con.execute(sql).fetchall()

        timings = []
        rows = []
        col_names = []

        for _ in range(RUNS):
            t0 = time.perf_counter()
            result = con.execute(sql)
            rows = result.fetchall()  # last run output
            t1 = time.perf_counter()

            col_names = [d[0] for d in result.description] if result.description else []
            timings.append((t1 - t0) * 1000)

        con.close()
        return rows, col_names, statistics.median(timings), "CPU OK"

    except Exception as e:
        return [], [], 0, f"CPU ERR: {str(e)[:50]}"


def run_gpu_cli(cli, ext, sql, mode_name, extra_env=None):
    """Run GPU query with warmup + median timing. Last run output retained."""
    escaped = sql.replace("'", "''")

    if mode_name == "sirius":
        full_sql = f"SELECT * FROM gpu_buffer_init('8GB', '4GB'); PRAGMA enable_profiling; SELECT * FROM gpu_processing('{escaped}');"
    else:
        full_sql = f"LOAD '{ext}'; PRAGMA enable_profiling; SELECT * FROM gpu_execution('{escaped}');"

    env = build_env(extra_env)

    # warmup runs
    for _ in range(WARM_UP):
        try:
            subprocess.run(
                [cli, "-unsigned", "-csv", "-noheader", DB, "-c", full_sql],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                env=env,
            )
        except:
            pass

    timings = []
    last_rows = []

    for _ in range(RUNS):
        try:
            proc = subprocess.run(
                [cli, "-unsigned", "-csv", "-noheader", DB, "-c", full_sql],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return [], 0, "TIMEOUT"
        except FileNotFoundError:
            return [], 0, "NOT FOUND"

        stderr = proc.stderr or ""
        stdout = proc.stdout or ""
        combined = stderr + "\n" + stdout

        if proc.returncode != 0 or "SIGSEGV" in combined:
            return [], 0, "CRASH"

        # timing
        time_ms = 0
        m = re.search(r"TOTAL gpu_execute\s+([\d.]+)\s*ms", combined)
        if m:
            time_ms = float(m.group(1))
        else:
            m = re.search(r"Total Time:\s+([\d.]+)s", combined)
            if m:
                time_ms = float(m.group(1)) * 1000.0
            else:
                m = re.search(r"Total Time:\s+([\d.]+)ms", combined)
                if m:
                    time_ms = float(m.group(1))

        # fallback
        if (
            "fallback to CPU" in combined
            or "GPU error" in combined
            or "CPU-only mode" in combined
            or "executing query on DuckDB CPU" in combined
        ):
            return [], time_ms, "FALLBACK"

        # no gpu
        if (
            "executed on GPU" not in combined
            and "TOTAL gpu_execute" not in combined
        ):
            return [], time_ms, "NO GPU"

        # parse output rows
        csv_rows = []
        for line in stdout.strip().split("\n"):
            line = ANSI_RE.sub('', line).strip()
            if not line:
                continue
            if line.startswith("["):
                continue
            if line.startswith("Success"):
                continue
            if line.startswith("boolean"):
                continue
            if "rows" in line.lower():
                continue
            csv_rows.append(line)

        timings.append(time_ms)
        last_rows = csv_rows

    return last_rows, statistics.median(timings), "GPU OK"


def parse_csv_value(s):
    s = s.strip()

    if s == "" or s.lower() == "null":
        return None

    try:
        return int(s)
    except:
        pass

    try:
        return float(s)
    except:
        pass

    return s


def values_equal(a, b):
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False

    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        fa = float(a)
        fb = float(b)

        if fa == 0 and fb == 0:
            return True
        if fa == 0 or fb == 0:
            return abs(fa - fb) < 1e-6

        return abs(fa - fb) / max(abs(fa), abs(fb)) < FLOAT_RTOL

    return str(a) == str(b)


def check_correctness(cpu_rows, gpu_csv_rows, is_large):
    if not cpu_rows and not gpu_csv_rows:
        return True, "both empty"

    if is_large:
        if len(cpu_rows) == len(gpu_csv_rows):
            return True, f"rows={len(cpu_rows)}"
        return False, "row mismatch"

    gpu_rows = []
    for line in gpu_csv_rows:
        gpu_rows.append(tuple(parse_csv_value(x) for x in line.split(",")))

    cpu_rows = [tuple(row) for row in cpu_rows]

    if len(cpu_rows) != len(gpu_rows):
        return False, "row mismatch"

    def sort_key(row):
        return tuple("" if v is None else str(v) for v in row)

    cpu_rows = sorted(cpu_rows, key=sort_key)
    gpu_rows = sorted(gpu_rows, key=sort_key)

    for cr, gr in zip(cpu_rows, gpu_rows):
        if len(cr) != len(gr):
            return False, "col mismatch"

        for a, b in zip(cr, gr):
            if not values_equal(a, b):
                return False, "value mismatch"

    return True, "exact"


def main():
    parser = argparse.ArgumentParser(
        description="Compare adapted queries: CPU vs RasterDB vs Sirius"
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--large", action="store_true")
    args = parser.parse_args()

    print("Running TPCH:", DB)
    print(f"CPU DuckDB limits: threads={CPU_MAX_THREADS}, memory_limit={CPU_MEMORY_LIMIT}")

    CHECK = args.check
    CHECK_LARGE = args.large

    with open(QUERIES_JSON) as f:
        queries = json.load(f)

    adapted = queries["adapted"]

    rdb_env = {
        "RASTERDF_SHADER_DIR": os.path.expanduser(
            "~/Device/IMPORTANT/rasterdf/shaders/compiled"
        )
    }

    sep = "=" * 120

    print()
    print(sep)

    if CHECK:
        print(
            f"  {'Query':<5s} {'Name':<32s} {'CPU (ms)':>10s}  "
            f"{'RasterDB':>22s}  {'Sirius':>22s}  {'RDB✓':>6s} {'SIR✓':>6s}"
        )
    else:
        print(
            f"  {'Query':<5s} {'Name':<32s} {'CPU (ms)':>10s}  "
            f"{'RasterDB':>22s}  {'Sirius':>22s}"
        )

    print(sep)

    total_cpu = 0
    total_rdb = 0
    total_sir = 0

    n_rdb_gpu = 0
    n_sir_gpu = 0

    n_rdb_correct = 0
    n_sir_correct = 0
    n_checked = 0

    sorted_keys = sorted(adapted.keys(), key=lambda k: int(k[1:]) if k[1:].isdigit() else 999)

    for key in sorted_keys:
        q = adapted[key]
        sql = q["query"]
        name = q["name"]
        is_large = q.get("is_large", False)

        # CPU
        if RUN_CPU:
            cpu_rows, cpu_cols, cpu_ms, _ = run_cpu(sql)
            total_cpu += cpu_ms
            cpu_display = f"{cpu_ms:10.2f}"
        else:
            cpu_rows, cpu_cols, cpu_ms = [], [], 0
            cpu_display = f"{'---':>10s}"

        # RasterDB
        if RUN_RASTERB:
            rdb_csv, rdb_ms, rdb_status = run_gpu_cli(
                RASTERDB_CLI, RASTERDB_EXT, sql, "rasterdb", rdb_env
            )

            if "GPU OK" in rdb_status:
                total_rdb += rdb_ms
                n_rdb_gpu += 1
                rdb_display = f"GPU OK ({rdb_ms:7.2f}ms)"
            else:
                rdb_display = rdb_status[:22]
        else:
            rdb_csv, rdb_ms, rdb_status = [], 0, "SKIPPED"
            rdb_display = "---"

        # Sirius
        if RUN_SIRIUS:
            sir_csv, sir_ms, sir_status = run_gpu_cli(
                SIRIUS_CLI, SIRIUS_EXT, sql, "sirius"
            )

            if "GPU OK" in sir_status:
                total_sir += sir_ms
                n_sir_gpu += 1
                sir_display = f"GPU OK ({sir_ms:7.2f}ms)"
            else:
                sir_display = sir_status[:22]
        else:
            sir_csv, sir_ms, sir_status = [], 0, "SKIPPED"
            sir_display = "---"

        rdb_chk = ""
        sir_chk = ""

        if CHECK and RUN_CPU and (not is_large or CHECK_LARGE):
            n_checked += 1

            if "GPU OK" in rdb_status:
                ok, _ = check_correctness(cpu_rows, rdb_csv, is_large)
                rdb_chk = "✓" if ok else "✗"
                if ok:
                    n_rdb_correct += 1
            else:
                rdb_chk = "-"

            if "GPU OK" in sir_status:
                ok, _ = check_correctness(cpu_rows, sir_csv, is_large)
                sir_chk = "✓" if ok else "✗"
                if ok:
                    n_sir_correct += 1
            else:
                sir_chk = "-"
        elif CHECK:
            rdb_chk = "---" if not RUN_RASTERB else "-"
            sir_chk = "---" if not RUN_SIRIUS else "-"

        if CHECK:
            print(
                f"  {key:<5s} {name:<32s} {cpu_display:>10s}  "
                f"{rdb_display:>22s}  {sir_display:>22s}  "
                f"{rdb_chk:>6s} {sir_chk:>6s}"
            )
        else:
            print(
                f"  {key:<5s} {name:<32s} {cpu_display:>10s}  "
                f"{rdb_display:>22s}  {sir_display:>22s}"
            )

    print(sep)

    n_total = len(adapted)

    print(f"\n  Summary ({n_total} queries):")
    if RUN_CPU:
        print(f"    CPU total         : {total_cpu:10.2f} ms")
    else:
        print(f"    CPU total         :        ---")
    if RUN_RASTERB:
        print(f"    RasterDB GPU OK   : {n_rdb_gpu}/{n_total}  total: {total_rdb:10.2f} ms")
    else:
        print(f"    RasterDB GPU OK   : ---")
    if RUN_SIRIUS:
        print(f"    Sirius   GPU OK   : {n_sir_gpu}/{n_total}  total: {total_sir:10.2f} ms")
    else:
        print(f"    Sirius   GPU OK   : ---")

    if CHECK:
        if RUN_CPU and RUN_RASTERB:
            print(f"    RasterDB correct  : {n_rdb_correct}/{n_checked} checked")
        else:
            print(f"    RasterDB correct  : ---")
        if RUN_CPU and RUN_SIRIUS:
            print(f"    Sirius   correct  : {n_sir_correct}/{n_checked} checked")
        else:
            print(f"    Sirius   correct  : ---")

    if RUN_CPU and RUN_RASTERB and total_rdb > 0:
        print(f"    RasterDB speedup  : {total_cpu / total_rdb:.2f}x vs CPU")

    if RUN_CPU and RUN_SIRIUS and total_sir > 0:
        print(f"    Sirius   speedup  : {total_cpu / total_sir:.2f}x vs CPU")

    if RUN_RASTERB and RUN_SIRIUS and total_rdb > 0 and total_sir > 0:
        print(f"    RasterDB vs Sirius: {total_sir / total_rdb:.2f}x")

    print()


if __name__ == "__main__":
    main()




# SELECT * FROM gpu_execution('SELECT l_returnflag_id, l_linestatus_id, sum(l_quantity) as sum_qty, sum(l_extendedprice) as sum_base_price, count(*) as count_order FROM lineitem_int WHERE l_shipdate_int <= 19980902 GROUP BY l_returnflag_id, l_linestatus_id');
