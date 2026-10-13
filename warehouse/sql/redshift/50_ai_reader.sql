-- C2-5 ask-the-data (enable_ai): read-only warehouse user for the Data API. SELECT on the semantic layer (dw.v_* views) only,
-- nothing on facts, dimensions, staging or landing. Run once by an admin after the star exists; the password goes into the
-- Secrets Manager secret created by infra/modules/ai (ai_reader_secret_arn). Statement timeout is a second guard next to the app's.
CREATE USER ai_reader PASSWORD DISABLE;
CREATE ROLE ai_read_dw_views;
GRANT USAGE ON SCHEMA dw TO ROLE ai_read_dw_views;
GRANT SELECT ON dw.v_sales, dw.v_vendor_performance, dw.v_production_scrap_on_time TO ROLE ai_read_dw_views;
GRANT ROLE ai_read_dw_views TO ai_reader;
ALTER USER ai_reader SET statement_timeout TO 15000;
