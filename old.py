#!/usr/bin/env python3
"""
TPC-H Benchmark: DuckDB CPU vs Sirius (CUDA) vs RasterDB (Vulkan)

Tests both:
  1. Original TPC-H queries (on standard tpch tables with VARCHAR/DATE/DECIMAL)
  2. Adapted int/float-only queries (on *_int tables, GPU-compatible)

Timing: Parses [TIMER]/[SIRIUS_TIMER] TOTAL gpu_execute from stderr.

Usage:
  python tpch_benchmark.py                         # run all queries
  python tpch_benchmark.py --suite adapted         # only int/float queries
  python tpch_benchmark.py --suite original        # only standard queries
  python tpch_benchmark.py --query Q6              # run only matching queries
  python tpch_benchmark.py --sf 10                 # use SF=10 database
"""

import os
import sys
import re
import json
import time
import subprocess
import statistics
import math
import argparse
import duckdb

# ── Configuration ─────────────────────────────────────────────────────────

DEFAULT_SF = 1
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


# ── Load queries from JSON ───────────────────────────────────────────────

def _load_queries_from_json():
    """Load queries from tpch_queries.json and return as flat list tuples.
    Returns list of (suite, name, query, is_large, features).
    """
    with open(QUERIES_JSON, "r") as f:
        data = json.load(f)
    result = []
    for suite in ["original", "adapted"]:
        for key, qobj in data.get(suite, {}).items():
            result.append((
                suite,
                qobj["name"],
                qobj["query"],
                qobj.get("is_large", False),
                qobj.get("features", ""),
            ))
    return result

ALL_QUERIES = _load_queries_from_json()

