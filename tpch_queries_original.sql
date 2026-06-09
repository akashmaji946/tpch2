-- ============================================================================
-- TPC-H Standard Benchmark Queries (All 22)
-- Reference: TPC Benchmark™ H Standard Specification Revision 3.0.1
--
-- These are the ORIGINAL queries using standard TPC-H schema with
-- VARCHAR, DATE, DECIMAL types. They require DuckDB's tpch tables
-- generated via: INSTALL tpch; LOAD tpch; CALL dbgen(sf=1);
--
-- Feature requirements per query:
--   Q1:  GROUP BY, aggregate, filter (DATE)
--   Q2:  correlated subquery, multi-join, ORDER BY, LIMIT, LIKE
--   Q3:  3-way JOIN, filter (DATE, VARCHAR), GROUP BY, ORDER BY, LIMIT
--   Q4:  EXISTS subquery, filter (DATE), GROUP BY, ORDER BY
--   Q5:  6-way JOIN, filter (DATE, VARCHAR), GROUP BY, ORDER BY
--   Q6:  filter (DATE, DECIMAL), aggregate (simplest query)
--   Q7:  CASE WHEN, multi-join, filter (VARCHAR, DATE), GROUP BY, ORDER BY
--   Q8:  CASE WHEN, 8-way JOIN, filter, GROUP BY, ORDER BY
--   Q9:  CASE WHEN, LIKE, 6-way JOIN, GROUP BY, ORDER BY
--   Q10: 4-way JOIN, filter (DATE), GROUP BY, ORDER BY, LIMIT
--   Q11: HAVING, subquery, multi-join, GROUP BY, ORDER BY
--   Q12: CASE WHEN, IN, filter (DATE), GROUP BY, ORDER BY
--   Q13: LEFT OUTER JOIN, subquery, GROUP BY, ORDER BY
--   Q14: CASE WHEN, filter (DATE), aggregate
--   Q15: CREATE VIEW, subquery, multi-join (view)
--   Q16: DISTINCT, NOT IN subquery, GROUP BY, ORDER BY
--   Q17: correlated subquery, AVG, JOIN
--   Q18: IN subquery, HAVING, multi-join, GROUP BY, ORDER BY, LIMIT
--   Q19: OR, BETWEEN, IN, multi-condition filter, JOIN
--   Q20: EXISTS, IN subquery, multi-join, filter (DATE, LIKE)
--   Q21: EXISTS, NOT EXISTS, multi-join, GROUP BY, ORDER BY, LIMIT
--   Q22: NOT EXISTS, CASE WHEN, SUBSTRING, IN subquery, GROUP BY, ORDER BY
-- ============================================================================

-- Q1: Pricing Summary Report
-- Features: GROUP BY, SUM, AVG, COUNT, filter on DATE
SELECT
    l_returnflag,
    l_linestatus,
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
ORDER BY l_returnflag, l_linestatus;

---------------------------------------------------------
SELECT l_returnflag_id, 
        l_linestatus_id, 
        sum(l_quantity) as sum_qty, 
        sum(l_extendedprice) as sum_base_price, 
        count(*) as count_order 
FROM lineitem_int 
WHERE l_shipdate_int <= 19980902 
GROUP BY l_returnflag_id, l_linestatus_id
---------------------------------------------------------

-- Q2: Minimum Cost Supplier
-- Features: correlated subquery, 5-way JOIN, ORDER BY, LIMIT, LIKE
SELECT
    s_acctbal, s_name, n_name, p_partkey, p_mfgr,
    s_address, s_phone, s_comment
FROM part, supplier, partsupp, nation, region
WHERE
    p_partkey = ps_partkey
    AND s_suppkey = ps_suppkey
    AND p_size = 15
    AND p_type LIKE '%BRASS'
    AND s_nationkey = n_nationkey
    AND n_regionkey = r_regionkey
    AND r_name = 'EUROPE'
    AND ps_supplycost = (
        SELECT min(ps_supplycost)
        FROM partsupp, supplier, nation, region
        WHERE
            p_partkey = ps_partkey
            AND s_suppkey = ps_suppkey
            AND s_nationkey = n_nationkey
            AND n_regionkey = r_regionkey
            AND r_name = 'EUROPE'
    )
ORDER BY s_acctbal DESC, n_name, s_name, p_partkey
LIMIT 100;


