# ADR 0006: The modernized app talks to DynamoDB directly through per-domain repositories

Status: Accepted for review (Phase 5)

## Context
The before app uses EF Core over SQL. Phase 3 designed one single-table DynamoDB design per domain, and D4 says the new app
writes orders straight to DynamoDB.

## Decision
- **Separate project:** a new `src/AdventureWorks.Web` (.NET 10, minimal hosting, nullable). The 2.1 app stays at the
  root as the before baseline (side-by-side cutover, D4).
- **Low-level SDK:** each domain gets a repository built on the low-level `IAmazonDynamoDB` client
  (`CatalogRepository`, `CustomerRepository`, `SalesRepository`). There is no object-persistence `DynamoDBContext` and no
  generic repository.
  - Every method implements one documented access pattern (docs/modernization/app.md), and key templates are kept
    in one place (`Keys`).
  - We chose this over the object-persistence model because overloaded `PK`/`SK`/`GSI` items, transactions and condition
    expressions are explicit (The DynamoDB Book, ch. 6.4 for condition expressions and ch. 9 From modeling to implementation).
- **Consistency:** strong reads only for login, the cart and read-after-checkout (D8).
- **App-written item metadata:** `src = "ddb"`, `ver`, `updated_at`, so Redshift and CDC can tell them from SQL-sourced
  items (ADR 0002).
- **Order IDs:** one atomic counter increment per order (P3-1) from 1,000,000,000. The `SO-DDB-` prefix is applied in
  `Keys.OrderNumber` (D5).
- **Checkout:** a single `TransactWriteItems` with the header (`attribute_not_exists`), the lines and the cart deletes.
  Past 100 actions, the remaining cart deletes run right after the transaction in a batch. More than 95 lines is
  refused (P3-5).
- **Endpoints:** one endpoint per table is configurable (`DynamoDb:Endpoints`) for the multi-instance DynamoDB Local.
  AWS uses the Region only.

## Consequences
- **Writes that span copies are the app's job:** for example, renaming a person updates both the PERSON item and the
  customer's `display_name`/`GSI2SK` in one transaction. Copies in other tables (for example `customer_name` on old
  orders) stay as historical snapshots.
- **No CDC back to SQL:** new orders exist only in DynamoDB and Redshift (D4). Reports must read Redshift, not SQL.