ORIGINAL_QUERIES = [
    ("original", "Q1_pricing_summary",
     """SELECT l_returnflag, l_linestatus,
        sum(l_quantity) as sum_qty,
        sum(l_extendedprice) as sum_base_price,
        sum(l_extendedprice * (1 - l_discount)) as sum_disc_price,
        sum(l_extendedprice * (1 - l_discount) * (1 + l_tax)) as sum_charge,
        avg(l_quantity) as avg_qty,
        avg(l_extendedprice) as avg_price,
        avg(l_discount) as avg_disc,
        count(*) as count_order
     FROM lineitem
     WHERE l_shipdate <= DATE '1998-12-01' - INTERVAL '90' DAY
     GROUP BY l_returnflag, l_linestatus
     ORDER BY l_returnflag, l_linestatus""",
     False, "GROUP BY, aggregate, DATE filter, VARCHAR group key"),

    ("original", "Q3_shipping_priority",
     """SELECT l_orderkey,
        sum(l_extendedprice * (1 - l_discount)) as revenue,
        o_orderdate, o_shippriority
     FROM customer, orders, lineitem
     WHERE c_mktsegment = 'BUILDING'
       AND c_custkey = o_custkey
       AND l_orderkey = o_orderkey
       AND o_orderdate < DATE '1995-03-15'
       AND l_shipdate > DATE '1995-03-15'
     GROUP BY l_orderkey, o_orderdate, o_shippriority
     ORDER BY revenue DESC, o_orderdate
     LIMIT 10""",
     False, "3-way JOIN, DATE filter, VARCHAR filter, GROUP BY, ORDER BY, LIMIT"),

    ("original", "Q4_order_priority",
     """SELECT o_orderpriority, count(*) as order_count
     FROM orders
     WHERE o_orderdate >= DATE '1993-07-01'
       AND o_orderdate < DATE '1993-07-01' + INTERVAL '3' MONTH
       AND EXISTS (
           SELECT * FROM lineitem
           WHERE l_orderkey = o_orderkey AND l_commitdate < l_receiptdate
       )
     GROUP BY o_orderpriority
     ORDER BY o_orderpriority""",
     False, "EXISTS subquery, DATE filter, GROUP BY"),

    ("original", "Q5_local_supplier_volume",
     """SELECT n_name,
        sum(l_extendedprice * (1 - l_discount)) as revenue
     FROM customer, orders, lineitem, supplier, nation, region
     WHERE c_custkey = o_custkey
       AND l_orderkey = o_orderkey
       AND l_suppkey = s_suppkey
       AND c_nationkey = s_nationkey
       AND s_nationkey = n_nationkey
       AND n_regionkey = r_regionkey
       AND r_name = 'ASIA'
       AND o_orderdate >= DATE '1994-01-01'
       AND o_orderdate < DATE '1994-01-01' + INTERVAL '1' YEAR
     GROUP BY n_name
     ORDER BY revenue DESC""",
     False, "6-way JOIN, DATE+VARCHAR filter, GROUP BY"),

    ("original", "Q6_forecasting_revenue",
     """SELECT sum(l_extendedprice * l_discount) as revenue
     FROM lineitem
     WHERE l_shipdate >= DATE '1994-01-01'
       AND l_shipdate < DATE '1994-01-01' + INTERVAL '1' YEAR
       AND l_discount BETWEEN 0.06 - 0.01 AND 0.06 + 0.01
       AND l_quantity < 24""",
     False, "filter + SUM (simplest TPC-H)"),

    ("original", "Q10_returned_item",
     """SELECT c_custkey, c_name,
        sum(l_extendedprice * (1 - l_discount)) as revenue,
        c_acctbal, n_name, c_address, c_phone, c_comment
     FROM customer, orders, lineitem, nation
     WHERE c_custkey = o_custkey
       AND l_orderkey = o_orderkey
       AND o_orderdate >= DATE '1993-10-01'
       AND o_orderdate < DATE '1993-10-01' + INTERVAL '3' MONTH
       AND l_returnflag = 'R'
       AND c_nationkey = n_nationkey
     GROUP BY c_custkey, c_name, c_acctbal, c_phone, n_name, c_address, c_comment
     ORDER BY revenue DESC
     LIMIT 20""",
     False, "4-way JOIN, DATE+VARCHAR filter, GROUP BY, ORDER BY, LIMIT"),

    ("original", "Q12_shipping_modes",
     """SELECT l_shipmode,
        sum(CASE WHEN o_orderpriority = '1-URGENT' OR o_orderpriority = '2-HIGH' THEN 1 ELSE 0 END) as high_line_count,
        sum(CASE WHEN o_orderpriority <> '1-URGENT' AND o_orderpriority <> '2-HIGH' THEN 1 ELSE 0 END) as low_line_count
     FROM orders, lineitem
     WHERE o_orderkey = l_orderkey
       AND l_shipmode IN ('MAIL', 'SHIP')
       AND l_commitdate < l_receiptdate
       AND l_shipdate < l_commitdate
       AND l_receiptdate >= DATE '1994-01-01'
       AND l_receiptdate < DATE '1994-01-01' + INTERVAL '1' YEAR
     GROUP BY l_shipmode
     ORDER BY l_shipmode""",
     False, "CASE WHEN, IN, DATE filter, JOIN, GROUP BY"),

    ("original", "Q14_promotion_effect",
     """SELECT 100.00 * sum(CASE WHEN p_type LIKE 'PROMO%' THEN l_extendedprice * (1 - l_discount) ELSE 0 END)
        / sum(l_extendedprice * (1 - l_discount)) as promo_revenue
     FROM lineitem, part
     WHERE l_partkey = p_partkey
       AND l_shipdate >= DATE '1995-09-01'
       AND l_shipdate < DATE '1995-09-01' + INTERVAL '1' MONTH""",
     False, "CASE WHEN, LIKE, DATE filter, JOIN"),

    ("original", "Q18_large_volume_customer",
     """SELECT c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice, sum(l_quantity)
     FROM customer, orders, lineitem
     WHERE o_orderkey IN (
         SELECT l_orderkey FROM lineitem GROUP BY l_orderkey HAVING sum(l_quantity) > 300
     )
       AND c_custkey = o_custkey
       AND o_orderkey = l_orderkey
     GROUP BY c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice
     ORDER BY o_totalprice DESC, o_orderdate
     LIMIT 100""",
     False, "IN subquery, HAVING, 3-way JOIN, GROUP BY, ORDER BY, LIMIT"),
]


# ── Adapted Int/Float Queries (on *_int tables, GPU-compatible) ──────────
# These use only INT32 and FLOAT32 columns, no VARCHAR/DATE/DECIMAL.
# Designed to exercise the GPU operators that RasterDB supports.