-- Q3: Shipping Priority
-- Features: 3-way JOIN, filter (DATE, VARCHAR), GROUP BY, ORDER BY, LIMIT
SELECT
    l_orderkey,
    sum(l_extendedprice * (1 - l_discount)) as revenue,
    o_orderdate,
    o_shippriority
FROM customer, orders, lineitem
WHERE
    c_mktsegment = 'BUILDING'
    AND c_custkey = o_custkey
    AND l_orderkey = o_orderkey
    AND o_orderdate < DATE '1995-03-15'
    AND l_shipdate > DATE '1995-03-15'
GROUP BY l_orderkey, o_orderdate, o_shippriority
ORDER BY revenue DESC, o_orderdate
LIMIT 10;

SELECT l.l_orderkey, 
    sum(l.l_extendedprice * (1.0 - l.l_discount)) as revenue, 
    o.o_orderdate_int, 
    o.o_shippriority 
FROM lineitem_int l INNER JOIN orders_int o ON l.l_orderkey = o.o_orderkey INNER JOIN customer_int c ON c.c_custkey = o.o_custkey 
WHERE c.c_mktsegment_id = 2 
        AND o.o_orderdate_int < 19950315 
        AND l.l_shipdate_int > 19950315 
GROUP BY l.l_orderkey, o.o_orderdate_int, o.o_shippriority 
ORDER BY revenue DESC, o.o_orderdate_int

-- Q4: Order Priority Checking
-- Features: EXISTS subquery, filter (DATE), GROUP BY, ORDER BY
SELECT
    o_orderpriority,
    count(*) as order_count
FROM orders
WHERE
    o_orderdate >= DATE '1993-07-01'
    AND o_orderdate < DATE '1993-07-01' + INTERVAL '3' MONTH
    AND EXISTS (
        SELECT * FROM lineitem
        WHERE l_orderkey = o_orderkey AND l_commitdate < l_receiptdate
    )
GROUP BY o_orderpriority
ORDER BY o_orderpriority;


-- Q5: Local Supplier Volume
-- Features: 6-way JOIN, filter (DATE, VARCHAR), GROUP BY, ORDER BY
SELECT
    n_name,
    sum(l_extendedprice * (1 - l_discount)) as revenue
FROM customer, orders, lineitem, supplier, nation, region
WHERE
    c_custkey = o_custkey
    AND l_orderkey = o_orderkey
    AND l_suppkey = s_suppkey
    AND c_nationkey = s_nationkey
    AND s_nationkey = n_nationkey
    AND n_regionkey = r_regionkey
    AND r_name = 'ASIA'
    AND o_orderdate >= DATE '1994-01-01'
    AND o_orderdate < DATE '1994-01-01' + INTERVAL '1' YEAR
GROUP BY n_name
ORDER BY revenue DESC;


-- Q6: Forecasting Revenue Change
-- Features: filter (DATE, DECIMAL range), SUM aggregate
-- This is the SIMPLEST TPC-H query.
SELECT
    sum(l_extendedprice * l_discount) as revenue
FROM lineitem
WHERE
    l_shipdate >= DATE '1994-01-01'
    AND l_shipdate < DATE '1994-01-01' + INTERVAL '1' YEAR
    AND l_discount BETWEEN 0.06 - 0.01 AND 0.06 + 0.01
    AND l_quantity < 24;


-- Q7: Volume Shipping
-- Features: CASE WHEN, multi-join, filter (VARCHAR, DATE), GROUP BY, ORDER BY
SELECT
    supp_nation, cust_nation, l_year, sum(volume) as revenue
FROM (
    SELECT
        n1.n_name as supp_nation,
        n2.n_name as cust_nation,
        EXTRACT(YEAR FROM l_shipdate) as l_year,
        l_extendedprice * (1 - l_discount) as volume
    FROM supplier, lineitem, orders, customer, nation n1, nation n2
    WHERE
        s_suppkey = l_suppkey
        AND o_orderkey = l_orderkey
        AND c_custkey = o_custkey
        AND s_nationkey = n1.n_nationkey
        AND c_nationkey = n2.n_nationkey
        AND (
            (n1.n_name = 'FRANCE' AND n2.n_name = 'GERMANY')
            OR (n1.n_name = 'GERMANY' AND n2.n_name = 'FRANCE')
        )
        AND l_shipdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31'
) as shipping
GROUP BY supp_nation, cust_nation, l_year
ORDER BY supp_nation, cust_nation, l_year;


