#!/usr/bin/env python3
"""
Run individual TPC-H queries on CPU, Sirius, or RasterDB.

Usage:
  python run_tpch.py --mode rasterdb --db tpch_sf1.db --query 6 --suite adapted
  python run_tpch.py -m r -d tpch_sf1.db -q 6 -s a
  python run_tpch.py -m c -q 1                      # CPU mode, Q1, default db
  python run_tpch.py -m s -q 3 -s o                 # Sirius, original Q3
  python run_tpch.py --list                          # list all available queries
  python run_tpch.py --list -s adapted               # list adapted queries only

Shortcuts:
  --mode / -m : rasterdb/r, cpu/c, sirius/s
  --suite / -s: adapted/a, original/o
  --query / -q: 1-22 (TPC-H number) or query name (e.g. lineitem_sum_price)
"""

# python run_tpch.py -m r -s a -d tpch_sf1.db -q 1

import os
import sys
import json
import time
import subprocess
import argparse
import duckdb

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
QUERIES_JSON = os.path.join(SCRIPT_DIR, "tpch_queries.json")

SIRIUS_EXT = os.path.expanduser(
    "~/Device/IMPORTANT/sirius/build/release/extension/sirius/sirius.duckdb_extension")
SIRIUS_CLI = os.path.expanduser(
    "~/Device/IMPORTANT/sirius/build/release/duckdb")

RASTERDB_EXT = os.path.expanduser(
    "~/Device/IMPORTANT/rasterdb/build/release/extension/rasterdb/rasterdb.duckdb_extension")
RASTERDB_CLI = os.path.expanduser(
    "~/Device/IMPORTANT/rasterdb/build/release/duckdb")


def load_queries():
    """Load queries from JSON file."""
    with open(QUERIES_JSON, "r") as f:
        return json.load(f)


def resolve_mode(m):
    """Resolve short mode names."""
    m = m.lower().strip()
    if m in ("r", "rasterdb"):
        return "rasterdb"
    elif m in ("c", "cpu"):
        return "cpu"
    elif m in ("s", "sirius"):
        return "sirius"
    else:
        print(f"ERROR: Unknown mode '{m}'. Use: rasterdb/r, cpu/c, sirius/s")
        sys.exit(1)


def resolve_suite(s):
    """Resolve short suite names."""
    s = s.lower().strip()
    if s in ("a", "adapted"):
        return "adapted"
    elif s in ("o", "original"):
        return "original"
    else:
        print(f"ERROR: Unknown suite '{s}'. Use: adapted/a, original/o")
        sys.exit(1)


def find_query(all_queries, suite, query_key):
    """Find a query by key (Q-number or name) in the given suite."""
    suite_queries = all_queries.get(suite, {})

    # Try direct key match (e.g. "Q6", "lineitem_sum_price")
    if query_key in suite_queries:
        return query_key, suite_queries[query_key]

    # Try "Q<N>" format
    q_upper = query_key.upper()
    if not q_upper.startswith("Q"):
        q_upper = f"Q{q_upper}"
    if q_upper in suite_queries:
        return q_upper, suite_queries[q_upper]

    # Try matching by name substring
    for key, qobj in suite_queries.items():
        if query_key.lower() in qobj["name"].lower():
            return key, qobj
        if query_key.lower() in key.lower():
            return key, qobj

    return None, None


def list_queries(all_queries, suite_filter=None):
    """Print all available queries."""
    for suite in ["original", "adapted"]:
        if suite_filter and suite != suite_filter:
            continue
        queries = all_queries.get(suite, {})
        print(f"\n{'=' * 80}")
        print(f"  Suite: {suite.upper()} ({len(queries)} queries)")
        print(f"{'=' * 80}")
        print(f"  {'Key':<12s} {'Name':<40s} {'Features'}")
        print(f"  {'-' * 76}")
        for key, qobj in queries.items():
            print(f"  {key:<12s} {qobj['name']:<40s} {qobj['features']}")
    print()


