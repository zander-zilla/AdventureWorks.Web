-- Redshift Serverless one-time setup (run as admin in database aw_dw after `terraform apply` of infra/modules/warehouse).
-- Order (runbook: docs/design/warehouse.md "Deploying on AWS"): 00_setup -> 10_staging_views -> star/01_ddl -> star/05_static_ddl
--   -> 40_static_copy -> 30_physical -> star/20_build_procedure -> CALL dw.sp_build_star() -> star/04_views.

-- 1. One database per zero-ETL integration (ids: terraform output integration_arns / SVV_INTEGRATION).
--    ${integration_id_<domain>} are placeholders to fill in (SELECT integration_id FROM SVV_INTEGRATION).
CREATE DATABASE aw_zetl_catalog     FROM INTEGRATION '${integration_id_catalog}';
CREATE DATABASE aw_zetl_customer    FROM INTEGRATION '${integration_id_customer}';
CREATE DATABASE aw_zetl_hr          FROM INTEGRATION '${integration_id_hr}';
CREATE DATABASE aw_zetl_inventory   FROM INTEGRATION '${integration_id_inventory}';
CREATE DATABASE aw_zetl_purchasing  FROM INTEGRATION '${integration_id_purchasing}';
CREATE DATABASE aw_zetl_reference   FROM INTEGRATION '${integration_id_reference}';
CREATE DATABASE aw_zetl_sales       FROM INTEGRATION '${integration_id_sales}';

-- 2. Item attributes can exceed 64 KB only in the catalog photos/documents (max ~62 KB today, checked in CI by
--    warehouse/local/check_item_sizes.py); truncate instead of failing the whole table if one ever grows past the limit.
ALTER DATABASE aw_zetl_catalog SET TRUNCATECOLUMNS TRUE;

-- 3. Schemas + least-privilege reader for QuickSight.
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS dw;
CREATE SCHEMA IF NOT EXISTS dw_static;
CREATE USER quicksight_reader PASSWORD DISABLE;
GRANT USAGE ON SCHEMA dw, dw_static TO quicksight_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA dw GRANT SELECT ON TABLES TO quicksight_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA dw_static GRANT SELECT ON TABLES TO quicksight_reader;
