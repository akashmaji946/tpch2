#!/usr/bin/env python3
import os
import subprocess

DB_PATH = os.path.expanduser("~/Device/IMPORTANT/tpch/tpch_sf1.db")
RASTERDB_EXT = os.path.expanduser("~/Device/IMPORTANT/rasterdb/build/release/extension/rasterdb/rasterdb.duckdb_extension")
RASTERDB_CLI = os.path.expanduser("~/Device/IMPORTANT/rasterdb/build/release/duckdb")
WHERE = "l_shipdate >= DATE '1994-01-01' AND l_shipdate < DATE '1994-01-01' + INTERVAL '1' YEAR AND l_discount BETWEEN 0.06 - 0.01 AND 0.06 + 0.01 AND l_quantity < 24"

def env():
    e = os.environ.copy()
    e.pop("__EGL_VENDOR_LIBRARY_DIRS", None)
    e["RASTERDF_SHADER_DIR"] = os.path.expanduser("~/Device/IMPORTANT/rasterdf/shaders/compiled")
    return e

def run(sql):
    escaped = sql.replace("'", "''")
    full = f"LOAD '{RASTERDB_EXT}'; SELECT * FROM gpu_execution('{escaped}');"
    proc = subprocess.run([RASTERDB_CLI, "-unsigned", DB_PATH, "-c", full], env=env(), text=True, capture_output=True, timeout=120)
    print("\nSQL:", sql)
    print(proc.stdout)
    if "fallback" in proc.stderr or "unsupported" in proc.stderr:
        print(proc.stderr)

for expr in ["count(*)", "sum(l_discount)", "sum(l_extendedprice)", "sum(l_extendedprice * l_discount)"]:
    run(f"SELECT {expr} FROM lineitem WHERE {WHERE}")