-- Q8: National Market Share
-- Features: CASE WHEN, 8-way JOIN, subquery, GROUP BY, ORDER BY
SELECT
    o_year,
    sum(CASE WHEN nation = 'BRAZIL' THEN volume ELSE 0 END) / sum(volume) as mkt_share
FROM (
    SELECT
        EXTRACT(YEAR FROM o_orderdate) as o_year,
        l_extendedprice * (1 - l_discount) as volume,
        n2.n_name as nation
    FROM part, supplier, lineitem, orders, customer, nation n1, nation n2, region
    WHERE
        p_partkey = l_partkey
        AND s_suppkey = l_suppkey
        AND l_orderkey = o_orderkey
        AND o_custkey = c_custkey
        AND c_nationkey = n1.n_nationkey
        AND n1.n_regionkey = r_regionkey
        AND r_name = 'AMERICA'
        AND s_nationkey = n2.n_nationkey
        AND o_orderdate BETWEEN DATE '1995-01-01' AND DATE '1996-12-31'
        AND p_type = 'ECONOMY ANODIZED STEEL'
) as all_nations
GROUP BY o_year
ORDER BY o_year;


-- Q9: Product Type Profit Measure
-- Features: CASE WHEN, LIKE, 6-way JOIN, GROUP BY, ORDER BY
SELECT
    nation, o_year, sum(amount) as sum_profit
FROM (
    SELECT
        n_name as nation,
        EXTRACT(YEAR FROM o_orderdate) as o_year,
        l_extendedprice * (1 - l_discount) - ps_supplycost * l_quantity as amount
    FROM part, supplier, lineitem, partsupp, orders, nation
    WHERE
        s_suppkey = l_suppkey
        AND ps_suppkey = l_suppkey
        AND ps_partkey = l_partkey
        AND p_partkey = l_partkey
        AND o_orderkey = l_orderkey
        AND s_nationkey = n_nationkey
        AND p_name LIKE '%green%'
) as profit
GROUP BY nation, o_year
ORDER BY nation, o_year DESC;


-- Q10: Returned Item Reporting
-- Features: 4-way JOIN, filter (DATE, VARCHAR), GROUP BY, ORDER BY, LIMIT
SELECT
    c_custkey, c_name,
    sum(l_extendedprice * (1 - l_discount)) as revenue,
    c_acctbal, n_name, c_address, c_phone, c_comment
FROM customer, orders, lineitem, nation
WHERE
    c_custkey = o_custkey
    AND l_orderkey = o_orderkey
    AND o_orderdate >= DATE '1993-10-01'
    AND o_orderdate < DATE '1993-10-01' + INTERVAL '3' MONTH
    AND l_returnflag = 'R'
    AND c_nationkey = n_nationkey
GROUP BY c_custkey, c_name, c_acctbal, c_phone, n_name, c_address, c_comment
ORDER BY revenue DESC
LIMIT 20;


-- Q11: Important Stock Identification
-- Features: HAVING, subquery, 3-way JOIN, GROUP BY, ORDER BY
SELECT
    ps_partkey,
    sum(ps_supplycost * ps_availqty) as value
FROM partsupp, supplier, nation
WHERE
    ps_suppkey = s_suppkey
    AND s_nationkey = n_nationkey
    AND n_name = 'GERMANY'
GROUP BY ps_partkey
HAVING sum(ps_supplycost * ps_availqty) > (
    SELECT sum(ps_supplycost * ps_availqty) * 0.0001
    FROM partsupp, supplier, nation
    WHERE
        ps_suppkey = s_suppkey
        AND s_nationkey = n_nationkey
        AND n_name = 'GERMANY'
)
ORDER BY value DESC;


-- Q12: Shipping Modes and Order Priority
-- Features: CASE WHEN, IN, filter (DATE), GROUP BY, ORDER BY
SELECT
    l_shipmode,
    sum(CASE
        WHEN o_orderpriority = '1-URGENT' OR o_orderpriority = '2-HIGH'
        THEN 1 ELSE 0
    END) as high_line_count,
    sum(CASE
        WHEN o_orderpriority <> '1-URGENT' AND o_orderpriority <> '2-HIGH'
        THEN 1 ELSE 0
    END) as low_line_count
