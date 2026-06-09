#!/usr/bin/env python3
"""Quick test: run all adapted queries on RasterDB and report status."""
import json, subprocess, os, re

QUERIES_JSON = '/home/akashmaji/Device/IMPORTANT/tpch/tpch_queries.json'
RASTERDB_CLI = os.path.expanduser('~/Device/IMPORTANT/rasterdb/build/release/duckdb')
RASTERDB_EXT = os.path.expanduser('~/Device/IMPORTANT/rasterdb/build/release/extension/rasterdb/rasterdb.duckdb_extension')
DB = '/home/akashmaji/Device/IMPORTANT/tpch/tpch_sf1.db'

with open(QUERIES_JSON) as f:
    queries = json.load(f)

env = os.environ.copy()
env.pop('__EGL_VENDOR_LIBRARY_DIRS', None)
env['RASTERDF_SHADER_DIR'] = os.path.expanduser('~/Device/IMPORTANT/rasterdf/shaders/compiled')

adapted = queries['adapted']
ok = 0
fail = 0
for key in sorted(adapted.keys(), key=lambda k: int(k[1:])):
    q = adapted[key]
    sql = q['query'].replace("'", "''")
    full_sql = f"LOAD '{RASTERDB_EXT}'; SELECT * FROM gpu_execution('{sql}');"
    try:
        proc = subprocess.run([RASTERDB_CLI, '-unsigned', '-csv', '-noheader', DB, '-c', full_sql],
                              capture_output=True, text=True, timeout=60, env=env)
    except subprocess.TimeoutExpired:
        print(f"{key:40s} {'TIMEOUT':40s}")
        fail += 1
        continue

    stderr = proc.stderr or ''
    stdout = proc.stdout or ''

    combined = stderr + '\n' + stdout  # spdlog may go to stdout
    status = 'OK'
    if proc.returncode != 0 or 'SIGSEGV' in combined:
        status = 'CRASH'
    elif 'fallback to CPU' in combined or 'GPU error' in combined:
        for line in combined.split('\n'):
            if 'fallback' in line or 'GPU error' in line:
                m = re.search(r'exception_message":"(.+?)"', line)
                if m:
                    status = f'FALLBACK: {m.group(1)[:55]}'
                else:
                    m2 = re.search(r'falling back to CPU . (.+)', line)
                    if m2:
                        status = f'FALLBACK: {m2.group(1)[:55]}'
                    else:
                        status = 'FALLBACK: unknown'
                break
    elif 'executed on GPU' in combined or 'TOTAL gpu_execute' in combined:
        m = re.search(r'TOTAL gpu_execute\s+([\d.]+)\s*ms', combined)
        if m:
            status = f'GPU OK ({m.group(1)}ms)'

    if status.startswith('GPU OK'):
        ok += 1
    else:
        fail += 1
    label = f"{key} ({q['name']})"
    print(f"{label:40s} {q['features']:40s} {status}")

print(f"\n{'='*80}")
print(f"  GPU OK: {ok}   FAILED: {fail}   TOTAL: {ok+fail}")
print(f"{'='*80}")
