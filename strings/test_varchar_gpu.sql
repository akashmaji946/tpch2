-- Test VARCHAR/STRING GPU operations (RasterDB)
-- Run: /home/akashmaji/Device/IMPORTANT/rasterdb/build/release/duckdb -unsigned < /home/akashmaji/Device/IMPORTANT/tpch/strings/test_varchar_gpu.sql


.timer ON
-- Load extension
LOAD '/home/akashmaji/Device/IMPORTANT/rasterdb/build/release/extension/rasterdb/rasterdb.duckdb_extension';

-- ============================================================================
-- FILTER tests (VARCHAR comparisons)
-- ============================================================================

-- Filter: = (equality)
.print '=== Filter 1: VARCHAR = ==='
SELECT * FROM gpu_execution('SELECT n_nationkey, n_name FROM nation WHERE n_name = ''BRAZIL''');

-- Filter: != (inequality)
.print '=== Filter 2: VARCHAR != ==='
SELECT * FROM gpu_execution('SELECT n_nationkey, n_name FROM nation WHERE n_name != ''BRAZIL''');

-- Filter: < (less than — lexicographic)
.print '=== Filter 3: VARCHAR < ==='
SELECT * FROM gpu_execution('SELECT n_nationkey, n_name FROM nation WHERE n_name < ''FRANCE''');

-- Filter: > (greater than — lexicographic)
.print '=== Filter 4: VARCHAR > ==='
SELECT * FROM gpu_execution('SELECT n_nationkey, n_name FROM nation WHERE n_name > ''PERU''');

-- Filter: <= (less than or equal)
.print '=== Filter 5: VARCHAR <= ==='
SELECT * FROM gpu_execution('SELECT r_regionkey, r_name FROM region WHERE r_name <= ''EUROPE''');

-- Filter: >= (greater than or equal)
.print '=== Filter 6: VARCHAR >= ==='
SELECT * FROM gpu_execution('SELECT r_regionkey, r_name FROM region WHERE r_name >= ''EUROPE''');

-- ============================================================================
-- GROUP BY + AGGREGATE tests
-- ============================================================================

.print '=== GroupBy 1: VARCHAR key — nation ==='
SELECT * FROM gpu_execution('SELECT n_name, count(*) as cnt FROM nation GROUP BY n_name');

.print '=== GroupBy 2: VARCHAR key — customer mktsegment ==='
SELECT * FROM gpu_execution('SELECT c_mktsegment, count(*) as cnt FROM customer GROUP BY c_mktsegment');

-- ============================================================================
-- JOIN tests — integer key
-- ============================================================================

.print '=== Join 1: INT key — nation ⋈ region ON n_regionkey = r_regionkey ==='
SELECT * FROM gpu_execution('SELECT n.n_name, r.r_name FROM nation n INNER JOIN region r ON n.n_regionkey = r.r_regionkey LIMIT 10');

.print '=== Join 2: INT key + VARCHAR filter ==='
SELECT * FROM gpu_execution('SELECT n.n_name, n.n_nationkey FROM nation n INNER JOIN region r ON n.n_regionkey = r.r_regionkey WHERE r.r_name = ''EUROPE''');

-- ============================================================================
-- JOIN tests — string key
-- ============================================================================

.print '=== Join 3: STRING key — nation ⋈ nation self-join ON n_name = n_name ==='
SELECT * FROM gpu_execution('SELECT a.n_nationkey, a.n_name, b.n_regionkey FROM nation a INNER JOIN nation b ON a.n_name = b.n_name');

.print '=== Join 4: STRING key — region self-join ON r_name ==='
SELECT * FROM gpu_execution('SELECT a.r_regionkey AS r_key_a, a.r_name, b.r_regionkey AS r_key_b FROM region a INNER JOIN region b ON a.r_name = b.r_name');

.print '=== Join 5: STRING key + GROUP BY — nation self-join ON n_name, count ==='
SELECT * FROM gpu_execution('SELECT a.n_name, count(*) as cnt FROM nation a INNER JOIN nation b ON a.n_name = b.n_name GROUP BY a.n_name');

-- ============================================================================
-- ORDER BY tests (VARCHAR sort ASC / DESC)
-- ============================================================================

-- OrderBy: ASC
.print '=== OrderBy 1: VARCHAR ASC — nation names ascending ==='
SELECT * FROM gpu_execution('SELECT n_nationkey, n_name FROM nation ORDER BY n_name ASC');