FROM orders, lineitem
WHERE
    o_orderkey = l_orderkey
    AND l_shipmode IN ('MAIL', 'SHIP')
    AND l_commitdate < l_receiptdate
    AND l_shipdate < l_commitdate
    AND l_receiptdate >= DATE '1994-01-01'
    AND l_receiptdate < DATE '1994-01-01' + INTERVAL '1' YEAR
GROUP BY l_shipmode
ORDER BY l_shipmode;


-- Q13: Customer Distribution
-- Features: LEFT OUTER JOIN, subquery, GROUP BY, ORDER BY
SELECT
    c_count, count(*) as custdist
FROM (
    SELECT c_custkey, count(o_orderkey) as c_count
    FROM customer LEFT OUTER JOIN orders ON
        c_custkey = o_custkey
        AND o_comment NOT LIKE '%special%requests%'
    GROUP BY c_custkey
) as c_orders
GROUP BY c_count
ORDER BY custdist DESC, c_count DESC;


-- Q14: Promotion Effect
-- Features: CASE WHEN, filter (DATE), aggregate, JOIN
SELECT
    100.00 * sum(CASE
        WHEN p_type LIKE 'PROMO%'
        THEN l_extendedprice * (1 - l_discount)
        ELSE 0
    END) / sum(l_extendedprice * (1 - l_discount)) as promo_revenue
FROM lineitem, part
WHERE
    l_partkey = p_partkey
    AND l_shipdate >= DATE '1995-09-01'
    AND l_shipdate < DATE '1995-09-01' + INTERVAL '1' MONTH;


-- Q15: Top Supplier
-- Features: CREATE VIEW, subquery, multi-join
-- Note: Standard Q15 uses a view; here we use a CTE instead.
WITH revenue0 AS (
    SELECT
        l_suppkey as supplier_no,
        sum(l_extendedprice * (1 - l_discount)) as total_revenue
    FROM lineitem
    WHERE
        l_shipdate >= DATE '1996-01-01'
        AND l_shipdate < DATE '1996-01-01' + INTERVAL '3' MONTH
    GROUP BY l_suppkey
)
SELECT s_suppkey, s_name, s_address, s_phone, total_revenue
FROM supplier, revenue0
WHERE
    s_suppkey = supplier_no
    AND total_revenue = (SELECT max(total_revenue) FROM revenue0)
ORDER BY s_suppkey;


-- Q16: Parts/Supplier Relationship
-- Features: DISTINCT, NOT IN subquery, GROUP BY, ORDER BY, LIKE
SELECT
    p_brand, p_type, p_size,
    count(DISTINCT ps_suppkey) as supplier_cnt
FROM partsupp, part
WHERE
    p_partkey = ps_partkey
    AND p_brand <> 'Brand#45'
    AND p_type NOT LIKE 'MEDIUM POLISHED%'
    AND p_size IN (49, 14, 23, 45, 19, 3, 36, 9)
    AND ps_suppkey NOT IN (
        SELECT s_suppkey FROM supplier WHERE s_comment LIKE '%Customer%Complaints%'
    )
GROUP BY p_brand, p_type, p_size
ORDER BY supplier_cnt DESC, p_brand, p_type, p_size;


-- Q17: Small-Quantity-Order Revenue
-- Features: correlated subquery, AVG, JOIN
SELECT
    sum(l_extendedprice) / 7.0 as avg_yearly
FROM lineitem, part
WHERE
    p_partkey = l_partkey
    AND p_brand = 'Brand#23'
    AND p_container = 'MED BOX'
    AND l_quantity < (
        SELECT 0.2 * avg(l_quantity)
        FROM lineitem
        WHERE l_partkey = p_partkey
    );


-- Q18: Large Volume Customer
-- Features: IN subquery, HAVING, multi-join, GROUP BY, ORDER BY, LIMIT
SELECT
    c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice,
    sum(l_quantity)
FROM customer, orders, lineitem
WHERE
    o_orderkey IN (
        SELECT l_orderkey FROM lineitem
        GROUP BY l_orderkey
        HAVING sum(l_quantity) > 300
    )
    AND c_custkey = o_custkey
    AND o_orderkey = l_orderkey
GROUP BY c_name, c_custkey, o_orderkey, o_orderdate, o_totalprice
ORDER BY o_totalprice DESC, o_orderdate
LIMIT 100;


-- Q19: Discounted Revenue
-- Features: OR, BETWEEN, IN, multi-condition filter, JOIN
SELECT
    sum(l_extendedprice * (1 - l_discount)) as revenue
