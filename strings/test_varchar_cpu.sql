-- Test VARCHAR/STRING operations on CPU (plain DuckDB)
-- Run: duckdb < /home/akashmaji/Device/IMPORTANT/tpch/strings/test_varchar_cpu.sql

.timer ON

-- ============================================================================
-- FILTER tests (VARCHAR comparisons)
-- ============================================================================

.print '=== Filter 1: VARCHAR = ==='
SELECT n_nationkey, n_name FROM nation WHERE n_name = 'BRAZIL';

.print '=== Filter 2: VARCHAR != ==='
SELECT n_nationkey, n_name FROM nation WHERE n_name != 'BRAZIL';

.print '=== Filter 3: VARCHAR < ==='
SELECT n_nationkey, n_name FROM nation WHERE n_name < 'FRANCE';

.print '=== Filter 4: VARCHAR > ==='
SELECT n_nationkey, n_name FROM nation WHERE n_name > 'PERU';

.print '=== Filter 5: VARCHAR <= ==='
SELECT r_regionkey, r_name FROM region WHERE r_name <= 'EUROPE';

.print '=== Filter 6: VARCHAR >= ==='
SELECT r_regionkey, r_name FROM region WHERE r_name >= 'EUROPE';

-- ============================================================================
-- GROUP BY + AGGREGATE tests
-- ============================================================================

.print '=== GroupBy 1: VARCHAR key — nation ==='
SELECT n_name, count(*) as cnt FROM nation GROUP BY n_name;

.print '=== GroupBy 2: VARCHAR key — customer mktsegment ==='
SELECT c_mktsegment, count(*) as cnt FROM customer GROUP BY c_mktsegment;

-- ============================================================================
-- JOIN tests — integer key
-- ============================================================================

.print '=== Join 1: INT key — nation ⋈ region ON n_regionkey = r_regionkey ==='
SELECT n.n_name, r.r_name FROM nation n INNER JOIN region r ON n.n_regionkey = r.r_regionkey LIMIT 10;

.print '=== Join 2: INT key + VARCHAR filter ==='
SELECT n.n_name, n.n_nationkey FROM nation n INNER JOIN region r ON n.n_regionkey = r.r_regionkey WHERE r.r_name = 'EUROPE';

-- ============================================================================
-- JOIN tests — string key
-- ============================================================================

.print '=== Join 3: STRING key — nation ⋈ nation self-join ON n_name = n_name ==='
SELECT a.n_nationkey, a.n_name, b.n_regionkey FROM nation a INNER JOIN nation b ON a.n_name = b.n_name;

.print '=== Join 4: STRING key — region self-join ON r_name ==='
SELECT a.r_regionkey, a.r_name, b.r_regionkey FROM region a INNER JOIN region b ON a.r_name = b.r_name;

.print '=== Join 5: STRING key + GROUP BY — nation self-join ON n_name, count ==='
SELECT a.n_name, count(*) as cnt FROM nation a INNER JOIN nation b ON a.n_name = b.n_name GROUP BY a.n_name;

-- ============================================================================
-- Reference: raw tables
-- ============================================================================
-- .print '=== Ref: All nations ==='
-- SELECT * from nation;

-- .print '=== Ref: All regions ==='
-- SELECT * from region;

.print '=== All VARCHAR CPU tests completed ==='
