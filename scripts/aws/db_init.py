#!/usr/bin/env python3
"""RDS SQL Server one-time init, run inside the VPC as the ECS tools task (`scripts/aws/run-tool.sh db-init`).

1. Stage AdventureWorks2022 / AdventureWorksLT2022 .bak files in the backups bucket (downloaded from the official
   microsoft/sql-server-samples release if missing) and restore them with RDS native restore
   (msdb.dbo.rds_restore_database; option SQLSERVER_BACKUP_RESTORE in infra/modules/source_db).
2. Enable CDC the RDS way: msdb.dbo.rds_cdc_enable_db, then sys.sp_cdc_enable_table for the 68 business tables
   (same selection as docker/before/sql/02-enable-cdc.sql and aws/dms/table-mappings.json), 7-day retention (P4-4),
   1-second capture polling.
3. Print the UTC time to start DMS from (scripts/aws/start-cdc.sh) - captured before the bulk load.
Idempotent: existing databases / CDC-enabled tables are skipped. Env: SQL_HOST, SQL_USER, MSSQL_SA_PASSWORD, BACKUPS_BUCKET.
"""
import datetime, os, sys, time, urllib.request
import boto3, pymssql

RELEASE = "https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/"
DBS = ["AdventureWorks2022", "AdventureWorksLT2022"]
SCHEMAS = ("HumanResources", "Person", "Production", "Purchasing", "Sales")


def conn(db="master"):
    c = pymssql.connect(server=os.environ["SQL_HOST"], port=int(os.environ.get("SQL_PORT", "1433")), user=os.environ["SQL_USER"],
                        password=os.environ["MSSQL_SA_PASSWORD"], database=db, autocommit=True)
    return c


def q(c, sql, *args):
    cur = c.cursor()
    cur.execute(sql, args or None)
    try:
        return cur.fetchall()
    except pymssql.OperationalError:
        return []


def stage(bucket, name):
    s3 = boto3.client("s3")
    try:
        s3.head_object(Bucket=bucket, Key=name)
        return
    except s3.exceptions.ClientError:
        pass
    print("downloading", name, flush=True)
    with urllib.request.urlopen(RELEASE + name) as r:
        s3.upload_fileobj(r, bucket, name)


def restore(c, bucket, db):
    if q(c, "SELECT 1 FROM sys.databases WHERE name = %s", db):
        print(db, "already restored"); return
    stage(bucket, db + ".bak")
    arn = "arn:aws:s3:::%s/%s.bak" % (bucket, db)
    q(c, "EXEC msdb.dbo.rds_restore_database @restore_db_name=%s, @s3_arn_to_restore_from=%s", db, arn)
    while True:
        rows = q(c, "EXEC msdb.dbo.rds_task_status @db_name=%s", db)
        status = rows[-1][5] if rows else "UNKNOWN"  # lifecycle column
        print(db, status, flush=True)
        if status == "SUCCESS":
            return
        if status in ("ERROR", "CANCELLED"):
            sys.exit("restore of %s failed: %s" % (db, rows[-1]))
        time.sleep(20)


def enable_cdc():
    c = conn("master")
    if not q(c, "SELECT 1 FROM sys.databases WHERE name='AdventureWorks2022' AND is_cdc_enabled=1"):
        q(c, "EXEC msdb.dbo.rds_cdc_enable_db 'AdventureWorks2022'")
    d = conn("AdventureWorks2022")
    tables = q(d, """SELECT s.name, t.name, CASE WHEN EXISTS (SELECT 1 FROM sys.indexes i WHERE i.object_id=t.object_id AND i.is_primary_key=1) THEN 1 ELSE 0 END
                      FROM sys.tables t JOIN sys.schemas s ON s.schema_id=t.schema_id
                     WHERE t.is_ms_shipped=0 AND s.name IN %s
                       AND NOT EXISTS (SELECT 1 FROM cdc.change_tables ct WHERE ct.source_object_id=t.object_id)
                     ORDER BY 1, 2""", SCHEMAS)
    for s, n, haspk in tables:
        q(d, "EXEC sys.sp_cdc_enable_table @source_schema=%s, @source_name=%s, @role_name=NULL, @supports_net_changes=%s", s, n, haspk)
    total = q(d, "SELECT COUNT(*) FROM cdc.change_tables")[0][0]
    print("CDC tables:", total)
    q(d, "EXEC sys.sp_cdc_change_job @job_type=N'cleanup', @retention=10080")  # 7 days (P4-4)
    q(d, "EXEC sys.sp_cdc_change_job @job_type=N'capture', @pollinginterval=1")
    for job in ("capture", "cleanup"):
        q(d, "EXEC sys.sp_cdc_stop_job @job_type=N'%s'" % job)
        q(d, "EXEC sys.sp_cdc_start_job @job_type=N'%s'" % job)
    if total < 68:
        sys.exit("expected 68 CDC tables, got %d" % total)


def main():
    c = conn()
    for db in DBS:
        restore(c, os.environ["BACKUPS_BUCKET"], db)
    enable_cdc()
    start = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("CDC_START_TIME=%s  (start DMS from here: scripts/aws/start-cdc.sh %s)" % (start, start), flush=True)


if __name__ == "__main__":
    main()