ADAPTED_QUERIES = [
    # ── Q6-adapted: Simplest TPC-H — filter + aggregate on lineitem ──
    ("adapted", "Q6_revenue_int",
     """SELECT sum(l_extendedprice * l_discount) as revenue
     FROM lineitem_int
     WHERE l_shipdate_int >= 19940101
       AND l_shipdate_int < 19950101
       AND l_discount > 0.05 AND l_discount < 0.07
       AND l_quantity < 24.0""",
     False, "filter + SUM"),

    # ── Q1-adapted: GROUP BY + multi-aggregate on lineitem ──
    ("adapted", "Q1_pricing_int",
     """SELECT l_returnflag_id, l_linestatus_id,
        sum(l_quantity) as sum_qty,
        sum(l_extendedprice) as sum_base_price,
        count(*) as count_order
     FROM lineitem_int
     WHERE l_shipdate_int <= 19980902
     GROUP BY l_returnflag_id, l_linestatus_id""",
     False, "GROUP BY + aggregate + filter"),

    # ── Simple lineitem aggregates ──
    ("adapted", "lineitem_sum_price",
     "SELECT sum(l_extendedprice) FROM lineitem_int",
     False, "ungrouped SUM"),

    ("adapted", "lineitem_avg_qty",
     "SELECT avg(l_quantity) FROM lineitem_int",
     False, "ungrouped AVG"),

    ("adapted", "lineitem_min_max_discount",
     "SELECT min(l_discount), max(l_discount) FROM lineitem_int",
     False, "ungrouped MIN/MAX"),

    ("adapted", "lineitem_count",
     "SELECT count(*) FROM lineitem_int",
     False, "COUNT(*)"),

    # ── Lineitem filters ──
    ("adapted", "lineitem_filter_qty",
     "SELECT l_orderkey, l_quantity, l_extendedprice FROM lineitem_int WHERE l_quantity > 40.0",
     True, "filter >"),

    ("adapted", "lineitem_filter_discount",
     "SELECT l_orderkey, l_discount FROM lineitem_int WHERE l_discount > 0.05 AND l_discount < 0.07",
     True, "filter AND"),

    ("adapted", "lineitem_filter_shipmode",
     "SELECT l_orderkey, l_extendedprice FROM lineitem_int WHERE l_shipmode_id = 5",
     True, "filter = (TRUCK)"),

    # ── Filter + aggregate ──
    ("adapted", "lineitem_filter_sum",
     """SELECT sum(l_extendedprice) FROM lineitem_int
     WHERE l_shipdate_int >= 19950101 AND l_shipdate_int < 19960101""",
     False, "filter + SUM"),

    ("adapted", "lineitem_filter_count",
     """SELECT count(*) FROM lineitem_int WHERE l_returnflag_id = 3""",
     False, "filter + COUNT (returnflag=R)"),

    # ── GROUP BY on lineitem ──
    ("adapted", "lineitem_groupby_returnflag",
     """SELECT l_returnflag_id, sum(l_extendedprice), count(*)
     FROM lineitem_int GROUP BY l_returnflag_id""",
     False, "GROUP BY + SUM + COUNT"),

    ("adapted", "lineitem_groupby_shipmode",
     """SELECT l_shipmode_id, sum(l_quantity), avg(l_extendedprice)
     FROM lineitem_int GROUP BY l_shipmode_id""",
     False, "GROUP BY + SUM + AVG"),

    ("adapted", "lineitem_groupby_linestatus",
     """SELECT l_linestatus_id, min(l_extendedprice), max(l_extendedprice), count(*)
     FROM lineitem_int GROUP BY l_linestatus_id""",
     False, "GROUP BY + MIN + MAX + COUNT"),

    # ── Orders queries ──
    ("adapted", "orders_sum_totalprice",
     "SELECT sum(o_totalprice) FROM orders_int",
     False, "ungrouped SUM"),

    ("adapted", "orders_filter_status",
     "SELECT o_orderkey, o_totalprice FROM orders_int WHERE o_orderstatus_id = 1",
     True, "filter = (status F)"),

    ("adapted", "orders_groupby_priority",
     """SELECT o_orderpriority_id, count(*), sum(o_totalprice)
     FROM orders_int GROUP BY o_orderpriority_id""",
     False, "GROUP BY + COUNT + SUM"),

    ("adapted", "orders_groupby_status",
     """SELECT o_orderstatus_id, count(*), avg(o_totalprice)
     FROM orders_int GROUP BY o_orderstatus_id""",
     False, "GROUP BY + COUNT + AVG"),

    # ── ORDER BY + LIMIT ──
    ("adapted", "lineitem_sort_price_limit",
     """SELECT l_orderkey, l_extendedprice FROM lineitem_int
     ORDER BY l_extendedprice DESC LIMIT 20""",
     False, "ORDER BY DESC + LIMIT"),

    ("adapted", "orders_sort_price_limit",
     """SELECT o_orderkey, o_totalprice FROM orders_int
     ORDER BY o_totalprice DESC LIMIT 20""",
     False, "ORDER BY DESC + LIMIT"),

    # ── Scan + LIMIT ──
    ("adapted", "lineitem_scan_limit",
     "SELECT * FROM lineitem_int LIMIT 10",
     False, "scan + LIMIT"),

    ("adapted", "orders_scan_limit",
     "SELECT * FROM orders_int LIMIT 10",
     False, "scan + LIMIT"),

    # ── JOIN queries (inner join) ──
    ("adapted", "join_orders_customer_count",
     """SELECT count(*)
     FROM orders_int o INNER JOIN customer_int c ON o.o_custkey = c.c_custkey""",
     False, "2-way INNER JOIN + COUNT"),

    ("adapted", "join_orders_customer_sum",
     """SELECT sum(o.o_totalprice)
     FROM orders_int o INNER JOIN customer_int c ON o.o_custkey = c.c_custkey""",
     False, "2-way INNER JOIN + SUM"),

    ("adapted", "join_lineitem_orders_count",
     """SELECT count(*)
     FROM lineitem_int l INNER JOIN orders_int o ON l.l_orderkey = o.o_orderkey""",
     False, "2-way INNER JOIN + COUNT (large)"),

    ("adapted", "join_lineitem_orders_sum",
     """SELECT sum(l.l_extendedprice)
     FROM lineitem_int l INNER JOIN orders_int o ON l.l_orderkey = o.o_orderkey""",
     False, "2-way INNER JOIN + SUM (large)"),

    # ── Q3-adapted: 3-way join (customer-orders-lineitem) ──
    ("adapted", "Q3_shipping_int",
     """SELECT l.l_orderkey,
        sum(l.l_extendedprice * (1.0 - l.l_discount)) as revenue,
        o.o_orderdate_int, o.o_shippriority
     FROM customer_int c, orders_int o, lineitem_int l
     WHERE c.c_mktsegment_id = 2
       AND c.c_custkey = o.o_custkey
       AND l.l_orderkey = o.o_orderkey
       AND o.o_orderdate_int < 19950315
       AND l.l_shipdate_int > 19950315
     GROUP BY l.l_orderkey, o.o_orderdate_int, o.o_shippriority
     ORDER BY revenue DESC, o.o_orderdate_int
     LIMIT 10""",
     False, "3-way JOIN + filter + GROUP BY + ORDER BY + LIMIT"),

    # ── Q5-adapted: multi-join supplier volume ──
    ("adapted", "Q5_supplier_volume_int",
     """SELECT n.n_name_id,
        sum(l.l_extendedprice * (1.0 - l.l_discount)) as revenue
     FROM customer_int c, orders_int o, lineitem_int l,
          supplier_int s, nation_int n, region_int r
     WHERE c.c_custkey = o.o_custkey
       AND l.l_orderkey = o.o_orderkey
       AND l.l_suppkey = s.s_suppkey
       AND c.c_nationkey = s.s_nationkey
       AND s.s_nationkey = n.n_nationkey
       AND n.n_regionkey = r.r_regionkey
       AND r.r_name_id = 2
       AND o.o_orderdate_int >= 19940101
       AND o.o_orderdate_int < 19950101
     GROUP BY n.n_name_id
     ORDER BY revenue DESC""",
     False, "6-way JOIN + filter + GROUP BY + ORDER BY"),

    # ── Projection queries ──
    ("adapted", "lineitem_project_revenue",
     """SELECT l_orderkey, l_extendedprice * (1.0 - l_discount) as disc_price
     FROM lineitem_int LIMIT 100""",
     False, "projection + LIMIT"),

    ("adapted", "lineitem_project_charge",
     """SELECT l_orderkey, l_extendedprice * (1.0 - l_discount) * (1.0 + l_tax) as charge
     FROM lineitem_int LIMIT 100""",
     False, "projection (multi-op) + LIMIT"),

    # ── Filter + GROUP BY ──
    ("adapted", "lineitem_filter_groupby",
     """SELECT l_returnflag_id, sum(l_extendedprice), count(*)
     FROM lineitem_int
     WHERE l_shipdate_int >= 19940101 AND l_shipdate_int < 19950101
     GROUP BY l_returnflag_id""",
     False, "filter + GROUP BY + SUM + COUNT"),

    # ── Partsupp queries ──
    ("adapted", "partsupp_sum_cost",
     "SELECT sum(ps_supplycost * ps_availqty) FROM partsupp_int",
     False, "projection + ungrouped SUM"),

    ("adapted", "partsupp_groupby_suppkey_count",
     """SELECT ps_suppkey, count(*) FROM partsupp_int
     GROUP BY ps_suppkey LIMIT 20""",
     False, "GROUP BY + COUNT + LIMIT (wait: GROUP BY before LIMIT may not push down)"),
]