def build_env(overrides=None):
    env = os.environ.copy()
    env.pop("__EGL_VENDOR_LIBRARY_DIRS", None)
    if overrides:
        env.update(overrides)
    return env


def run_cpu(db_path, query, query_name):
    """Run on DuckDB CPU via Python API."""
    print(f"[CPU] Running: {query_name}")
    print(f"[CPU] Database: {db_path}")
    print(f"[CPU] SQL:\n  {query}\n")

    con = duckdb.connect(db_path, read_only=True)

    # Warmup
    con.execute(query).fetchall()

    # Timed
    t0 = time.perf_counter()
    result = con.execute(query)
    rows = result.fetchall()
    t1 = time.perf_counter()
    elapsed_ms = (t1 - t0) * 1000

    # Get column names
    col_names = [desc[0] for desc in result.description] if result.description else []

    con.close()

    print(f"{'=' * 60}")
    print(f"  Mode     : CPU (DuckDB Python API)")
    print(f"  Time     : {elapsed_ms:.2f} ms")
    print(f"  Rows     : {len(rows)}")
    print(f"  Columns  : {', '.join(col_names)}")
    print(f"{'=' * 60}")

    # Print results (up to 50 rows)
    if col_names:
        # Compute column widths
        widths = [len(c) for c in col_names]
        display_rows = rows[:50]
        for row in display_rows:
            for i, val in enumerate(row):
                widths[i] = max(widths[i], len(str(val)))

        header = " | ".join(f"{c:<{widths[i]}}" for i, c in enumerate(col_names))
        separator = "-+-".join("-" * w for w in widths)
        print(f"  {header}")
        print(f"  {separator}")
        for row in display_rows:
            line = " | ".join(f"{str(v):<{widths[i]}}" for i, v in enumerate(row))
            print(f"  {line}")

        if len(rows) > 50:
            print(f"  ... ({len(rows) - 50} more rows)")
    print()


def run_rasterdb(db_path, query, query_name):
    """Run on RasterDB (Vulkan GPU)."""
    print(f"[RasterDB] Running: {query_name}")
    print(f"[RasterDB] Database: {db_path}")
    print(f"[RasterDB] SQL:\n  {query}\n")

    escaped = query.replace("'", "''")
    full_sql = f"LOAD '{RASTERDB_EXT}'; PRAGMA enable_profiling; SELECT * FROM gpu_execution('{escaped}');"

    env = build_env({
        "RASTERDF_SHADER_DIR": os.path.expanduser(
            "~/Device/IMPORTANT/rasterdf/shaders/compiled"),
    })

    proc = subprocess.run(
        [RASTERDB_CLI, "-unsigned", db_path, "-c", full_sql],
        capture_output=True, text=True, timeout=100, env=env,
    )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    print(f"{'=' * 60}")
    print(f"  Mode     : RasterDB (Vulkan GPU)")
    print(f"{'=' * 60}")

    # Print stderr (contains TIMER lines)
    if stderr:
        print("\n[stderr output]")
        for line in stderr.strip().split("\n"):
            print(f"  {line}")

    # Print stdout (contains query results)
    if stdout:
        print("\n[stdout output]")
        for line in stdout.strip().split("\n"):
            print(f"  {line}")

    if proc.returncode != 0:
        print(f"\n  EXIT CODE: {proc.returncode}")

    print()


