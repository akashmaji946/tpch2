#!/bin/bash
# Run VARCHAR string tests using pre-built TPC-H databases
# Usage: ./run.sh -r -sf=1    (rasterdb GPU, scale factor 1)
#        ./run.sh -s -sf=10   (sirius, scale factor 10)
#        ./run.sh -c -sf=1    (CPU DuckDB, scale factor 1)
#        ./run.sh -a -sf=1    (all three, scale factor 1)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TPCH_DIR="~/Device/IMPORTANT/tpch"
DUCKDB_RDB="~/Device/IMPORTANT/rasterdb/build/release/duckdb"
DUCKDB_SIRIUS="~/Device/IMPORTANT/sirius/build/release/duckdb"
DUCKDB_CPU="~/Device/IMPORTANT/sirius/build/release/duckdb"

export RASTERDF_SHADER_DIR="~/Device/IMPORTANT/rasterdf/shaders/compiled"

# Parse arguments
ENGINE=""
SF=1
for arg in "$@"; do
    case "$arg" in
        -r|-s|-c|-a) ENGINE="$arg" ;;
        -sf=*) SF="${arg#-sf=}" ;;
    esac
done

if [ -z "$ENGINE" ]; then
    echo "Usage: $0 <-r|-s|-c|-a> -sf=<scale_factor>"
    echo "  -r      RasterDB GPU"
    echo "  -s      Sirius"
    echo "  -c      CPU DuckDB"
    echo "  -a      All three"
    echo "  -sf=N   Scale factor (default: 1)"
    echo ""
    echo "Available databases:"
    ls "$TPCH_DIR"/tpch_sf*.db 2>/dev/null | sed 's/.*tpch_sf/  sf/' | sed 's/\.db//'
    exit 1
fi

DB_FILE="$TPCH_DIR/tpch_sf${SF}.db"
if [ ! -f "$DB_FILE" ]; then
    echo "ERROR: Database not found: $DB_FILE"
    echo "Available databases:"
    ls "$TPCH_DIR"/tpch_sf*.db 2>/dev/null | sed 's/.*tpch_sf/  sf/' | sed 's/\.db//'
    exit 1
fi

echo "Using TPC-H SF${SF} database: $DB_FILE"
echo ""

run_gpu() {
    echo "========================================"
    echo "  Running: RasterDB GPU (rasterdf) SF${SF}"
    echo "========================================"
    "$DUCKDB_RDB" -unsigned "$DB_FILE" < "$SCRIPT_DIR/test_varchar_gpu.sql"
}

run_sirius() {
    echo "========================================"
    echo "  Running: Sirius SF${SF}"
    echo "========================================"
    "$DUCKDB_SIRIUS" -unsigned "$DB_FILE" < "$SCRIPT_DIR/test_varchar_sirius.sql"
}

run_cpu() {
    echo "========================================"
    echo "  Running: CPU DuckDB SF${SF}"
    echo "========================================"
    "$DUCKDB_CPU" "$DB_FILE" < "$SCRIPT_DIR/test_varchar_cpu.sql"
}

case "$ENGINE" in
    -r) run_gpu ;;
    -s) run_sirius ;;
    -c) run_cpu ;;
    -a) run_gpu; echo; run_sirius; echo; run_cpu ;;
    *)  echo "Unknown option: $ENGINE"; exit 1 ;;
esac