# ── Helpers ────────────────────────────────────────────────────────────────

def _parse_timer_ms(stderr_text, prefix):
    """Parse TOTAL gpu_execute time from stderr."""
    pattern = re.compile(
        rf'^\[{re.escape(prefix)}\]\s+TOTAL gpu_execute\s+([\d.]+)\s*ms',
        re.MULTILINE)
    match = pattern.search(stderr_text)
    if match:
        return float(match.group(1))
    return None


def _detect_gpu_or_cpu(stderr_text, stdout_text):
    """Detect whether execution ran on GPU or fell back to CPU."""
    combined = (stderr_text or "") + (stdout_text or "")
    if "executed on GPU" in combined:
        return "GPU"
    if "fallback to CPU" in combined or "fallback to DuckDB" in combined:
        return "CPU"
    if "executing query on DuckDB CPU" in combined:
        return "CPU"
    if "Error in GPUExecuteQuery" in combined:
        return "CPU"
    if "[TIMER] TOTAL gpu_execute" in combined or "[SIRIUS_TIMER] TOTAL gpu_execute" in combined:
        return "GPU"
    return "?"


def _build_env(overrides=None):
    env = os.environ.copy()
    env.pop("__EGL_VENDOR_LIBRARY_DIRS", None)
    if overrides:
        env.update(overrides)
    return env