def run_sirius(db_path, query, query_name):
    """Run on Sirius (CUDA GPU)."""
    print(f"[Sirius] Running: {query_name}")
    print(f"[Sirius] Database: {db_path}")
    print(f"[Sirius] SQL:\n  {query}\n")

    escaped = query.replace("'", "''")
    full_sql = (f"SELECT * FROM gpu_buffer_init('12GB', '12GB'); "
                f"PRAGMA enable_profiling; "
                f"SELECT * FROM gpu_processing('{escaped}');")

    env = build_env()

    proc = subprocess.run(
        [SIRIUS_CLI, "-unsigned", db_path, "-c", full_sql],
        capture_output=True, text=True, timeout=300, env=env,
    )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    print(f"{'=' * 60}")
    print(f"  Mode     : Sirius (CUDA GPU)")
    print(f"{'=' * 60}")

    if stderr:
        print("\n[stderr output]")
        for line in stderr.strip().split("\n"):
            print(f"  {line}")

    if stdout:
        print("\n[stdout output]")
        for line in stdout.strip().split("\n"):
            print(f"  {line}")

    if proc.returncode != 0:
        print(f"\n  EXIT CODE: {proc.returncode}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Run TPC-H queries on CPU, Sirius, or RasterDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_tpch.py -m r -q 6 -s a          # RasterDB, adapted Q6
  python run_tpch.py -m c -q 1 -s o          # CPU, original Q1
  python run_tpch.py -m s -q 3               # Sirius, adapted Q3 (default)
  python run_tpch.py -m r -q lineitem_sum_price
  python run_tpch.py --list                   # list all queries
  python run_tpch.py --list -s o              # list original queries
""")
    parser.add_argument("-m", "--mode", type=str, default=None,
                        help="Execution mode: rasterdb/r, cpu/c, sirius/s")
    parser.add_argument("-d", "--db", type=str, default=None,
                        help="Database path (default: tpch/tpch_sf1.db)")
    parser.add_argument("-q", "--query", type=str, default=None,
                        help="Query key: 1-22 (TPC-H Q number) or name")
    parser.add_argument("-s", "--suite", type=str, default="adapted",
                        help="Suite: adapted/a, original/o (default: adapted)")
    parser.add_argument("--list", action="store_true",
                        help="List all available queries")
    args = parser.parse_args()

    all_queries = load_queries()

    # Handle --list
    if args.list:
        suite_f = resolve_suite(args.suite) if args.suite else None
        list_queries(all_queries, suite_f)
        return

    # Require --mode and --query for execution
    if not args.mode:
        parser.print_help()
        print("\nERROR: --mode / -m is required (rasterdb/r, cpu/c, sirius/s)")
        sys.exit(1)
    if not args.query:
        parser.print_help()
        print("\nERROR: --query / -q is required (1-22 or query name)")
        sys.exit(1)

    mode = resolve_mode(args.mode)
    suite = resolve_suite(args.suite)

    # Resolve database path
    db_path = args.db
    if db_path and not os.path.isabs(db_path):
        # Try in tpch/ folder first, then current dir
        tpch_path = os.path.join(SCRIPT_DIR, db_path)
        if os.path.exists(tpch_path):
            db_path = tpch_path
        elif not os.path.exists(db_path):
            db_path = tpch_path  # will fail with clear error
    if not db_path:
        db_path = os.path.join(SCRIPT_DIR, "tpch_sf25.db")

    # Find query
    key, qobj = find_query(all_queries, suite, args.query)
    if qobj is None:
        print(f"ERROR: Query '{args.query}' not found in suite '{suite}'")
        print(f"  Use --list to see available queries")
        sys.exit(1)

    query_name = f"{suite}/{qobj['name']} [{key}]"
    query_sql = qobj["query"]

    print(f"\n{'#' * 60}")
    print(f"  TPC-H Query Runner")
    print(f"  Mode   : {mode}")
    print(f"  Suite  : {suite}")
    print(f"  Query  : {key} — {qobj['name']}")
    print(f"  Features: {qobj['features']}")
    print(f"  DB     : {db_path}")
    print(f"{'#' * 60}\n")

    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}")
        print(f"  Run: python tpch/create_tpch_db.py --sf 1")
        sys.exit(1)

    # Execute
    if mode == "cpu":
        run_cpu(db_path, query_sql, query_name)
    elif mode == "rasterdb":
        run_rasterdb(db_path, query_sql, query_name)
    elif mode == "sirius":
        run_sirius(db_path, query_sql, query_name)


if __name__ == "__main__":
    main()
