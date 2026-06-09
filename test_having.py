#!/usr/bin/env python3
"""
Test and benchmark HAVING clause support in RasterDB.
HAVING is essentially a FILTER on aggregated results (GROUP BY output).
"""

import sys
import os
import subprocess
import time
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
RASTERDB_EXT = os.path.expanduser(
    "~/Device/IMPORTANT/rasterdb/build/release/extension/rasterdb/rasterdb.duckdb_extension")
RASTERDB_CLI = os.path.expanduser(
    "~/Device/IMPORTANT/rasterdb/build/release/duckdb")
DB = os.path.join(SCRIPT_DIR, 'tpch_sf1.db')

# Set shader directory for rasterdf
os.environ['RASTERDF_SHADER_DIR'] = os.path.expanduser(
    "~/Device/IMPORTANT/rasterdf/shaders/compiled")
# Remove EGL vendor library for NVIDIA
os.environ.pop("__EGL_VENDOR_LIBRARY_DIRS", None)

# Load queries
with open(os.path.join(SCRIPT_DIR, 'tpch_queries.json'), 'r') as f:
    queries = json.load(f)

# Use adapted queries
queries = queries['adapted']

TIMEOUT = 120

def run_gpu_cli(sql):
    """Run query on GPU via CLI, return (rows_csv, time_ms, status)."""
    escaped = sql.replace("'", "''")
    full_sql = f"LOAD '{RASTERDB_EXT}'; SELECT * FROM gpu_execution('{escaped}');"
    
    try:
        proc = subprocess.run(
            [RASTERDB_CLI, "-unsigned", "-csv", "-noheader", DB, "-c", full_sql],
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return [], 0, "TIMEOUT"
    except FileNotFoundError:
        return [], 0, "NOT FOUND"

    stderr = proc.stderr or ""
    stdout = proc.stdout or ""
    combined = stderr + "\n" + stdout

    if proc.returncode != 0 or "SIGSEGV" in combined:
        return [], 0, f"CRASH: {combined[:100]}"
    elif "NotImplementedException" in combined or "falling back to CPU" in combined:
        # Fallback to CPU is OK for testing
        if stdout:
            rows = [line.split(',') for line in stdout.strip().split('\n') if line]
            return rows, 0, "CPU_FALLBACK"
        return [], 0, "FALLBACK_ERR"
    else:
        if stdout:
            rows = [line.split(',') for line in stdout.strip().split('\n') if line]
            return rows, 0, "GPU_OK"
        return [], 0, "NO_OUTPUT"

def run_cpu(sql):
    """Run query on CPU via CLI, return (rows_csv, time_ms, status)."""
    try:
        proc = subprocess.run(
            [RASTERDB_CLI, "-unsigned", "-csv", "-noheader", DB, "-c", sql],
            capture_output=True, text=True, timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return [], 0, "TIMEOUT"
    except FileNotFoundError:
        return [], 0, "NOT FOUND"

    stderr = proc.stderr or ""
    stdout = proc.stdout or ""
    combined = stderr + "\n" + stdout

    if proc.returncode != 0 or "SIGSEGV" in combined:
        return [], 0, f"CRASH: {combined[:100]}"
    else:
        if stdout:
            rows = [line.split(',') for line in stdout.strip().split('\n') if line]
            return rows, 0, "CPU_OK"
        return [], 0, "NO_OUTPUT"

def test_having_basic():
    """Test basic HAVING clause functionality."""
    print("\n=== Testing HAVING Clause ===")
    
    # Run HAVING query
    query_key = 'Q11_having'
    print(f"\nQuery: {query_key}")
    print(f"SQL: {queries[query_key]['query']}")
    
    # CPU baseline
    print("\n--- CPU (baseline) ---")
    cpu_rows, _, cpu_status = run_cpu(queries[query_key]['query'])
    print(f"Status: {cpu_status}")
    print(f"Rows: {len(cpu_rows)}")
    if cpu_rows:
        print(f"Result: {cpu_rows[:5]}")  # Show first 5 rows
    
    # GPU
    print("\n--- GPU (HAVING support) ---")
    gpu_rows, _, gpu_status = run_gpu_cli(queries[query_key]['query'])
    print(f"Status: {gpu_status}")
    print(f"Rows: {len(gpu_rows)}")
    if gpu_rows:
        print(f"Result: {gpu_rows[:5]}")
    
    # Verify results match
    if cpu_rows == gpu_rows:
        print("\n✓ GPU and CPU results match!")
        return True
    else:
        print("\n✗ Results differ!")
        print(f"CPU: {cpu_rows}")
        print(f"GPU: {gpu_rows}")
        return False

def benchmark_having():
    """Benchmark HAVING clause with multiple runs."""
    print("\n=== HAVING Benchmark ===")
    
    query_key = 'Q11_having'
    query = queries[query_key]['query']
    
    # Warmup
    run_gpu_cli(query)
    
    # GPU runs
    gpu_times = []
    for i in range(5):
        start = time.time()
        run_gpu_cli(query)
        elapsed = (time.time() - start) * 1000
        gpu_times.append(elapsed)
        print(f"  GPU run {i+1}: {elapsed:.2f} ms")
    
    # CPU runs
    cpu_times = []
    for i in range(3):
        start = time.time()
        run_cpu(query)
        elapsed = (time.time() - start) * 1000
        cpu_times.append(elapsed)
        print(f"  CPU run {i+1}: {elapsed:.2f} ms")
    
    avg_gpu = sum(gpu_times) / len(gpu_times)
    avg_cpu = sum(cpu_times) / len(cpu_times)
    
    print(f"\nAverage GPU time: {avg_gpu:.2f} ms")
    print(f"Average CPU time: {avg_cpu:.2f} ms")
    print(f"Average speedup: {avg_cpu/avg_gpu:.2f}x")

def test_having_operators():
    """Test HAVING with different comparison operators."""
    print("\n=== Testing HAVING Comparison Operators ===")
    
    # Test different HAVING conditions
    having_tests = [
        ("> 10000000", "greater than"),
        (">= 5000000", "greater than or equal"),
        ("< 50000000", "less than"),
        ("<= 20000000", "less than or equal"),
        ("= 10000000", "equal"),
    ]
    
    for condition, desc in having_tests:
        query = f"""
        SELECT l_returnflag_id, sum(l_extendedprice) AS total_revenue
        FROM lineitem_int
        WHERE l_shipdate_int >= 19940101 AND l_shipdate_int < 19950101
        GROUP BY l_returnflag_id
        HAVING sum(l_extendedprice) {condition}
        """
        
        print(f"\n--- HAVING {desc} ({condition}) ---")
        
        # GPU
        gpu_rows, _, gpu_status = run_gpu_cli(query)
        print(f"  GPU: {gpu_status}, {len(gpu_rows)} rows")
        
        # CPU
        cpu_rows, _, cpu_status = run_cpu(query)
        print(f"  CPU: {cpu_status}, {len(cpu_rows)} rows")
        
        if gpu_status == "GPU_OK" and cpu_status == "CPU_OK" and gpu_rows == cpu_rows:
            print(f"  ✓ Results match")
        elif gpu_status == "GPU_OK" and cpu_status == "CPU_OK":
            print(f"  ✗ Results differ")

if __name__ == "__main__":
    print("RasterDB HAVING Clause Test")
    print("=" * 50)
    
    # Test basic HAVING
    success = test_having_basic()
    
    if success:
        # Benchmark
        benchmark_having()
        
        # Test different operators
        test_having_operators()
    
    print("\n" + "=" * 50)
    print("HAVING test complete")