def _count_csv_rows(stdout_text):
    """Count the number of data rows in CSV output."""
    count = 0
    for line in stdout_text.strip().split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("[") or s.startswith("D ") or "info" in s[:40]:
            continue
        if s.startswith("100%") or s.startswith("DuckDB"):
            continue
        count += 1
    return count


def _parse_csv_rows(stdout_text):
    """Parse all data rows from CSV output."""
    rows = []
    for line in stdout_text.strip().split("\n"):
        s = line.strip()
        if not s or s.startswith("[") or "info" in s[:40]:
            continue
        if s.startswith("100%") or s.startswith("DuckDB") or s.startswith("D "):
            continue
        parts = s.split(",")
        converted = []
        for val in parts:
            val = val.strip()
            if val == '' or val == 'NULL':
                converted.append(None)
            else:
                try:
                    converted.append(int(val))
                except ValueError:
                    try:
                        converted.append(float(val))
                    except ValueError:
                        converted.append(val)
        rows.append(tuple(converted))
    return rows


# ── Query Runners ─────────────────────────────────────────────────────────

def run_cpu_query(db_path, query):
    """Run query via DuckDB Python API. Returns (exec_ms, on_gpu)."""
    con = duckdb.connect(db_path, read_only=True)
    t0 = time.perf_counter()
    con.execute(query).fetchall()
    t1 = time.perf_counter()
    con.close()
    return (t1 - t0) * 1000, "CPU"


def run_cpu_query_with_result(db_path, query):
    """Run query and return rows for validation."""
    con = duckdb.connect(db_path, read_only=True)
    rows = con.execute(query).fetchall()
    con.close()
    return rows


def run_rasterdb_query(db_path, query):
    """Run query via RasterDB. Returns (exec_ms, on_gpu)."""
    escaped = query.replace("'", "''")
    full_sql = f"LOAD '{RASTERDB_EXT}'; SELECT * FROM gpu_execution('{escaped}');"

    env = _build_env({
        "RASTERDF_SHADER_DIR": os.path.expanduser("~/Device/IMPORTANT/rasterdf/shaders/compiled"),
    })

    proc = subprocess.run(
        [RASTERDB_CLI, "-unsigned", "-csv", "-noheader", db_path, "-c", full_sql],
        capture_output=True, text=True, timeout=300, env=env,
    )

    stderr = proc.stderr or ""
    stdout = proc.stdout or ""

    if proc.returncode != 0 and not stdout.strip():
        if "Not implemented" in stderr or "NotImplemented" in stderr:
            raise NotImplementedError(stderr.split('\n')[0][:200])
        raise RuntimeError(stderr[:300] or f"CLI exit code {proc.returncode}")

    exec_ms = _parse_timer_ms(stderr, "TIMER")
    on_gpu = _detect_gpu_or_cpu(stderr, stdout)

    if exec_ms is None:
        raise RuntimeError("Could not parse [TIMER] TOTAL gpu_execute from stderr")

    return exec_ms, on_gpu


def run_rasterdb_query_with_result(db_path, query, is_large=False):
    """Run query and return validation data."""
    escaped = query.replace("'", "''")
    full_sql = f"LOAD '{RASTERDB_EXT}'; SELECT * FROM gpu_execution('{escaped}');"

    env = _build_env({
        "RASTERDF_SHADER_DIR": os.path.expanduser("~/Device/IMPORTANT/rasterdf/shaders/compiled"),
    })

    proc = subprocess.run(
        [RASTERDB_CLI, "-unsigned", "-csv", "-noheader", db_path, "-c", full_sql],
        capture_output=True, text=True, timeout=300, env=env,
    )

    stderr = proc.stderr or ""
    stdout = proc.stdout or ""

    if proc.returncode != 0 and not stdout.strip():
        return None, None

    if is_large:
        return _count_csv_rows(stdout), None
    else:
        rows = _parse_csv_rows(stdout)
        return len(rows), rows


