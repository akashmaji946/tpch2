#!/usr/bin/env python3
import os
import subprocess
import duckdb

DB_PATH = os.path.expanduser("~/Device/IMPORTANT/tpch/tpch_sf1.db")
RASTERDB_EXT = os.path.expanduser("~/Device/IMPORTANT/rasterdb/build/release/extension/rasterdb/rasterdb.duckdb_extension")
RASTERDB_CLI = os.path.expanduser("~/Device/IMPORTANT/rasterdb/build/release/duckdb")

def env():
    e = os.environ.copy()
    e.pop("__EGL_VENDOR_LIBRARY_DIRS", None)
    e["RASTERDF_SHADER_DIR"] = os.path.expanduser("~/Device/IMPORTANT/rasterdf/shaders/compiled")
    return e

def run(label, sql):
    print(f"\n=== {label} ===")
    con = duckdb.connect(DB_PATH, read_only=True)
    cpu = con.execute(sql).fetchall()
    con.close()
    print("CPU:", cpu)
    escaped = sql.replace("'", "''")
    full = f"LOAD '{RASTERDB_EXT}'; SELECT * FROM gpu_execution('{escaped}');"
    proc = subprocess.run([RASTERDB_CLI, "-unsigned", DB_PATH, "-c", full], env=env(), text=True, capture_output=True, timeout=120)
    print(proc.stdout)
    if proc.stderr:
        interesting = [line for line in proc.stderr.splitlines() if "fallback" in line or "unsupported" in line or "query executed on GPU" in line or "FILTER" in line or "RDB_OP" in line]
        print("\n".join(interesting[-20:]))
    print("PASSED" if proc.returncode == 0 else "FAILED")

run("BETWEEN INT", "SELECT count(*) FROM orders WHERE o_orderkey BETWEEN 1 AND 100")
run("BETWEEN DOUBLE", "SELECT count(*) FROM orders WHERE CAST(o_totalprice AS DOUBLE) BETWEEN 1000.0 AND 2000.0")
