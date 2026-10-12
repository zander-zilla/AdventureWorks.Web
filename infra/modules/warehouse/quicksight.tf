# QuickSight: Redshift data source + SPICE data set over dw.v_sales. The dashboard itself is defined in
# aws/warehouse/quicksight/dashboard.json (CreateDashboard API input, applied with aws/warehouse/quicksight/deploy.sh).
# Optional (decision W-4): only created when enable_quicksight = true; the QuickSight Enterprise subscription itself is a
# manual, billed account step done only for the showcase.
locals { qs = var.enable_quicksight }

resource "aws_quicksight_data_source" "redshift" {
  count          = local.qs ? 1 : 0
  data_source_id = "${var.name}-redshift-dw"
  name           = "AdventureWorks DW (Redshift Serverless)"
  type           = "REDSHIFT"
  parameters {
    redshift {
      host     = aws_redshiftserverless_workgroup.aw.endpoint[0].address
      port     = 5439
      database = "aw_dw"
    }
  }
  dynamic "vpc_connection_properties" {
    for_each = var.quicksight_vpc_connection_arn == "" ? [] : [1]
    content { vpc_connection_arn = var.quicksight_vpc_connection_arn }
  }
  permission {
    principal = var.quicksight_principal_arn
    actions = ["quicksight:DescribeDataSource", "quicksight:DescribeDataSourcePermissions", "quicksight:PassDataSource",
    "quicksight:UpdateDataSource", "quicksight:DeleteDataSource", "quicksight:UpdateDataSourcePermissions"]
  }
}

resource "aws_quicksight_data_set" "sales" {
  count       = local.qs ? 1 : 0
  data_set_id = "${var.name}-sales"
  name        = "AW Sales (internet + reseller)"
  import_mode = "SPICE"
  physical_table_map {
    physical_table_map_id = "vsales"
    relational_table {
      data_source_arn = aws_quicksight_data_source.redshift[0].arn
      schema          = "dw"
      name            = "v_sales"
      input_columns {
        name = "channel"
        type = "STRING"
      }
      input_columns {
        name = "order_date"
        type = "DATETIME"
      }
      input_columns {
        name = "calendar_year"
        type = "INTEGER"
      }
      input_columns {
        name = "fiscal_year"
        type = "INTEGER"
      }
      input_columns {
        name = "sales_territory_group"
        type = "STRING"
      }
      input_columns {
        name = "sales_territory_country"
        type = "STRING"
      }
      input_columns {
        name = "product_category"
        type = "STRING"
      }
      input_columns {
        name = "product_subcategory"
        type = "STRING"
      }
      input_columns {
        name = "customer_or_reseller"
        type = "STRING"
      }
      input_columns {
        name = "order_quantity"
        type = "INTEGER"
      }
      input_columns {
        name = "sales_amount"
        type = "DECIMAL"
      }
      input_columns {
        name = "total_product_cost"
        type = "DECIMAL"
      }
      input_columns {
        name = "gross_margin"
        type = "DECIMAL"
      }
    }
  }
  refresh_properties {
    refresh_configuration {
      incremental_refresh {
        lookback_window {
          column_name = "order_date"
          size        = 7
          size_unit   = "DAY"
        }
      }
    }
  }
  permissions {
    principal = var.quicksight_principal_arn
    actions = ["quicksight:DescribeDataSet", "quicksight:DescribeDataSetPermissions", "quicksight:PassDataSet",
      "quicksight:DescribeIngestion", "quicksight:ListIngestions", "quicksight:UpdateDataSet",
    "quicksight:DeleteDataSet", "quicksight:CreateIngestion", "quicksight:CancelIngestion", "quicksight:UpdateDataSetPermissions"]
  }
}

resource "aws_quicksight_refresh_schedule" "sales" {
  count       = local.qs ? 1 : 0
  data_set_id = aws_quicksight_data_set.sales[0].data_set_id
  schedule_id = "hourly"
  schedule {
    refresh_type = "INCREMENTAL_REFRESH"
    schedule_frequency { interval = "HOURLY" }
  }
}
