#!/usr/bin/env python3
"""
Create TPC-H database with int/float-only tables for GPU benchmarking.

Uses DuckDB's built-in TPC-H data generator (dbgen), then creates derived
tables with all columns cast to INT or FLOAT (no VARCHAR, DATE, DECIMAL).

Usage:
  python create_tpch_db.py                  # SF=1  (~6M lineitem rows)
  python create_tpch_db.py --sf 10          # SF=10 (~60M lineitem rows)
  python create_tpch_db.py --sf 1 --out tpch_sf1.db
"""

import argparse
import os
import time
import duckdb


def main():
    parser = argparse.ArgumentParser(description="Generate TPC-H database (int/float only)")
    parser.add_argument("--sf", type=float, default=1.0, help="Scale factor (default: 1)")
    parser.add_argument("--out", type=str, default=None,
                        help="Output DB path (default: tpch_sf<SF>.db)")
    args = parser.parse_args()

    sf = args.sf
    db_path = args.out or os.path.expanduser(
        f"~/Device/IMPORTANT/tpch/tpch_sf{int(sf)}.db")

    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"Removed existing {db_path}")

    print(f"Creating TPC-H database: {db_path}")
    print(f"  Scale Factor : {sf}")
    print(f"  Expected rows: lineitem ~{int(sf * 6_001_215):,}, orders ~{int(sf * 1_500_000):,}")
    print()

    con = duckdb.connect(db_path)

    # ── Step 1: Generate standard TPC-H tables ───────────────────────────
    print("Step 1: Generating standard TPC-H tables via dbgen...")
    t0 = time.time()
    con.execute("INSTALL tpch; LOAD tpch;")
    con.execute(f"CALL dbgen(sf={sf});")
    t1 = time.time()
    print(f"  dbgen completed in {t1 - t0:.1f}s")

    # Print row counts
    for tbl in ["region", "nation", "supplier", "customer", "part",
                "partsupp", "orders", "lineitem"]:
        cnt = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:>12s}: {cnt:>12,} rows")
    print()

    # ── Step 2: Create int/float-only tables ─────────────────────────────
    # These tables drop all VARCHAR columns and encode DATE→INT, DECIMAL→FLOAT.
    # String columns that are useful for filtering are encoded as integer IDs.
    print("Step 2: Creating int/float-only tables...")
    t0 = time.time()

    # REGION: r_regionkey INT, r_name→r_name_id INT
    con.execute("""
        CREATE TABLE region_int AS
        SELECT
            CAST(r_regionkey AS INTEGER) AS r_regionkey,
            -- Encode region names: AFRICA=0, AMERICA=1, ASIA=2, EUROPE=3, MIDDLE EAST=4
            CASE r_name
                WHEN 'AFRICA'      THEN 0
                WHEN 'AMERICA'     THEN 1
                WHEN 'ASIA'        THEN 2
                WHEN 'EUROPE'      THEN 3
                WHEN 'MIDDLE EAST' THEN 4
            END AS r_name_id
        FROM region
    """)

    # NATION: n_nationkey, n_regionkey, n_name_id (0–24 = nationkey itself)
    con.execute("""
        CREATE TABLE nation_int AS
        SELECT
            CAST(n_nationkey AS INTEGER) AS n_nationkey,
            CAST(n_regionkey AS INTEGER) AS n_regionkey,
            CAST(n_nationkey AS INTEGER) AS n_name_id
        FROM nation
    """)

    # SUPPLIER: s_suppkey, s_nationkey, s_acctbal
    con.execute("""
        CREATE TABLE supplier_int AS
        SELECT
            CAST(s_suppkey AS INTEGER)   AS s_suppkey,
            CAST(s_nationkey AS INTEGER) AS s_nationkey,
            CAST(s_acctbal AS FLOAT)     AS s_acctbal
        FROM supplier
    """)

    # CUSTOMER: c_custkey, c_nationkey, c_acctbal, c_mktsegment_id
    con.execute("""
        CREATE TABLE customer_int AS
        SELECT
            CAST(c_custkey AS INTEGER)   AS c_custkey,
            CAST(c_nationkey AS INTEGER) AS c_nationkey,
            CAST(c_acctbal AS FLOAT)     AS c_acctbal,
            CASE c_mktsegment
                WHEN 'AUTOMOBILE' THEN 1
                WHEN 'BUILDING'   THEN 2
                WHEN 'FURNITURE'  THEN 3
                WHEN 'HOUSEHOLD'  THEN 4
                WHEN 'MACHINERY'  THEN 5
            END AS c_mktsegment_id
        FROM customer
    """)

    # PART: p_partkey, p_brand_id, p_type_id, p_size, p_container_id, p_retailprice
    # brand is 'Brand#NN' → extract NN as integer
    con.execute("""
        CREATE TABLE part_int AS
        SELECT
            CAST(p_partkey AS INTEGER)      AS p_partkey,
            CAST(REPLACE(p_brand, 'Brand#', '') AS INTEGER) AS p_brand_id,
            CAST(p_size AS INTEGER)          AS p_size,
            CAST(p_retailprice AS FLOAT)     AS p_retailprice
        FROM part
    """)

    # PARTSUPP: ps_partkey, ps_suppkey, ps_availqty, ps_supplycost
    con.execute("""
        CREATE TABLE partsupp_int AS
        SELECT
            CAST(ps_partkey AS INTEGER)    AS ps_partkey,
            CAST(ps_suppkey AS INTEGER)    AS ps_suppkey,
            CAST(ps_availqty AS INTEGER)   AS ps_availqty,
            CAST(ps_supplycost AS FLOAT)   AS ps_supplycost
        FROM partsupp
    """)

    # ORDERS: o_orderkey, o_custkey, o_orderstatus_id, o_totalprice, o_orderdate_int, o_orderpriority_id, o_shippriority
    con.execute("""
        CREATE TABLE orders_int AS
        SELECT
            CAST(o_orderkey AS INTEGER)    AS o_orderkey,
            CAST(o_custkey AS INTEGER)     AS o_custkey,
            CASE o_orderstatus
                WHEN 'F' THEN 1
                WHEN 'O' THEN 2
                WHEN 'P' THEN 3
            END AS o_orderstatus_id,
            CAST(o_totalprice AS FLOAT)    AS o_totalprice,
            -- DATE → INT as YYYYMMDD
            CAST(year(o_orderdate) * 10000 + month(o_orderdate) * 100 + day(o_orderdate) AS INTEGER) AS o_orderdate_int,
            -- Priority: '1-URGENT'=1, '2-HIGH'=2, '3-MEDIUM'=3, '4-NOT SPECIFIED'=4, '5-LOW'=5
            CAST(CAST(LEFT(o_orderpriority, 1) AS INTEGER) AS INTEGER) AS o_orderpriority_id,
            CAST(o_shippriority AS INTEGER) AS o_shippriority
        FROM orders
    """)

    # LINEITEM: the fact table — all numeric columns + encoded flags/dates
    con.execute("""
        CREATE TABLE lineitem_int AS
        SELECT
            CAST(l_orderkey AS INTEGER)     AS l_orderkey,
            CAST(l_partkey AS INTEGER)      AS l_partkey,
            CAST(l_suppkey AS INTEGER)      AS l_suppkey,
            CAST(l_linenumber AS INTEGER)   AS l_linenumber,
            CAST(l_quantity AS FLOAT)       AS l_quantity,
            CAST(l_extendedprice AS FLOAT)  AS l_extendedprice,
            CAST(l_discount AS FLOAT)       AS l_discount,
            CAST(l_tax AS FLOAT)            AS l_tax,
            CASE l_returnflag
                WHEN 'A' THEN 1
                WHEN 'N' THEN 2
                WHEN 'R' THEN 3
            END AS l_returnflag_id,
            CASE l_linestatus
                WHEN 'F' THEN 1
                WHEN 'O' THEN 2
            END AS l_linestatus_id,
            CAST(year(l_shipdate) * 10000 + month(l_shipdate) * 100 + day(l_shipdate) AS INTEGER) AS l_shipdate_int,
            CAST(year(l_commitdate) * 10000 + month(l_commitdate) * 100 + day(l_commitdate) AS INTEGER) AS l_commitdate_int,
            CAST(year(l_receiptdate) * 10000 + month(l_receiptdate) * 100 + day(l_receiptdate) AS INTEGER) AS l_receiptdate_int,
            CASE l_shipmode
                WHEN 'REG AIR' THEN 1
                WHEN 'AIR'     THEN 2
                WHEN 'RAIL'    THEN 3
                WHEN 'SHIP'    THEN 4
                WHEN 'TRUCK'   THEN 5
                WHEN 'MAIL'    THEN 6
                WHEN 'FOB'     THEN 7
            END AS l_shipmode_id,
            CASE l_shipinstruct
                WHEN 'DELIVER IN PERSON'    THEN 1
                WHEN 'COLLECT COD'          THEN 2
                WHEN 'NONE'                 THEN 3
                WHEN 'TAKE BACK RETURN'     THEN 4
            END AS l_shipinstruct_id
        FROM lineitem
    """)

    t1 = time.time()
    print(f"  Int/float tables created in {t1 - t0:.1f}s")

    # Print row counts for int tables
    for tbl in ["region_int", "nation_int", "supplier_int", "customer_int",
                "part_int", "partsupp_int", "orders_int", "lineitem_int"]:
        cnt = con.execute(f"SELECT count(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:>16s}: {cnt:>12,} rows")

    # Verify column types
    print()
    print("Column types (lineitem_int):")
    cols = con.execute("DESCRIBE lineitem_int").fetchall()
    for col_name, col_type, *_ in cols:
        print(f"  {col_name:<25s} {col_type}")

    print()
    print("Column types (orders_int):")
    cols = con.execute("DESCRIBE orders_int").fetchall()
    for col_name, col_type, *_ in cols:
        print(f"  {col_name:<25s} {col_type}")

    con.close()
    db_size = os.path.getsize(db_path) / (1024 * 1024)
    print(f"\nDatabase size: {db_size:.1f} MB")
    print(f"Done: {db_path}")


if __name__ == "__main__":
    main()