FROM lineitem, part
WHERE
    (
        p_partkey = l_partkey
        AND p_brand = 'Brand#12'
        AND p_container IN ('SM CASE', 'SM BOX', 'SM PACK', 'SM PKG')
        AND l_quantity >= 1 AND l_quantity <= 1 + 10
        AND p_size BETWEEN 1 AND 5
        AND l_shipmode IN ('AIR', 'AIR REG')
        AND l_shipinstruct = 'DELIVER IN PERSON'
    )
    OR (
        p_partkey = l_partkey
        AND p_brand = 'Brand#23'
        AND p_container IN ('MED BAG', 'MED BOX', 'MED PKG', 'MED PACK')
        AND l_quantity >= 10 AND l_quantity <= 10 + 10
        AND p_size BETWEEN 1 AND 10
        AND l_shipmode IN ('AIR', 'AIR REG')
        AND l_shipinstruct = 'DELIVER IN PERSON'
    )
    OR (
        p_partkey = l_partkey
        AND p_brand = 'Brand#34'
        AND p_container IN ('LG CASE', 'LG BOX', 'LG PACK', 'LG PKG')
        AND l_quantity >= 20 AND l_quantity <= 20 + 10
        AND p_size BETWEEN 1 AND 15
        AND l_shipmode IN ('AIR', 'AIR REG')
        AND l_shipinstruct = 'DELIVER IN PERSON'
    );


-- Q20: Potential Part Promotion
-- Features: EXISTS, IN subquery, multi-join, filter (DATE, LIKE)
SELECT s_name, s_address
FROM supplier, nation
WHERE
    s_suppkey IN (
        SELECT ps_suppkey FROM partsupp
        WHERE
            ps_partkey IN (SELECT p_partkey FROM part WHERE p_name LIKE 'forest%')
            AND ps_availqty > (
                SELECT 0.5 * sum(l_quantity) FROM lineitem
                WHERE
                    l_partkey = ps_partkey
                    AND l_suppkey = ps_suppkey
                    AND l_shipdate >= DATE '1994-01-01'
                    AND l_shipdate < DATE '1994-01-01' + INTERVAL '1' YEAR
            )
    )
    AND s_nationkey = n_nationkey
    AND n_name = 'CANADA'
ORDER BY s_name;


-- Q21: Suppliers Who Kept Orders Waiting
-- Features: EXISTS, NOT EXISTS, multi-join, GROUP BY, ORDER BY, LIMIT
SELECT s_name, count(*) as numwait
FROM supplier, lineitem l1, orders, nation
WHERE
    s_suppkey = l1.l_suppkey
    AND o_orderkey = l1.l_orderkey
    AND o_orderstatus = 'F'
    AND l1.l_receiptdate > l1.l_commitdate
    AND EXISTS (
        SELECT * FROM lineitem l2
        WHERE l2.l_orderkey = l1.l_orderkey AND l2.l_suppkey <> l1.l_suppkey
    )
    AND NOT EXISTS (
        SELECT * FROM lineitem l3
        WHERE
            l3.l_orderkey = l1.l_orderkey
            AND l3.l_suppkey <> l1.l_suppkey
            AND l3.l_receiptdate > l3.l_commitdate
    )
    AND s_nationkey = n_nationkey
    AND n_name = 'SAUDI ARABIA'
GROUP BY s_name
ORDER BY numwait DESC, s_name
LIMIT 100;


-- Q22: Global Sales Opportunity
-- Features: NOT EXISTS, CASE WHEN, SUBSTRING, IN subquery, GROUP BY, ORDER BY
SELECT
    cntrycode, count(*) as numcust, sum(c_acctbal) as totacctbal
FROM (
    SELECT
        SUBSTRING(c_phone FROM 1 FOR 2) as cntrycode,
        c_acctbal
    FROM customer
    WHERE
        SUBSTRING(c_phone FROM 1 FOR 2) IN ('13', '31', '23', '29', '30', '18', '17')
        AND c_acctbal > (
            SELECT avg(c_acctbal) FROM customer
            WHERE
                c_acctbal > 0.00
                AND SUBSTRING(c_phone FROM 1 FOR 2) IN ('13', '31', '23', '29', '30', '18', '17')
        )
        AND NOT EXISTS (
            SELECT * FROM orders WHERE o_custkey = c_custkey
        )
) as custsale
GROUP BY cntrycode
ORDER BY cntrycode;
