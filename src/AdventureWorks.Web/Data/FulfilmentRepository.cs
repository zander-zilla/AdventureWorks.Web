using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using AdventureWorks.Web.Models;

namespace AdventureWorks.Web.Data;

/// <summary>C2-2 change feed (outbox): every app business write also puts one FEED item (aw-sales, same transaction in
/// AWS) naming the items it wrote and the Redshift staging view that picks each one up. The back office "Replication
/// monitor" reads it; zero-ETL ignores it (no staging view has type ChangeFeed). TTL 7 days.</summary>
public static class ChangeFeed
{
    public static readonly TimeSpan Ttl = TimeSpan.FromDays(7);

    public static Dictionary<string, AttributeValue> Entry(DateTime now, string evt, string subject, string actor, IEnumerable<string> writes)
    {
        var i = Av.Item(Keys.Feed(now), $"{Keys.Iso(now)}#{Guid.NewGuid():N}"[..28], "ChangeFeed");
        i["event"] = Av.S(evt); i["subject"] = Av.S(subject); i["actor"] = Av.S(actor); i["at"] = Av.S(Keys.Iso(now) + "Z");
        i["writes"] = new AttributeValue { L = writes.Select(Av.S).ToList() };
        i["ttl"] = Av.N(new DateTimeOffset(DateTime.SpecifyKind(now, DateTimeKind.Utc)).Add(Ttl).ToUnixTimeSeconds());
        i["src_lsn"] = Av.S(Keys.AppLsn);
        return i;
    }

    /// <summary>Order status history item in the order's partition (SAL-04 reads it with the order).</summary>
    public static Dictionary<string, AttributeValue> Event(long orderId, DateTime now, int seq, string action, int? from, int to, string actor, string? note)
    {
        var e = Av.Item(Keys.Order(orderId), Keys.OrderEvent(now, seq), "OrderEvent");
        e["sales_order_id"] = Av.N(orderId); e["action"] = Av.S(action); e["to_status"] = Av.N(to); e["actor"] = Av.S(actor);
        e["at"] = Av.S(Keys.Iso(now) + "Z"); e["src_lsn"] = Av.S(Keys.AppLsn);
        if (from is { } f) e["from_status"] = Av.N(f);
        e.Set("note", note);
        return e;
    }
}

public sealed record FeedEntry(string Id, DateTime At, string Event, string Subject, string Actor, List<string> Writes);
public sealed record ShipRequest(int ShipMethodId, string TrackingNumber);
public sealed record TransitionResult(Order Order, string Outcome, List<string> Shortages);
public sealed record StockAllocation(int ProductId, int LocationId, int Quantity, decimal OnHandAtLocation, decimal OnHandTotal, int ReorderPoint);

public sealed class ConflictException(string message) : Exception(message);

/// <summary>Back-office order fulfilment over aw-sales (SAL-05 queue, SAL-06 transitions) and aw-inventory (INV-01 stock,
/// INV-03 movements). Ship is one transaction: order status + ship date + tracking, INV#loc decrement (condition on hand
/// >= qty), InventoryProduct stock total, catalog stock copy, TransactionHistory type S per line, event + feed.</summary>
public sealed class FulfilmentRepository(DynamoTables t, TimeProvider clock, PricingRepository pricing)
{
    /// <summary>1 header + per line (line tracking + INV + InventoryProduct + catalog copy + TXN) + event + feed &lt;= 100.</summary>
    public const int MaxShipLines = 19;
    public const long TxnIdStart = 10_000_000;   // above SQL's TransactionID range (< 300k)

    private IAmazonDynamoDB Sales => t.For(DynamoTables.Sales);
    private string SalesT => t.Name(DynamoTables.Sales);
    private string InvT => t.Name(DynamoTables.Inventory);
    private string CatT => t.Name(DynamoTables.Catalog);

    // ---------------------------------------------------------------- SAL-05

