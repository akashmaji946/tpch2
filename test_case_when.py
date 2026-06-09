#!/usr/bin/env python3
"""
Reduced test for CASE WHEN + OR GPU support.
Tests:
  1. Ungrouped: sum(CASE WHEN o_orderpriority = 1 OR o_orderpriority = 2 THEN 1 ELSE 0 END) FROM orders
  2. Grouped:   SELECT o_orderpriority, sum(CASE WHEN o_orderstatus = 1 THEN 1 ELSE 0 END) FROM orders GROUP BY o_orderpriority
  3. OR filter:  SELECT count(*) FROM orders WHERE o_orderpriority = 1 OR o_orderpriority = 2
"""

import os
import sys
import subprocess
import time

RASTERDB_EXT = os.path.expanduser(
    "~/Device/IMPORTANT/rasterdb/build/release/extension/rasterdb/rasterdb.duckdb_extension")
RASTERDB_CLI = os.path.expanduser(
    "~/Device/IMPORTANT/rasterdb/build/release/duckdb")
DB_PATH = os.path.expanduser(
    "~/Device/IMPORTANT/tpch/tpch_sf1.db")

def build_env():
    env = os.environ.copy()
    env.pop("__EGL_VENDOR_LIBRARY_DIRS", None)
    env["RASTERDF_SHADER_DIR"] = os.path.expanduser(
        "~/Device/IMPORTANT/rasterdf/shaders/compiled")
    return env

def run_query(label, sql):
    escaped = sql.replace("'", "''")
    full_sql = f"LOAD '{RASTERDB_EXT}'; SELECT * FROM gpu_execution('{escaped}');"
    print(f"\n{'='*70}")
    print(f"  TEST: {label}")
    print(f"  SQL:  {sql}")
    print(f"{'='*70}")

    # CPU reference
    import duckdb
    con = duckdb.connect(DB_PATH, read_only=True)
    cpu_result = con.execute(sql).fetchall()
    cpu_cols = [d[0] for d in con.description]
    con.close()
    print(f"  CPU result: {cpu_result}")

    # GPU
    env = build_env()
    proc = subprocess.run(
        [RASTERDB_CLI, "-unsigned", DB_PATH, "-c", full_sql],
        capture_output=True, text=True, timeout=120, env=env,
    )
    print(f"  GPU stdout:\n{proc.stdout}")
    if proc.stderr:
        print(f"  GPU stderr:\n{proc.stderr}")
    if proc.returncode != 0:
        print(f"  *** FAILED (exit code {proc.returncode}) ***")
    else:
        print(f"  *** PASSED ***")

# # Test 1: OR filter on INTEGER column (simplest - o_shippriority is INT)
# run_query(
#     "OR filter (INT)",
#     "SELECT count(*) FROM orders WHERE o_shippriority = 0 OR o_shippriority = 1"
# )

# # Test 2: Ungrouped CASE WHEN (INT comparison)
# run_query(
#     "Ungrouped CASE WHEN",
#     "SELECT sum(CASE WHEN o_shippriority = 0 THEN 1 ELSE 0 END) as zero_count FROM orders"
# )

# # Test 3: Ungrouped CASE WHEN with OR
# run_query(
#     "Ungrouped CASE WHEN + OR",
#     "SELECT sum(CASE WHEN o_shippriority = 0 OR o_shippriority = 1 THEN 1 ELSE 0 END) as high_count FROM orders"
# )

# # Test 4: OR filter on STRING column (uses string_compare shader)
# run_query(
#     "OR filter (STRING)",
#     "SELECT count(*) FROM orders WHERE o_orderpriority = '1-URGENT' OR o_orderpriority = '2-HIGH'"
# )

# # Test 5: Grouped CASE WHEN (simulates Q12 pattern)
# run_query(
#     "Grouped CASE WHEN (Q12 pattern)",
#     "SELECT o_shippriority, sum(CASE WHEN o_shippriority = 0 THEN 1 ELSE 0 END) as cnt FROM orders GROUP BY o_shippriority"
# )

run_query(
    "IN filter (INT)",
    "SELECT count(*) FROM orders WHERE o_orderkey IN (1, 2, 3)"
)

run_query(
    "NOT IN filter (INT)",
    "SELECT count(*) FROM orders WHERE o_orderkey NOT IN (1, 2, 3)"
)

run_query(
    "IN filter (STRING)",
    "SELECT count(*) FROM lineitem WHERE l_shipmode IN ('MAIL', 'SHIP')"
)

run_query(
    "Q12 reduced IN + CASE + GROUP BY",
    "SELECT l_shipmode, sum(CASE WHEN l_shipmode IN ('MAIL', 'SHIP') THEN 1 ELSE 0 END) as cnt FROM lineitem WHERE l_shipmode IN ('MAIL', 'SHIP') GROUP BY l_shipmode"
)

print("\n\nAll tests complete.")
