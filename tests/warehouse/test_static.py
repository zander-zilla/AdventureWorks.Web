"""Fast, offline checks (no containers): portable-SQL lint, generated SQL in sync, QuickSight definition valid."""
import json, os, re, subprocess, sys
import botocore.session, botocore.validate
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
STAR = os.path.join(ROOT, "warehouse/sql/star")
PORTABLE = ["01_ddl.sql", "02_dims.sql", "03_facts.sql", "04_views.sql", "05_static_ddl.sql", "20_build_procedure.sql"]
# constructs that work on only one of Redshift / Postgres (or behave differently) - keep them out of the shared layer
FORBIDDEN = [r"::", r"\bILIKE\b", r"generate_series", r"DISTINCT\s+ON", r"FILTER\s*\(", r"jsonb", r"->>", r"\bNVL2?\s*\(",
             r"\bDATEADD\b", r"\bDATEDIFF\b", r"\bGETDATE\b", r"\bTOP\s+\d", r"\bINTERVAL\b", r"\bTRUNCATE\b", r"\bSERIAL\b",
             r"\bIDENTITY\b", r"ON\s+CONFLICT", r"\bRETURNING\b", r"\bLATERAL\b", r"\bARRAY\b", r"\bDISTKEY\b", r"\bSORTKEY\b",
             r"\bSUPER\b", r"\bLISTAGG\b", r"\bSTRING_AGG\b", r"\bMERGE\b", r"\bQUALIFY\b", r"\bVALUES\s*\("]

def strip_comments(sql):
    return "\n".join(l.split("--")[0] for l in sql.splitlines())

def test_star_sql_is_portable():
    bad = []
    for f in PORTABLE:
        sql = strip_comments(open(os.path.join(STAR, f)).read())
        for pat in FORBIDDEN:
            for m in re.finditer(pat, sql, re.I):
                bad.append("%s: %r near %r" % (f, pat, sql[max(0, m.start() - 40):m.end() + 20]))
    assert not bad, "\n".join(bad)

def test_generated_sql_in_sync(tmp_path):
    files = ["warehouse/sql/postgres/10_staging_views.sql", "warehouse/sql/redshift/10_staging_views.sql", "warehouse/sql/star/20_build_procedure.sql"]
    before = {f: open(os.path.join(ROOT, f)).read() for f in files}
    subprocess.check_call([sys.executable, os.path.join(ROOT, "warehouse/gen_staging.py")])
    for f in files:
        assert open(os.path.join(ROOT, f)).read() == before[f], f + " is stale: run python warehouse/gen_staging.py"

def test_staging_views_cover_star_inputs():
    used = set(re.findall(r"stg\.\"?([a-z_]+)", "".join(open(os.path.join(STAR, f)).read() for f in ("02_dims.sql", "03_facts.sql"))))
    have = set(re.findall(r"CREATE MATERIALIZED VIEW stg\.([a-z_]+)", open(os.path.join(ROOT, "warehouse/sql/postgres/10_staging_views.sql")).read()))
    assert used <= have, used - have

def _v_sales_columns():
    sql = open(os.path.join(STAR, "04_views.sql")).read()
    first = sql.split("FROM dw.fact_internet_sales")[0].split("SELECT", 1)[1]
    return {m.group(1) for m in re.finditer(r"(?:AS\s+|\.)([a-z_]+)\s*(?:,|$)", first, re.M)}

def test_quicksight_dashboard_definition():
    d = json.load(open(os.path.join(ROOT, "aws/warehouse/quicksight/dashboard.json")))
    model = botocore.session.get_session().get_service_model("quicksight")
    botocore.validate.validate_parameters(d, model.operation_model("CreateDashboard").input_shape)  # raises on schema errors
    cols = {m for m in re.findall(r'"ColumnName": "([a-z_]+)"', json.dumps(d))}
    assert cols <= _v_sales_columns(), cols - _v_sales_columns()
    tf = open(os.path.join(ROOT, "aws/warehouse/terraform/quicksight.tf")).read()
    assert cols <= set(re.findall(r'name = "([a-z_]+)"', tf)), "dashboard uses columns the data set does not import"