    /// <summary>Orders in one open status, newest first, optional date range and territory. Territory is a FilterExpression
    /// on the SAL-05 query (decision: no SAL-14 index; the open-order set is small, see PLAN C2-2 as built).</summary>
    public async Task<OrderPage> QueueAsync(int status, DateTime? from, DateTime? to, int? territoryId, string? token, int pageSize = 50)
    {
        if (!OrderStatus.IsOpen(status)) throw new ArgumentException("Only open statuses (1-3) are indexed (SAL-05).");
        var q = new QueryRequest
        {
            TableName = SalesT, IndexName = "GSI2", ScanIndexForward = false, Limit = pageSize, ExclusiveStartKey = Paging.Decode(token),
            KeyConditionExpression = "GSI2PK = :pk AND GSI2SK BETWEEN :f AND :t",
            ExpressionAttributeValues = new()
            {
                [":pk"] = Av.S($"ORDERSTATUS#{status}"), [":f"] = Av.S(from is { } f ? Keys.Iso(f) : "0"), [":t"] = Av.S((to is { } x ? Keys.Iso(x) : "9999") + "~"),
            },
        };
        if (territoryId is { } terr) { q.FilterExpression = "territory_id = :terr"; q.ExpressionAttributeValues[":terr"] = Av.N(terr); }
        var r = await Sales.QueryAsync(q);
        return new OrderPage((r.Items ?? new()).Where(i => i.IsLive()).Select(SalesRepository.ToOrder).ToList(), Paging.Encode(r.LastEvaluatedKey));
    }

    public async Task<Dictionary<int, int>> CountsAsync()
    {
        var d = new Dictionary<int, int>();
        foreach (var s in new[] { 1, 2, 3 })
        {
            int n = 0; Dictionary<string, AttributeValue>? start = null;
            do
            {
                var r = await Sales.QueryAsync(new QueryRequest { TableName = SalesT, IndexName = "GSI2", Select = Select.COUNT, ExclusiveStartKey = start,
                    KeyConditionExpression = "GSI2PK = :pk", ExpressionAttributeValues = new() { [":pk"] = Av.S($"ORDERSTATUS#{s}") } });
                n += r.Count ?? 0; start = r.LastEvaluatedKey is { Count: > 0 } k ? k : null;
            } while (start is not null);
            d[s] = n;
        }
        return d;
    }

    // ---------------------------------------------------------------- INV-01

    public sealed record Stock(int ProductId, List<(int LocationId, string? Name, decimal Quantity)> Locations, decimal Total, int ReorderPoint, bool HasProductItem);

