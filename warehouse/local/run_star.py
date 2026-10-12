#!/usr/bin/env python3
"""Build the star schema in the Postgres stand-in: staging views -> DDL -> dims -> facts -> views.
The star SQL files are the same ones the Redshift stored procedure runs (warehouse/sql/redshift/20_build_procedure.sql)."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import pg
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
# 20_build_procedure.sql is the generated dw.sp_build_star() (02_dims + 03_facts) - the exact procedure Redshift runs.
FILES = ["warehouse/sql/postgres/10_staging_views.sql", "warehouse/sql/star/01_ddl.sql", "warehouse/sql/star/05_static_ddl.sql",
         "warehouse/sql/star/20_build_procedure.sql", "CALL dw.sp_build_star();", "warehouse/sql/star/04_views.sql"]

def static_loaded(conn):
    cur = conn.cursor(); cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'dw_static'"); return cur.fetchone()[0] > 0

def main():
    conn = pg.connect(); timings = {}
    for f in FILES:
        if f == "warehouse/sql/star/05_static_ddl.sql" and static_loaded(conn):
            continue  # static tables were loaded by static_export.py --pg; DDL is the same file
        t0 = time.time()
        if f.endswith(".sql"):
            steps = pg.run_file(conn, os.path.join(ROOT, f))
        else:
            conn.cursor().execute(f); conn.commit(); steps = [f]
        timings[f] = round(time.time() - t0, 1)
        if "staging" in f:  # fresh materialized views have no statistics -> terrible join plans without this
            conn.autocommit = True; conn.cursor().execute("ANALYZE"); conn.autocommit = False
        print("%-45s %6.1fs (%d statements)" % (f, timings[f], len(steps)), flush=True)
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'dw' AND table_type = 'BASE TABLE' ORDER BY 1")
    for (t,) in cur.fetchall():
        cur.execute("SELECT COUNT(*) FROM dw.%s" % t); print("  dw.%-28s %8d" % (t, cur.fetchone()[0]))

if __name__ == "__main__":
    main()
