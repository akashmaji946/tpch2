#!/usr/bin/env python3
"""Debug failing queries: show CPU vs RasterDB output side by side."""
import duckdb, subprocess, os, json

DB = '~/Device/IMPORTANT/tpch/tpch_sf1.db'
CLI = os.path.expanduser('~/Device/IMPORTANT/rasterdb/build/release/duckdb')
EXT = os.path.expanduser('~/Device/IMPORTANT/rasterdb/build/release/extension/rasterdb/rasterdb.duckdb_extension')

with open('tpch_queries.json') as f:
    queries = json.load(f)['adapted']

env = os.environ.copy()
env.pop('__EGL_VENDOR_LIBRARY_DIRS', None)
env['RASTERDF_SHADER_DIR'] = os.path.expanduser('~/Device/IMPORTANT/rasterdf/shaders/compiled')

for qk in ['Q14','Q15','Q20','Q21','Q22','Q32','Q33','Q2','Q3']:
    q = queries[qk]
    sql = q['query']
    # CPU
    con = duckdb.connect(DB, read_only=True)
    cpu = con.execute(sql).fetchall()
    cols = [d[0] for d in con.execute(sql).description]
    con.close()
    # GPU
    escaped = sql.replace("'", "''")
    full_sql = f"LOAD '{EXT}'; SELECT * FROM gpu_execution('{escaped}');"
    proc = subprocess.run([CLI, '-unsigned', '-csv', '-noheader', DB, '-c', full_sql],
                          capture_output=True, text=True, timeout=60, env=env)
    gpu_lines = [l.strip() for l in proc.stdout.strip().split('\n')
                 if l.strip() and not l.strip().startswith('[') and 'rows' not in l.lower()
                 and 'Success' not in l and 'boolean' not in l]
    print(f'=== {qk}: {q["name"]} ({q["features"]}) ===')
    print(f'  SQL: {sql[:100]}...')
    print(f'  Cols: {cols}')
    print(f'  CPU ({len(cpu)} rows):')
    for r in cpu[:8]:
        print(f'    {r}')
    if len(cpu) > 8:
        print(f'    ... ({len(cpu)-8} more)')
    print(f'  GPU ({len(gpu_lines)} rows):')
    for l in gpu_lines[:8]:
        print(f'    {l}')
    if len(gpu_lines) > 8:
        print(f'    ... ({len(gpu_lines)-8} more)')
    print()