    public async Task<Stock> GetStockAsync(int productId)
    {
        var items = await t.For(DynamoTables.Inventory).QueryAll(new QueryRequest { TableName = InvT, ConsistentRead = true,
            KeyConditionExpression = "PK = :pk AND SK <= :p", ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.InvProduct(productId)), [":p"] = Av.S("PRODUCT") } });
        var locs = items.Where(i => i.Str("type") == "ProductInventory" && i.IsLive())
            .Select(i => (i.Int("location_id") ?? 0, i.Str("location_name"), i.Dec("quantity") ?? 0)).ToList();
        var head = items.FirstOrDefault(i => i.Str("SK") == "PRODUCT");
        return new Stock(productId, locs, head?.Dec("stock_qty") ?? locs.Sum(l => l.Item3), head?.Int("reorder_point") ?? 0, head is not null);
    }

    /// <summary>Pure: one location per product that covers the whole quantity (largest stock first); else a shortage.</summary>
    public static (List<StockAllocation> Allocations, List<string> Shortages) Allocate(IEnumerable<(int ProductId, string Name, int Qty)> need, IReadOnlyDictionary<int, Stock> stock)
    {
        var alloc = new List<StockAllocation>(); var short_ = new List<string>();
        foreach (var g in need.GroupBy(n => n.ProductId))
        {
            var qty = g.Sum(x => x.Qty); var s = stock[g.Key];
            var loc = s.Locations.Where(l => l.Quantity >= qty).OrderByDescending(l => l.Quantity).ThenBy(l => l.LocationId).Select(l => (int?)l.LocationId).FirstOrDefault();
            if (loc is null) short_.Add($"{g.First().Name} (product {g.Key}): need {qty}, best location has {(s.Locations.Count == 0 ? 0 : s.Locations.Max(l => l.Quantity))}");
            else alloc.Add(new StockAllocation(g.Key, loc.Value, qty, s.Locations.First(l => l.LocationId == loc).Quantity, s.Total, s.ReorderPoint));
        }
        return (alloc, short_);
    }

    // ---------------------------------------------------------------- SAL-06

    public async Task<TransitionResult> ApplyAsync(long orderId, string action, long expectedVersion, string actor, ShipRequest? ship = null, string? idempotencyToken = null)
    {
        var o = await new SalesRepository(t, clock).GetOrderAsync(orderId, consistent: true) ?? throw new KeyNotFoundException();
        if (!OrderStatus.Actions.ContainsKey(action)) throw new ArgumentException($"Unknown action '{action}'.");
        if (o.Version != expectedVersion) throw new ConflictException($"{o.Number} was changed by someone else (version {o.Version}, you had {expectedVersion}). Reload and retry.");
        if (!OrderStatus.CanApply(action, o.Status))
            throw new ConflictException($"Cannot {action} {o.Number}: it is {OrderStatus.Text(o.Status)}.");
        var now = Now();
        if (action != "ship") { await StatusOnlyAsync(o, action, OrderStatus.Actions[action].To, actor, now, null, idempotencyToken); return new(Reload(o, OrderStatus.Actions[action].To), action, []); }

        if (ship is null || string.IsNullOrWhiteSpace(ship.TrackingNumber) || ship.TrackingNumber.Trim().Length > 25)
            throw new ArgumentException("Ship needs a ship method and a tracking number (1-25 characters).");
        var method = (await pricing.GetShipMethodsAsync()).FirstOrDefault(m => m.Id == ship.ShipMethodId) ?? throw new ArgumentException($"Unknown ship method {ship.ShipMethodId}.");
        if (o.Lines.Count > MaxShipLines) throw new ConflictException($"{o.Number} has {o.Lines.Count} lines; one shipment holds at most {MaxShipLines} (split shipments: later phase).");

        var stock = new Dictionary<int, Stock>();
        foreach (var pid in o.Lines.Select(l => l.ProductId).Distinct()) stock[pid] = await GetStockAsync(pid);
        var (alloc, shortages) = Allocate(o.Lines.Select(l => (l.ProductId, l.Name, l.Quantity)), stock);
        if (shortages.Count > 0)
        {
            // INV-01 condition not met: the order goes to Backordered instead (from Approved), as the plan specifies.
            if (o.Status == OrderStatus.Approved)
            {
                await StatusOnlyAsync(o, "backorder", OrderStatus.Backordered, actor, now, "insufficient stock: " + string.Join("; ", shortages), idempotencyToken);
                return new(Reload(o, OrderStatus.Backordered), "backordered", shortages);
            }
            return new(o, "still-backordered", shortages);
        }

        var tracking = ship.TrackingNumber.Trim();
        var txnStart = await NextTxnIdsAsync(o.Lines.Count);
        var actions = ShipPlan(t, o, alloc, method, tracking, actor, now, txnStart);
        try { await t.TransactAsync(actions, idempotencyToken); }
        catch (TransactionCanceledException e) { throw new ConflictException($"Ship of {o.Number} was rejected by a condition (stock or order changed meanwhile): {Reasons(e)}. Reload and retry."); }
        var shipped = Reload(o, OrderStatus.Shipped); shipped.ShipDate = now; shipped.CarrierTrackingNumber = tracking; shipped.ShipMethodId = method.Id; shipped.ShipMethodName = method.Name;
        return new(shipped, "shipped", []);
    }

    private static string Reasons(TransactionCanceledException e) =>
        string.Join(", ", e.CancellationReasons?.Where(r => r.Code != "None").Select(r => r.Code).Distinct() ?? []);

    private static Order Reload(Order o, int status) { o.Status = status; o.Version++; o.RevisionNumber++; return o; }

    private DateTime Now() { var n = clock.GetUtcNow().UtcDateTime; return n.AddTicks(-(n.Ticks % TimeSpan.TicksPerSecond)); }

    private async Task<long> NextTxnIdsAsync(int count)
    {
        var r = await t.For(DynamoTables.Inventory).UpdateItemAsync(new UpdateItemRequest
        {
            TableName = InvT, Key = new() { ["PK"] = Av.S("COUNTER"), ["SK"] = Av.S("TXN") }, ReturnValues = ReturnValue.UPDATED_NEW,
            UpdateExpression = "ADD next_id :n SET #t = if_not_exists(#t, :t), src = :src", ExpressionAttributeNames = new() { ["#t"] = "type" },
            ExpressionAttributeValues = new() { [":n"] = Av.N(count), [":t"] = Av.S("TxnIdCounter"), [":src"] = Av.S("ddb") },
        });
        return TxnIdStart + long.Parse(r.Attributes["next_id"].N) - count + 1;
    }

    /// <summary>Header transition (SAL-06): ver-checked, status-checked; the sparse GSI2 keys follow the new status.</summary>
    public static Update HeaderUpdate(string table, Order o, int to, DateTime now, Dictionary<string, AttributeValue>? extraSets = null)
    {
        var values = new Dictionary<string, AttributeValue>
        {
            [":to"] = Av.N(to), [":v"] = Av.N(o.Version), [":from"] = Av.N(o.Status), [":one"] = Av.N(1), [":now"] = Av.S(Keys.Iso(now)),
            [":u"] = Av.S(Keys.Iso(now) + "Z"), [":src"] = Av.S("ddb"), [":lsn"] = Av.S(Keys.AppLsn),
        };
        var sets = new List<string> { "#s = :to", "modified_date = :now", "updated_at = :u", "src = :src", "src_lsn = :lsn",
            "revision_number = if_not_exists(revision_number, :zero) + :one", "ver = ver + :one" };
        values[":zero"] = Av.N(0);
        string? remove = null;
        if (OrderStatus.IsOpen(to)) { sets.Add("GSI2PK = :g"); sets.Add("GSI2SK = :gs"); values[":g"] = Av.S($"ORDERSTATUS#{to}"); values[":gs"] = Av.S(Keys.Iso(o.OrderDate) + $"#{o.Id:0000000000}"); }
        else remove = " REMOVE GSI2PK, GSI2SK";
        foreach (var (k, v) in extraSets ?? new()) { sets.Add($"{k} = :x_{k}"); values[$":x_{k}"] = v; }
        return new Update
        {
            TableName = table, Key = new() { ["PK"] = Av.S(Keys.Order(o.Id)), ["SK"] = Av.S("ORDER") },
            UpdateExpression = "SET " + string.Join(", ", sets) + (remove ?? ""), ConditionExpression = "ver = :v AND #s = :from",
            ExpressionAttributeNames = new() { ["#s"] = "status" }, ExpressionAttributeValues = values,
        };
    }

    private async Task StatusOnlyAsync(Order o, string action, int to, string actor, DateTime now, string? note, string? token)
    {
        var pk = Keys.Order(o.Id);
        var actions = new List<(string, TransactWriteItem)>
        {
            (DynamoTables.Sales, new() { Update = HeaderUpdate(SalesT, o, to, now) }),
            (DynamoTables.Sales, new() { Put = new Put { TableName = SalesT, Item = ChangeFeed.Event(o.Id, now, o.Events.Count + 1, action, o.Status, to, actor, note) } }),
            (DynamoTables.Sales, new() { Put = new Put { TableName = SalesT, Item = ChangeFeed.Entry(now, $"order.{action}", o.Number, actor,
                [$"aw-sales {pk} ORDER status {o.Status}->{to} (Order -> stg.order)", $"aw-sales {pk} EVENT (OrderEvent, history)"]) } }),
        };
        try { await t.TransactAsync(actions, token); }
        catch (TransactionCanceledException) { throw new ConflictException($"{o.Number} changed meanwhile. Reload and retry."); }
    }

    /// <summary>Pure: the ship transaction (unit-tested). Order of groups: inventory first (stock conditions), then catalog
    /// copy, then sales (order version/status condition) - only matters for the per-table local DynamoDB layout.</summary>
    public static List<(string Table, TransactWriteItem Action)> ShipPlan(DynamoTables t, Order o, List<StockAllocation> alloc, ShipMethodInfo method,
        string tracking, string actor, DateTime now, long txnStart)
    {
        string inv = t.Name(DynamoTables.Inventory), cat = t.Name(DynamoTables.Catalog), sales = t.Name(DynamoTables.Sales);
        var a = new List<(string, TransactWriteItem)>();
        var u = Av.S(Keys.Iso(now) + "Z"); var lsn = Av.S(Keys.AppLsn); var src = Av.S("ddb");
        var writes = new List<string>();
        foreach (var s in alloc)
        {
            var pk = Av.S(Keys.InvProduct(s.ProductId));
            a.Add((DynamoTables.Inventory, new() { Update = new Update { TableName = inv, Key = new() { ["PK"] = pk, ["SK"] = Av.S($"INV#{s.LocationId:000}") },
                UpdateExpression = "SET quantity = quantity - :q, modified_date = :now, updated_at = :u, src = :src, src_lsn = :lsn ADD ver :one",
                ConditionExpression = "quantity >= :q",
                ExpressionAttributeValues = new() { [":q"] = Av.N(s.Quantity), [":now"] = Av.S(Keys.Iso(now)), [":u"] = u, [":src"] = src, [":lsn"] = lsn, [":one"] = Av.N(1) } } }));
            var newTotal = s.OnHandTotal - s.Quantity;
            var below = newTotal < s.ReorderPoint;
            a.Add((DynamoTables.Inventory, new() { Update = new Update { TableName = inv, Key = new() { ["PK"] = pk, ["SK"] = Av.S("PRODUCT") },
                UpdateExpression = "SET stock_qty = :new, updated_at = :u, src = :src, src_lsn = :lsn" + (below ? ", GSI1PK = :r, GSI1SK = :rs" : " REMOVE GSI1PK, GSI1SK") + " ADD ver :one",
                ConditionExpression = "attribute_exists(PK) AND (attribute_not_exists(stock_qty) OR stock_qty = :old)",
                ExpressionAttributeValues = below
                    ? new() { [":new"] = Av.N(newTotal), [":old"] = Av.N(s.OnHandTotal), [":u"] = u, [":src"] = src, [":lsn"] = lsn, [":one"] = Av.N(1), [":r"] = Av.S("REORDER"), [":rs"] = pk }
                    : new() { [":new"] = Av.N(newTotal), [":old"] = Av.N(s.OnHandTotal), [":u"] = u, [":src"] = src, [":lsn"] = lsn, [":one"] = Av.N(1) } } }));
            writes.Add($"aw-inventory {pk.S} INV#{s.LocationId:000} -{s.Quantity} (ProductInventory -> stg.product_inventory)");
            writes.Add($"aw-inventory {pk.S} PRODUCT stock_qty {s.OnHandTotal}->{newTotal}{(below ? " REORDER" : "")}");
        }
        var n = 0;
        foreach (var l in o.Lines)
        {
            var id = txnStart + n++;
            var item = Av.Item(Keys.InvProduct(l.ProductId), Keys.Txn(now, id), "InventoryTransaction");
            item["transaction_id"] = Av.N(id); item["product_id"] = Av.N(l.ProductId); item["reference_order_id"] = Av.N(o.Id);
            item["reference_order_line_id"] = Av.N(l.LineNo); item["transaction_date"] = Av.S(Keys.Iso(now)); item["transaction_type"] = Av.S("S");
            item["quantity"] = Av.N(l.Quantity); item["actual_cost"] = Av.N(l.UnitPrice); item["modified_date"] = Av.S(Keys.Iso(now));
            item["archived"] = Av.B(false); item["src_lsn"] = lsn;
            a.Add((DynamoTables.Inventory, new() { Put = new Put { TableName = inv, Item = item, ConditionExpression = "attribute_not_exists(PK)" } }));
            writes.Add($"aw-inventory {Keys.InvProduct(l.ProductId)} {Keys.Txn(now, id)} type S qty {l.Quantity} (InventoryTransaction -> stg.inventory_transaction)");
        }
        foreach (var s in alloc)
        {
            a.Add((DynamoTables.Catalog, new() { Update = new Update { TableName = cat, Key = new() { ["PK"] = Av.S(Keys.Product(s.ProductId)), ["SK"] = Av.S("PRODUCT") },
                UpdateExpression = "SET stock_qty = :new, updated_at = :u", ConditionExpression = "attribute_exists(PK)",
                ExpressionAttributeValues = new() { [":new"] = Av.N(s.OnHandTotal - s.Quantity), [":u"] = u } } }));
        }
        var opk = Keys.Order(o.Id);
        a.Add((DynamoTables.Sales, new() { Update = HeaderUpdate(sales, o, OrderStatus.Shipped, now, new()
        {
            ["ship_date"] = Av.S(Keys.Iso(now)), ["ship_method_id"] = Av.N(method.Id), ["ship_method_name"] = Av.S(method.Name), ["carrier_tracking_number"] = Av.S(tracking),
        }) }));
        foreach (var l in o.Lines)
            a.Add((DynamoTables.Sales, new() { Update = new Update { TableName = sales, Key = new() { ["PK"] = Av.S(opk), ["SK"] = Av.S(Keys.OrderLine(l.LineNo)) },
                UpdateExpression = "SET carrier_tracking_number = :c, updated_at = :u, src = :src, src_lsn = :lsn", ConditionExpression = "attribute_exists(PK)",
                ExpressionAttributeValues = new() { [":c"] = Av.S(tracking), [":u"] = u, [":src"] = src, [":lsn"] = lsn } } }));
        a.Add((DynamoTables.Sales, new() { Put = new Put { TableName = sales, Item = ChangeFeed.Event(o.Id, now, o.Events.Count + 1, "ship", o.Status, OrderStatus.Shipped, actor, $"{method.Name} · {tracking}") } }));
        writes.Insert(0, $"aw-sales {opk} ORDER status {o.Status}->5, ship_date, tracking (Order -> stg.order)");
        writes.Insert(1, $"aw-sales {opk} LINE# x{o.Lines.Count} carrier_tracking_number (OrderLine -> stg.order_line)");
        a.Add((DynamoTables.Sales, new() { Put = new Put { TableName = sales, Item = ChangeFeed.Entry(now, "order.ship", o.Number, actor, writes) } }));
        return a;
    }

    // ---------------------------------------------------------------- change feed

    /// <summary>Feed entry for catalog-side events (reviews, price edits). Written right after the catalog transaction
    /// (aw-catalog and aw-sales are separate tables; the feed is informational, the catalog write is the source of truth).</summary>
    public Task AppendFeedAsync(DateTime now, string evt, string subject, string actor, IEnumerable<string> writes) =>
        Sales.PutItemAsync(new PutItemRequest { TableName = SalesT, Item = ChangeFeed.Entry(now, evt, subject, actor, writes) });

    public async Task<List<FeedEntry>> FeedAsync(int limit = 50)
    {
        var now = clock.GetUtcNow().UtcDateTime; var all = new List<FeedEntry>();
        for (var d = 0; d < 7 && all.Count < limit; d++)
        {
            var r = await Sales.QueryAsync(new QueryRequest { TableName = SalesT, KeyConditionExpression = "PK = :pk", ScanIndexForward = false, Limit = limit - all.Count,
                ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Feed(now.AddDays(-d))) } });
            all.AddRange((r.Items ?? new()).Select(i => new FeedEntry(i.Str("SK")!, i.Date("at") ?? DateTime.MinValue, i.Str("event") ?? "", i.Str("subject") ?? "",
                i.Str("actor") ?? "", i.TryGetValue("writes", out var w) && w.L is { } l ? l.Select(x => x.S).ToList() : new())));
        }
        return all;
    }
}
