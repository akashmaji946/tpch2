-- Test VARCHAR/STRING operations on Sirius (exp branch — uses gpu_processing API)
-- Run: ~/Device/IMPORTANT/sirius/build/release/duckdb -unsigned < ~/Device/IMPORTANT/tpch/strings/test_varchar_sirius.sql

.timer ON

SELECT * FROM gpu_buffer_init('12GB', '8GB');

-- ============================================================================
-- FILTER tests (VARCHAR comparisons)
-- ============================================================================

-- -- Filter: = (equality)
-- .print '=== Filter 1: VARCHAR = ==='
-- SELECT * FROM gpu_processing('SELECT n_nationkey, n_name FROM nation WHERE n_name = ''BRAZIL''');

-- -- Filter: != (inequality)
-- .print '=== Filter 2: VARCHAR != ==='
-- SELECT * FROM gpu_processing('SELECT n_nationkey, n_name FROM nation WHERE n_name != ''BRAZIL''');

-- -- Filter: < (less than — lexicographic)
-- .print '=== Filter 3: VARCHAR < ==='
-- SELECT * FROM gpu_processing('SELECT n_nationkey, n_name FROM nation WHERE n_name < ''FRANCE''');

-- -- Filter: > (greater than — lexicographic)
-- .print '=== Filter 4: VARCHAR > ==='
-- SELECT * FROM gpu_processing('SELECT n_nationkey, n_name FROM nation WHERE n_name > ''PERU''');

-- -- Filter: <= (less than or equal)
-- .print '=== Filter 5: VARCHAR <= ==='
-- SELECT * FROM gpu_processing('SELECT r_regionkey, r_name FROM region WHERE r_name <= ''EUROPE''');

-- -- Filter: >= (greater than or equal)
-- .print '=== Filter 6: VARCHAR >= ==='
-- SELECT * FROM gpu_processing('SELECT r_regionkey, r_name FROM region WHERE r_name >= ''EUROPE''');

-- -- ============================================================================
-- -- GROUP BY + AGGREGATE tests
-- -- ============================================================================

-- .print '=== GroupBy 1: VARCHAR key — nation ==='
-- SELECT * FROM gpu_processing('SELECT n_name, count(*) as cnt FROM nation GROUP BY n_name');

-- .print '=== GroupBy 2: VARCHAR key — customer mktsegment ==='
-- SELECT * FROM gpu_processing('SELECT c_mktsegment, count(*) as cnt FROM customer GROUP BY c_mktsegment');

-- -- ============================================================================
-- -- JOIN tests — integer key
-- -- ============================================================================

-- .print '=== Join 1: INT key — nation ⋈ region ON n_regionkey = r_regionkey ==='
-- SELECT * FROM gpu_processing('SELECT n.n_name, r.r_name FROM nation n INNER JOIN region r ON n.n_regionkey = r.r_regionkey LIMIT 10');

-- .print '=== Join 2: INT key + VARCHAR filter ==='
-- SELECT * FROM gpu_processing('SELECT n.n_name, n.n_nationkey FROM nation n INNER JOIN region r ON n.n_regionkey = r.r_regionkey WHERE r.r_name = ''EUROPE''');

-- -- ============================================================================
-- -- JOIN tests — string key
-- -- ============================================================================

-- .print '=== Join 3: STRING key — nation ⋈ nation self-join ON n_name = n_name ==='
-- SELECT * FROM gpu_processing('SELECT a.n_nationkey, a.n_name, b.n_regionkey FROM nation a INNER JOIN nation b ON a.n_name = b.n_name');

-- .print '=== Join 4: STRING key — region self-join ON r_name ==='
-- SELECT * FROM gpu_processing('SELECT a.r_regionkey, a.r_name, b.r_regionkey FROM region a INNER JOIN region b ON a.r_name = b.r_name');

-- .print '=== Join 5: STRING key + GROUP BY — nation self-join ON n_name, count ==='
-- SELECT * FROM gpu_processing('SELECT a.n_name, count(*) as cnt FROM nation a INNER JOIN nation b ON a.n_name = b.n_name GROUP BY a.n_name');

.print '=== Big Join+Sort 4: customer ⋈ orders, GROUP BY c_mktsegment ORDER BY c_mktsegment DESC ==='
SELECT * FROM gpu_processing('SELECT c.c_mktsegment, count(*) as cnt FROM orders o INNER JOIN customer c ON o.o_custkey = c.c_custkey GROUP BY c.c_mktsegment ORDER BY c.c_mktsegment DESC');

-- SELECT * FROM gpu_processing('SELECT * FROM orders o INNER JOIN customer c ON o.o_custkey = c.c_custkey LIMIT 100;');

-- ============================================================================
-- Reference: raw tables
-- ============================================================================
-- .print '=== Ref: All nations ==='
-- SELECT * from nation;

-- .print '=== Ref: All regions ==='
-- SELECT * from region;

.print '=== All VARCHAR Sirius tests completed ==='
