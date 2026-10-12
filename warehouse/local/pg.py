"""Postgres stand-in connection helper (container aw-wh-postgres on localhost:5433)."""
import os, psycopg2

def connect(db=None):
    return psycopg2.connect(host=os.environ.get("PGHOST", "localhost"), port=int(os.environ.get("PGPORT", "5433")),
                            user=os.environ.get("PGUSER", "aw"), password=os.environ.get("PGPASSWORD", "aw"),
                            dbname=db or os.environ.get("PGDATABASE", "aw_dw"))

def run_file(conn, path, label=None):
    """Run a SQL file statement by statement (statements end with ';' at end of line). Returns [(first line, seconds)]."""
    import time
    sql = open(path).read(); out = []
    stmts = [s for s in split(sql)]
    with conn.cursor() as cur:
        for s in stmts:
            t0 = time.time(); cur.execute(s); out.append((s.strip().splitlines()[0][:100], round(time.time() - t0, 2)))
    conn.commit()
    return out

def split(sql):
    """Split on ';' at end of line; a $$ ... $$ body (procedure) is kept as one statement."""
    buf = []; in_body = False
    for line in sql.splitlines():
        if line.count("$$") % 2:
            in_body = not in_body
        if in_body:
            buf.append(line); continue
        if line.strip().startswith("--") and not buf:
            continue
        buf.append(line)
        if line.rstrip().endswith(";"):
            s = "\n".join(buf).strip(); buf = []
            if s.strip(";").strip():
                yield s
    if "\n".join(buf).strip():
        yield "\n".join(buf)