-- OrderBy: DESC
.print '=== OrderBy 2: VARCHAR DESC — nation names descending ==='
SELECT * FROM gpu_execution('SELECT n_nationkey, n_name FROM nation ORDER BY n_name DESC');

-- OrderBy: ASC on region
.print '=== OrderBy 3: VARCHAR ASC — region names ascending ==='
SELECT * FROM gpu_execution('SELECT r_regionkey, r_name FROM region ORDER BY r_name ASC');

-- OrderBy: DESC on region
.print '=== OrderBy 4: VARCHAR DESC — region names descending ==='
SELECT * FROM gpu_execution('SELECT r_regionkey, r_name FROM region ORDER BY r_name DESC');

-- ============================================================================
-- BIG JOIN + ORDER BY tests (correctness at scale)
-- ============================================================================

-- Big Join 1: customer ⋈ nation (150K rows) — sort by nation name ASC
.print '=== Big Join+Sort 1: customer ⋈ nation, ORDER BY n_name ASC (150K rows, top 25) ==='
SELECT * FROM gpu_execution('SELECT n.n_name, count(*) as cnt FROM customer c INNER JOIN nation n ON c.c_nationkey = n.n_nationkey GROUP BY n.n_name ORDER BY n.n_name ASC');

-- Big Join 2: customer ⋈ nation ⋈ region — sort by region name DESC
.print '=== Big Join+Sort 2: customer ⋈ nation ⋈ region, ORDER BY r_name DESC ==='
SELECT * FROM gpu_execution('SELECT r.r_name, count(*) as cnt FROM customer c INNER JOIN nation n ON c.c_nationkey = n.n_nationkey INNER JOIN region r ON n.n_regionkey = r.r_regionkey GROUP BY r.r_name ORDER BY r.r_name DESC');

-- Big Join 3: supplier ⋈ nation (10K rows) — sort by nation name, show counts
.print '=== Big Join+Sort 3: supplier ⋈ nation, ORDER BY n_name ASC ==='
SELECT * FROM gpu_execution('SELECT n.n_name, count(*) as cnt FROM supplier s INNER JOIN nation n ON s.s_nationkey = n.n_nationkey GROUP BY n.n_name ORDER BY n.n_name ASC');

SELECT * FROM gpu_execution('SELECT * FROM supplier s INNER JOIN nation n ON s.s_nationkey = n.n_nationkey');

-- -- Big Join 4: customer ⋈ orders (large join) — group by mktsegment, sort DESC
.print '=== Big Join+Sort 4: customer ⋈ orders, GROUP BY c_mktsegment ORDER BY c_mktsegment DESC ==='
SELECT * FROM gpu_execution('SELECT c.c_mktsegment, count(*) as cnt FROM orders o INNER JOIN customer c ON o.o_custkey = c.c_custkey GROUP BY c.c_mktsegment ORDER BY c.c_mktsegment DESC');

SELECT * FROM gpu_execution('SELECT * FROM orders o INNER JOIN customer c ON o.o_custkey = c.c_custkey LIMIT 100;');

-- Big Join 5: supplier ⋈ nation ⋈ region — full pipeline, sort by r_name ASC
.print '=== Big Join+Sort 5: supplier ⋈ nation ⋈ region, ORDER BY r_name ASC ==='
SELECT * FROM gpu_execution('SELECT r.r_name, count(*) as cnt FROM supplier s INNER JOIN nation n ON s.s_nationkey = n.n_nationkey INNER JOIN region r ON n.n_regionkey = r.r_regionkey GROUP BY r.r_name ORDER BY r.r_name ASC');

-- Big Sort 1: orders table — sort by o_orderpriority ASC (1.5M rows, grouped)
.print '=== Big Sort 1: orders GROUP BY o_orderpriority ORDER BY o_orderpriority ASC ==='
SELECT * FROM gpu_execution('SELECT o_orderpriority, count(*) as cnt FROM orders GROUP BY o_orderpriority ORDER BY o_orderpriority ASC');

-- Big Sort 2: customer mktsegment — sort DESC
.print '=== Big Sort 2: customer GROUP BY c_mktsegment ORDER BY c_mktsegment DESC ==='
SELECT * FROM gpu_execution('SELECT c_mktsegment, count(*) as cnt FROM customer GROUP BY c_mktsegment ORDER BY c_mktsegment DESC');

-- ============================================================================
-- Reference: raw tables
-- ============================================================================
-- .print '=== Ref: All nations ==='
-- SELECT * from nation;

-- .print '=== Ref: All regions ==='
-- SELECT * from region;

.print '=== All VARCHAR GPU tests completed ==='