def run_sirius_query(db_path, query):
    """Run query via Sirius. Returns (exec_ms, on_gpu)."""
    escaped = query.replace("'", "''")
    full_sql = (f"SELECT * FROM gpu_buffer_init('8GB', '8GB'); "
                f"SELECT * FROM gpu_processing('{escaped}');")

    env = _build_env()

    proc = subprocess.run(
        [SIRIUS_CLI, "-unsigned", "-csv", "-noheader", db_path, "-c", full_sql],
        capture_output=True, text=True, timeout=300, env=env,
    )

    stderr = proc.stderr or ""
    stdout = proc.stdout or ""

    if proc.returncode != 0 and not stdout.strip():
        if "Not implemented" in stderr or "NotImplemented" in stderr:
            raise NotImplementedError(stderr.split('\n')[0][:200])
        raise RuntimeError(stderr[:300] or f"CLI exit code {proc.returncode}")

    exec_ms = _parse_timer_ms(stderr, "SIRIUS_TIMER")
    on_gpu = _detect_gpu_or_cpu(stderr, stdout)

    if exec_ms is None:
        raise RuntimeError("Could not parse [SIRIUS_TIMER] TOTAL gpu_execute from stderr")

    return exec_ms, on_gpu


def run_sirius_query_with_result(db_path, query, is_large=False):
    """Run query and return validation data."""
    escaped = query.replace("'", "''")
    full_sql = (f"SELECT * FROM gpu_buffer_init('8GB', '8GB'); "
                f"SELECT * FROM gpu_processing('{escaped}');")

    env = _build_env()

    proc = subprocess.run(
        [SIRIUS_CLI, "-unsigned", "-csv", "-noheader", db_path, "-c", full_sql],
        capture_output=True, text=True, timeout=300, env=env,
    )

    stderr = proc.stderr or ""
    stdout = proc.stdout or ""

    if proc.returncode != 0 and not stdout.strip():
        return None, None

    if is_large:
        return _count_csv_rows(stdout), None
    else:
        rows = _parse_csv_rows(stdout)
        return len(rows), rows


# ── Validation ────────────────────────────────────────────────────────────

def validate_result(cpu_rows, gpu_count, gpu_rows, query, is_large, rtol=1e-2):
    """Validate GPU result against CPU."""
    if gpu_count is None:
        return False

    if is_large:
        return gpu_count == len(cpu_rows)

    if not isinstance(gpu_rows, list):
        return False

    if len(cpu_rows) != len(gpu_rows):
        return False

    if "GROUP BY" in query.upper():
        try:
            cpu_sorted = sorted(cpu_rows, key=lambda r: tuple(
                x if x is not None else -999999 for x in r))
            gpu_sorted = sorted(gpu_rows, key=lambda r: tuple(
                x if x is not None else -999999 for x in r))
        except TypeError:
            cpu_sorted = cpu_rows
            gpu_sorted = gpu_rows
    else:
        cpu_sorted = cpu_rows
        gpu_sorted = gpu_rows

    for cr, gr in zip(cpu_sorted, gpu_sorted):
        if len(cr) != len(gr):
            return False
        for cv, gv in zip(cr, gr):
            if cv is None and gv is None:
                continue
            if cv is None or gv is None:
                return False
            if isinstance(cv, float) or isinstance(gv, float):
                try:
                    cv_f, gv_f = float(cv), float(gv)
                    if abs(cv_f) < 1e-9 and abs(gv_f) < 1e-9:
                        continue
                    if abs(cv_f - gv_f) / max(abs(cv_f), 1e-9) > rtol:
                        return False
                except (ValueError, TypeError):
                    if cv != gv:
                        return False
            else:
                if cv != gv:
                    return False
    return True


# ── Benchmarking ──────────────────────────────────────────────────────────

def benchmark_timing(run_fn, num_warmup, num_runs):
    """Warmup + timed runs → (median_exec_ms, on_gpu, error_str|None)."""
    on_gpu = "?"
    for _ in range(num_warmup):
        try:
            _, on_gpu = run_fn()
        except (NotImplementedError, RuntimeError, subprocess.TimeoutExpired) as e:
            return None, "?", str(e)[:120]

    exec_times = []
    for _ in range(num_runs):
        try:
            exec_ms, on_gpu = run_fn()
            exec_times.append(exec_ms)
        except (NotImplementedError, RuntimeError, subprocess.TimeoutExpired) as e:
            return None, "?", str(e)[:120]

    return statistics.median(exec_times), on_gpu, None


def cleanup_stale_processes():
    subprocess.run(["pkill", "-9", "-f", "duckdb.*tpch"],
                   capture_output=True, timeout=5)
    time.sleep(0.5)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="TPC-H GPU Database Benchmark")
    parser.add_argument("--suite", choices=["original", "adapted", "all"],
                        default="all", help="Query suite (default: all)")
    parser.add_argument("--sf", type=int, default=DEFAULT_SF,
                        help=f"Scale factor (default: {DEFAULT_SF})")
    parser.add_argument("--runs", type=int, default=3, help="Timed runs (default: 3)")
    parser.add_argument("--warmup", type=int, default=1, help="Warmup runs (default: 1)")
    parser.add_argument("--query", type=str, default=None,
                        help="Run only queries matching this substring")
    parser.add_argument("--no-validate", action="store_true",
                        help="Skip result validation")
    parser.add_argument("--db", type=str, default=None,
                        help="Override database path")
    args = parser.parse_args()

    db_path = args.db or os.path.expanduser(
        f"~/Device/IMPORTANT/tpch/tpch_sf{args.sf}.db")

    cleanup_stale_processes()

    # Select queries
    queries = []
    if args.suite in ("original", "all"):
        queries += [(s, n, q, lg, feat) for s, n, q, lg, feat in ORIGINAL_QUERIES]
    if args.suite in ("adapted", "all"):
        queries += [(s, n, q, lg, feat) for s, n, q, lg, feat in ADAPTED_QUERIES]

    if args.query:
        queries = [(s, n, q, lg, feat) for s, n, q, lg, feat in queries
                   if args.query.lower() in n.lower()]

    print("=" * 120)
    print("  TPC-H Benchmark: DuckDB CPU  vs  Sirius (CUDA)  vs  RasterDB (Vulkan)")
    print("  Timing = gpu_execute only (parsed from stderr TIMER lines)")
    print("=" * 120)
    print(f"  Database    : {db_path}")
    print(f"  Scale Factor: SF={args.sf}")
    print(f"  Runs        : {args.warmup} warmup + {args.runs} timed → median")
    print(f"  Suite       : {args.suite}")
    if args.query:
        print(f"  Filter      : {args.query}")
    print()

    # Check paths
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found: {db_path}")
        print(f"  Run: python tpch/create_tpch_db.py --sf {args.sf}")
        sys.exit(1)

    for label, path in [("Sirius CLI", SIRIUS_CLI), ("RasterDB CLI", RASTERDB_CLI)]:
        if not os.path.exists(path):
            print(f"WARNING: Missing {label}: {path}")

    # Print table row counts
    con = duckdb.connect(db_path, read_only=True)
    tables = con.execute("SHOW TABLES").fetchall()
    print("  Tables:")
    for (tbl,) in sorted(tables):
        try:
            cnt = con.execute(f"SELECT count(*) FROM \"{tbl}\"").fetchone()[0]
            print(f"    {tbl:<20s}: {cnt:>12,} rows")
        except Exception:
            pass
    con.close()
    print()

    results = []

    for suite, name, query, is_large, features in queries:
        label = f"{suite}/{name}"
        print(f"  [{label:<45s}] ", end="", flush=True)

        # ── Validation ──
        rdb_ok = sir_ok = True
        if not args.no_validate:
            try:
                cpu_rows = run_cpu_query_with_result(db_path, query)
            except Exception as e:
                print(f"CPU_ERR: {str(e)[:80]}")
                results.append((suite, name, None, None, False, "?",
                               None, False, "?", features))
                continue

            rdb_cnt, rdb_data = run_rasterdb_query_with_result(db_path, query, is_large)
            sir_cnt, sir_data = run_sirius_query_with_result(db_path, query, is_large)
            rdb_ok = validate_result(cpu_rows, rdb_cnt, rdb_data, query, is_large)
            sir_ok = validate_result(cpu_rows, sir_cnt, sir_data, query, is_large)

        # ── CPU timing ──
        cpu_exec, _, cpu_err = benchmark_timing(
            lambda q=query: run_cpu_query(db_path, q), args.warmup, args.runs)
        if cpu_err:
            print(f"CPU_ERR: {cpu_err[:80]}")
            results.append((suite, name, None, None, sir_ok, "?",
                           None, rdb_ok, "?", features))
            continue

        # ── Sirius timing ──
        sir_exec, sir_gpu, sir_err = benchmark_timing(
            lambda q=query: run_sirius_query(db_path, q), args.warmup, args.runs)
        sir_tag = "✓" if sir_ok else ("SKIP" if sir_err else "✗")

        # ── RasterDB timing ──
        rdb_exec, rdb_gpu, rdb_err = benchmark_timing(
            lambda q=query: run_rasterdb_query(db_path, q), args.warmup, args.runs)
        rdb_tag = "✓" if rdb_ok else ("SKIP" if rdb_err else "✗")

        # One-liner
        s_str = f"{sir_exec:8.1f}ms" if sir_exec is not None else f"{'N/A':>10s}"
        r_str = f"{rdb_exec:8.1f}ms" if rdb_exec is not None else f"{'N/A':>10s}"
        s_dev = f"({sir_gpu})" if sir_gpu else ""
        r_dev = f"({rdb_gpu})" if rdb_gpu else ""
        print(f"CPU={cpu_exec:7.1f}ms  Sirius={s_str}[{sir_tag}]{s_dev}"
              f"  RasterDB={r_str}[{rdb_tag}]{r_dev}")

        results.append((suite, name, cpu_exec, sir_exec, sir_ok, sir_gpu,
                        rdb_exec, rdb_ok, rdb_gpu, features))

    # ── Summary Table ─────────────────────────────────────────────────────
    print()
    hdr = (f"  {'Query':<45s} {'CPU(ms)':>8s} {'Sirius(ms)':>10s} {'S.ok':>4s}"
           f" {'RDB(ms)':>10s} {'R.ok':>4s} {'S.spdup':>8s} {'R.spdup':>8s}"
           f"  Features")
    print("=" * 160)
    print(hdr)
    print("-" * 160)

    sirius_wins = rasterdb_wins = both = 0
    sir_spds, rdb_spds = [], []

    for entry in results:
        (suite, name, cpu_exec, sir_exec, sir_ok, sir_gpu,
         rdb_exec, rdb_ok, rdb_gpu, features) = entry
        label = f"{suite}/{name}"
        c = f"{cpu_exec:8.1f}" if cpu_exec else f"{'ERR':>8s}"
        s = f"{sir_exec:10.1f}" if sir_exec else f"{'N/A':>10s}"
        r = f"{rdb_exec:10.1f}" if rdb_exec else f"{'N/A':>10s}"
        sv = "✓" if sir_ok else "✗"
        rv = "✓" if rdb_ok else "✗"

        ss = f"{cpu_exec/sir_exec:8.2f}x" if cpu_exec and sir_exec else f"{'N/A':>8s}"
        rs = f"{cpu_exec/rdb_exec:8.2f}x" if cpu_exec and rdb_exec else f"{'N/A':>8s}"

        feat_short = features[:40] if features else ""
        print(f"  {label:<45s} {c} {s} {sv:>4s} {r} {rv:>4s} {ss} {rs}  {feat_short}")

        if cpu_exec and sir_exec:
            sir_spds.append(cpu_exec / sir_exec)
        if cpu_exec and rdb_exec:
            rdb_spds.append(cpu_exec / rdb_exec)
        if sir_exec and rdb_exec:
            both += 1
            if sir_exec < rdb_exec:
                sirius_wins += 1
            elif rdb_exec < sir_exec:
                rasterdb_wins += 1

    print("-" * 160)

    if sir_spds:
        g = math.exp(sum(math.log(s) for s in sir_spds) / len(sir_spds))
        print(f"  Sirius   geomean speedup vs CPU: {g:.4f}x  ({len(sir_spds)} queries)")
    if rdb_spds:
        g = math.exp(sum(math.log(s) for s in rdb_spds) / len(rdb_spds))
        print(f"  RasterDB geomean speedup vs CPU: {g:.4f}x  ({len(rdb_spds)} queries)")
    if both:
        print(f"  Head-to-head: Sirius wins {sirius_wins}, "
              f"RasterDB wins {rasterdb_wins}, "
              f"tied {both - sirius_wins - rasterdb_wins}")

    # ── Support Matrix ────────────────────────────────────────────────────
    print()
    print("=" * 100)
    print("  Support Matrix (which queries ran successfully on each backend)")
    print("-" * 100)
    print(f"  {'Query':<45s} {'CPU':>5s} {'Sirius':>8s} {'RasterDB':>10s}")
    print("-" * 100)
    for entry in results:
        (suite, name, cpu_exec, sir_exec, sir_ok, sir_gpu,
         rdb_exec, rdb_ok, rdb_gpu, features) = entry
        label = f"{suite}/{name}"
        cpu_s = "✓" if cpu_exec is not None else "✗"
        sir_s = "✓" if sir_exec is not None else "✗"
        rdb_s = "✓" if rdb_exec is not None else "✗"
        print(f"  {label:<45s} {cpu_s:>5s} {sir_s:>8s} {rdb_s:>10s}")
    print("=" * 100)


if __name__ == "__main__":
    main()
