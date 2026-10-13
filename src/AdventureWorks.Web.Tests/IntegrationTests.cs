using AdventureWorks.Web.Data;

namespace AdventureWorks.Web.Tests;

/// <summary>Against DynamoDB Local loaded by the Phase 3 loader (DDB_MULTI ports 8001.., set AW_DDB_IT=1).</summary>
public class IntegrationTests
{
    private static readonly bool On = Environment.GetEnvironmentVariable("AW_DDB_IT") == "1";
    internal static DynamoTables Tables()
    {
        var b = int.Parse(Environment.GetEnvironmentVariable("DDB_PORT_BASE") ?? "8001");
        return new DynamoTables(new DynamoOptions { Endpoints = new()
        {
            ["aw-catalog"] = $"http://localhost:{b}", ["aw-customer"] = $"http://localhost:{b + 1}", ["aw-inventory"] = $"http://localhost:{b + 3}", ["aw-purchasing"] = $"http://localhost:{b + 4}",
            ["aw-reference"] = $"http://localhost:{b + 5}", ["aw-sales"] = $"http://localhost:{b + 6}",
        } });
    }

    [Fact] public async Task Catalog_tree_search_and_descriptions()
    {
        if (!On) return;
        var c = new CatalogRepository(Tables());
        var tree = await c.GetCategoryTreeAsync();
        Assert.Equal(4, tree.Count);
        Assert.Equal(37, tree.Sum(x => x.Subcategories.Count));
        var bikes = await c.GetProductsBySubcategoryAsync(1);
        Assert.Equal(20, bikes.Count);   // active (A) products only; 32 incl. discontinued
        Assert.All(bikes, p => Assert.Equal("Mountain Bikes", p.SubcategoryName));
        var hits = await c.SearchByPrefixAsync("Touring-1000");
        Assert.NotEmpty(hits); Assert.All(hits, h => Assert.StartsWith("Touring-1000", h.Name));
        Assert.Empty(await c.SearchByPrefixAsync("Mountain-100"));   // discontinued (inactive) products are not sold
        var p = await c.GetProductAsync(771);
        Assert.Equal(6, (await c.GetDescriptionsAsync(p!.ModelId!.Value)).Count);
        Assert.Equal(680, (await c.GetByNumberAsync("FR-R92B-58"))!.Id);
    }

    [Fact] public async Task Login_customer_cart_checkout_history()
    {
        if (!On) return;
        var t = Tables();
        var customers = new CustomerRepository(t);
        var login = await customers.FindLoginAsync("donald0@adventure-works.com");
        Assert.NotNull(login);
        Assert.Equal(29568, login!.CustomerId);
        var view = await customers.GetCustomerAsync(login.CustomerId);
        Assert.NotEmpty(view!.Addresses);

        var catalog = new CatalogRepository(t);
        var sales = new SalesRepository(t, TimeProvider.System);
        foreach (var (pid, _) in (await sales.GetCartAsync(login.CustomerId)).Select(l => (l.ProductId, 0))) await sales.RemoveAsync(login.CustomerId, pid);
        await sales.AddToCartAsync(login.CustomerId, (await catalog.GetProductAsync(771))!, 1);
        await sales.AddToCartAsync(login.CustomerId, (await catalog.GetProductAsync(771))!, 2);
        await sales.AddToCartAsync(login.CustomerId, (await catalog.GetProductAsync(680))!, 1);
        var cart = await sales.GetCartAsync(login.CustomerId);
        Assert.Equal(3, cart.Single(l => l.ProductId == 771).Quantity);

        var order = await sales.CheckoutAsync(login.CustomerId, view, login.Email);
        Assert.True(order.Id > Keys.NativeOrderIdStart);
        Assert.Empty(await sales.GetCartAsync(login.CustomerId));
        var read = await sales.GetOrderAsync(order.Id, consistent: true);
        Assert.Equal(2, read!.Lines.Count);
        Assert.Equal(order.TotalDue, read.TotalDue);
        Assert.Equal("ddb", read.Source);
        var next = await sales.NextOrderIdAsync();
        Assert.Equal(order.Id + 1, next);   // one atomic increment per order (P3-1)

        var history = await sales.GetOrdersForCustomerAsync(login.CustomerId, null);
        Assert.Contains(history.Items, o => o.Id == order.Id);   // DynamoDB Local GSIs are effectively immediate
    }

    [Fact] public async Task Product_admin_create_update_delete_keeps_unique_indexes()
    {
        if (!On) return;
        var c = new CatalogRepository(Tables());
        var name = "Test Product " + Guid.NewGuid().ToString("N")[..8];
        var id = await c.CreateProductAsync(new Models.Product { Name = name, ProductNumber = "TP-" + name[^8..], ListPrice = 10, SubcategoryId = 14 });
        var p = await c.GetProductAsync(id);
        Assert.Equal("Road Frames", p!.SubcategoryName);
        await Assert.ThrowsAsync<Amazon.DynamoDBv2.Model.TransactionCanceledException>(() =>
            c.CreateProductAsync(new Models.Product { Name = name, ProductNumber = "OTHER-" + name[^8..], ListPrice = 1 }));
        p.Name = name + " v2"; await c.UpdateProductAsync(p);
        Assert.Single(await c.SearchByPrefixAsync(name + " v2"));
        Assert.DoesNotContain(await c.SearchByPrefixAsync(name), x => x.Name == name);
        p.Version = 1;   // stale version -> rejected
        await Assert.ThrowsAsync<Amazon.DynamoDBv2.Model.TransactionCanceledException>(() => c.UpdateProductAsync(p));
        await c.DeleteProductAsync(id);
        Assert.Null(await c.GetProductAsync(id));
        await Assert.ThrowsAsync<InvalidOperationException>(() => c.DeleteProductAsync(680));
    }

    /// <summary>C2-2 end to end on DynamoDB Local: real pricing at checkout, approve, ship (stock, TXN, status), feed,
    /// conflicts (stale version, wrong status), review once per customer, price edit writes history.</summary>
    [Fact] public async Task Order_placed_approved_shipped_moves_stock()
    {
        if (!On) return;
        var t = Tables();
        var customers = new CustomerRepository(t);
        var login = (await customers.FindLoginAsync("walter0@adventure-works.com"))!;
        var view = (await customers.GetCustomerAsync(login.CustomerId))!;
        var catalog = new CatalogRepository(t);
        var pricing = new PricingRepository(t, new PricingOptions(), TimeProvider.System);
        var sales = new SalesRepository(t, TimeProvider.System, pricing, catalog);
        var f = new FulfilmentRepository(t, TimeProvider.System, pricing);
        Assert.Equal(5, (await pricing.GetShipMethodsAsync()).Count);

        foreach (var l in await sales.GetCartAsync(login.CustomerId)) await sales.RemoveAsync(login.CustomerId, l.ProductId);
        var helmet = (await catalog.GetProductAsync(707))!;     // Sport-100 Helmet, Red: has volume-discount offers
        await sales.AddToCartAsync(login.CustomerId, helmet, 12);
        var quote = await sales.QuoteAsync(login.CustomerId, view, 1);
        Assert.Equal(2, quote.Lines[0].SpecialOfferId);           // Volume Discount 11 to 14 (2 %), offer date 2014-05-01
        Assert.Equal(Math.Round(helmet.ListPrice * 0.98m * 12, 6), quote.Lines[0].LineTotal);
        var order = await sales.CheckoutAsync(login.CustomerId, view, login.Email, 1);
        Assert.Equal(quote.TotalDue, order.TotalDue);

        var before = await f.GetStockAsync(707);
        var queue = await f.QueueAsync(OrderStatus.InProcess, null, null, null, null, 500);
        Assert.Contains(queue.Items, o => o.Id == order.Id);
        await Assert.ThrowsAsync<ConflictException>(() => f.ApplyAsync(order.Id, "ship", 1, "test", new ShipRequest(1, "T1")));   // not approved yet
        var approved = await f.ApplyAsync(order.Id, "approve", 1, "test");
        Assert.Equal(OrderStatus.Approved, approved.Order.Status);
        await Assert.ThrowsAsync<ConflictException>(() => f.ApplyAsync(order.Id, "cancel", 1, "test"));                           // stale version
        var shipped = await f.ApplyAsync(order.Id, "ship", 2, "test", new ShipRequest(5, "1Z-IT-0001"));
        Assert.Equal("shipped", shipped.Outcome);

        var read = (await sales.GetOrderAsync(order.Id, true))!;
        Assert.Equal(OrderStatus.Shipped, read.Status); Assert.Equal("1Z-IT-0001", read.CarrierTrackingNumber); Assert.NotNull(read.ShipDate);
        Assert.All(read.Lines, l => Assert.Equal("1Z-IT-0001", l.CarrierTrackingNumber));
        Assert.Equal(new[] { "place", "approve", "ship" }, read.Events.Select(e => e.Action).ToArray());
        var after = await f.GetStockAsync(707);
        Assert.Equal(before.Total - 12, after.Total);
        Assert.DoesNotContain((await f.QueueAsync(OrderStatus.Approved, null, null, null, null, 500)).Items, o => o.Id == order.Id);   // left the sparse index
        var feed = await f.FeedAsync(20);
        Assert.Contains(feed, e => e.Event == "order.ship" && e.Subject == order.Number && e.Writes.Any(w => w.Contains("type S")));
    }

    [Fact] public async Task Review_once_per_customer_and_price_history()
    {
        if (!On) return;
        var t = Tables();
        var c = new CatalogRepository(t);
        var cid = 900_000 + Random.Shared.Next(1, 99_999);
        var r = await c.AddReviewAsync(709, cid, "IT Reviewer", "it@x", 4, "Comfortable socks, would buy again.", DateTime.UtcNow);
        Assert.Contains(await c.GetReviewsAsync(709), x => x.Id == r.Id);
        await Assert.ThrowsAsync<Amazon.DynamoDBv2.Model.TransactionCanceledException>(() => c.AddReviewAsync(709, cid, "IT", "it@x", 5, "Second review is refused.", DateTime.UtcNow));

        var p = (await c.GetProductAsync(680))!;
        var newPrice = p.ListPrice + 1;
        var updated = await c.SetListPriceAsync(680, newPrice, p.Version);
        Assert.Equal(newPrice, updated.ListPrice);
        var hist = await c.GetPriceHistoryAsync(680);
        Assert.Equal(newPrice, hist[^1].ListPrice); Assert.Null(hist[^1].EndDate); Assert.Equal(DateTime.UtcNow.Date, hist[^1].StartDate);
        Assert.Single(hist, h => h.EndDate is null);
    }

    /// <summary>C2-3 end to end on DynamoDB Local: INV-02 suggestion -> PUR-04 create -> approve -> partial receipt (with a
    /// reject) -> final receipt; stock, TransactionHistory P, REORDER marker, PUR-05/06/07 and the change feed follow.</summary>
    [Fact] public async Task Procurement_suggest_create_approve_receive()
    {
        if (!On) return;
        var t = Tables();
        var pricing = new PricingRepository(t, new PricingOptions(), TimeProvider.System);
        var f = new FulfilmentRepository(t, TimeProvider.System, pricing);
        var p = new ProcurementRepository(t, TimeProvider.System, f);

        var vendors = await p.ListVendorsAsync();
        Assert.Equal(104, vendors.Count);
        Assert.NotEmpty((await p.ForEmployeeAsync(251, null)).Items);          // Mikael Sandberg's SQL-era POs (PUR-06)
        Assert.NotEmpty((await p.ForEmployeeAsync(250, null)).Items);          // Sheela Word
        var openBefore = await p.OpenCountsAsync();
        Assert.True(openBefore[1] > 0 && openBefore[2] > 0);                    // SQL-era open POs (PUR-07 markers)

        var sugg = await p.SuggestionsAsync();
        var s = sugg.First(x => x.Vendor is not null && x.SuggestedQty > 0);
        Assert.True(s.StockQty < s.ReorderPoint);
        var buyer = new StaffUser("mikael0@adventure-works.com", "Mikael Sandberg", 251);
        var qty = Math.Min(s.SuggestedQty, 50);
        var po = await p.CreateAsync(new CreatePoRequest(s.Vendor!.VendorId, 3, [new PoLineRequest(s.ProductId, qty)]), buyer, await pricing.GetShipMethodsAsync());
        Assert.True(po.Id >= Keys.NativePoIdStart); Assert.Equal(PoStatus.Pending, po.Status); Assert.Equal("ddb", po.Source);
        Assert.Contains((await p.OpenAsync(1, null, 1000)).Items, x => x.Id == po.Id);
        Assert.Contains((await p.ForEmployeeAsync(251, null)).Items, x => x.Id == po.Id);
        Assert.Contains(await p.ForVendorAsync(s.Vendor.VendorId), x => x.Id == po.Id);
        Assert.Contains((await p.SuppliersAsync(s.ProductId)), v => v.VendorId == s.Vendor.VendorId && v.OnOrderQty >= qty);

        await Assert.ThrowsAsync<ConflictException>(() => p.ReceiveAsync(po.Id, new ReceiveRequest(po.Version, [new(po.Lines[0].DetailId, 1, 0, null)]), "x"));   // pending
        var ap = await p.TransitionAsync(po.Id, "approve", po.Version, "sheela0@adventure-works.com", null);
        Assert.Equal(PoStatus.Approved, ap.Order.Status);
        await Assert.ThrowsAsync<ConflictException>(() => p.TransitionAsync(po.Id, "approve", po.Version, "x", null));   // stale version

        var stock0 = await f.GetStockAsync(s.ProductId);
        var first = qty > 1 ? qty / 2 : qty;
        var rejected = first > 1 ? 1 : 0;
        var r1 = await p.ReceiveAsync(po.Id, new ReceiveRequest(ap.Order.Version, [new(po.Lines[0].DetailId, first, rejected, null)]), "mikael0@adventure-works.com");
        var stock1 = await f.GetStockAsync(s.ProductId);
        Assert.Equal(stock0.Total + first - rejected, stock1.Total);
        Assert.Equal(first, r1.Order.Lines[0].ReceivedQty); Assert.Equal(rejected, r1.Order.Lines[0].RejectedQty);
        Assert.NotNull(r1.Order.ShipDate);
        if (first < qty)
        {
            Assert.Equal("partially-received", r1.Outcome);
            var r2 = await p.ReceiveAsync(po.Id, new ReceiveRequest(r1.Order.Version, [new(po.Lines[0].DetailId, qty - first, 0, 6)]), "mikael0@adventure-works.com");
            Assert.Equal("complete", r2.Outcome);
            Assert.Equal(stock1.Total + qty - first, (await f.GetStockAsync(s.ProductId)).Total);
        }
        var done = (await p.GetOrderAsync(po.Id))!;
        Assert.Equal(PoStatus.Complete, done.Status);
        Assert.Equal(new[] { "create", "approve", "receive" }, done.Events.Select(e => e.Action).Distinct().ToArray());
        Assert.DoesNotContain((await p.OpenAsync(2, null, 1000)).Items, x => x.Id == po.Id);

        var inv = t.For(DynamoTables.Inventory);
        var txns = await inv.QueryAll(new Amazon.DynamoDBv2.Model.QueryRequest { TableName = "aw-inventory", KeyConditionExpression = "PK = :pk AND begins_with(SK, :t)",
            FilterExpression = "reference_order_id = :po", ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.InvProduct(s.ProductId)), [":t"] = Av.S("TXN#"), [":po"] = Av.N(po.Id) } });
        Assert.Equal(qty - rejected, txns.Sum(x => x.Dec("quantity")));
        Assert.All(txns, x => Assert.Equal("P", x.Str("transaction_type")));
        var feed = await f.FeedAsync(100);
        Assert.Contains(feed, e => e.Event == "po.receive" && e.Subject == po.Number && e.Writes.Any(w => w.Contains("type P")));
        Assert.Contains(feed, e => e.Event == "po.create" && e.Subject == po.Number);
        var perf = await p.PerformanceAsync(s.Vendor.VendorId, await p.ForVendorAsync(s.Vendor.VendorId));
        Assert.True(perf.Orders >= 1 && perf.Received >= qty);
    }

    /// <summary>C2-4 end to end on DynamoDB Local: INV-06 by due month, INV-04 explosion, INV-05 where-used, KPIs, then plan ->
    /// create -> record an operation -> complete with scrap; product stock in, components out (TXN W), REORDER, feed.</summary>
    [Fact] public async Task Production_bom_work_order_create_operate_complete()
    {
        if (!On) return;
        var t = Tables();
        var pricing = new PricingRepository(t, new PricingOptions(), TimeProvider.System);
        var f = new FulfilmentRepository(t, TimeProvider.System, pricing);
        var p = new ProductionRepository(t, TimeProvider.System, f);

        var may = await p.ForMonthAsync("2014-05");
        Assert.True(may.Total > 1000);                                             // SQL-era work orders due in May 2014 (GSI2 WODUE#2014-05)
        Assert.All(may.Items, w => Assert.NotEqual("Open", w.State));              // all historical work orders are closed
        Assert.Contains(may.Items, w => w.ScrapReason is not null);
        var one = may.Items.First();
        var detail = (await p.GetAsync(one.Id))!;
        Assert.True(detail.ReadOnly); Assert.Empty(detail.Actions);
        var reasons = await p.ScrapReasonsAsync();
        Assert.Equal(16, reasons.Count);
        var k = await p.KpisAsync("2014-01", "2014-06");
        Assert.True(k.WorkOrders > 5000 && k.ScrapRate > 0 && k.ScrapRate < 0.05m && k.OnTimeRate > 0.3m && k.OnTimeRate <= 1);

        var assemblies = await p.AssembliesAsync();
        Assert.True(assemblies.Count > 50);
        var bike = assemblies.First(a => a.Name.StartsWith("Road-150", StringComparison.Ordinal));
        var tree = await p.ExplodeAsync(bike.ProductId, DateTime.UtcNow);
        Assert.True(tree.Root.Children.Count >= 5 && tree.Nodes > tree.Root.Children.Count);   // multi-level
        var leaf = ProductionRepository.Flatten(tree.Root).Last(n => n.Level >= 2);
        var used = await p.WhereUsedAsync(leaf.ProductId, DateTime.UtcNow);
        Assert.NotEmpty(used.Root.Children);

        ProductionPlan? plan = null;
        foreach (var a in assemblies.Take(80))
        {
            var pl = await p.PlanAsync(a.ProductId, 2);
            if (pl.Feasible && pl.Components.Count > 0) { plan = pl; break; }
        }
        Assert.NotNull(plan);
        var w = await p.CreateAsync(new CreateWorkOrderRequest(plan!.ProductId, 2, null), "production@adventure-works.com");
        Assert.True(w.Order.Id >= ProductionRepository.NativeWoIdStart); Assert.Equal("Open", w.Order.State); Assert.False(w.ReadOnly);
        Assert.Equal(plan.Routing.Count, w.Routing.Count);
        Assert.Contains(await p.OpenAsync(), x => x.Id == w.Order.Id);
        var op = await p.RecordOperationAsync(w.Order.Id, new OperationRequest(w.Version, 3.5m), "production@adventure-works.com");
        Assert.True(op.Order.Routing[0].Done); Assert.Equal(3.5m, op.Order.Routing[0].ActualResourceHrs);
        await Assert.ThrowsAsync<ConflictException>(() => p.RecordOperationAsync(w.Order.Id, new OperationRequest(w.Version, 1), "x"));   // stale version

        var before = await f.GetStockAsync(plan.ProductId);
        var compBefore = new Dictionary<int, decimal>();
        foreach (var c in plan.Components) compBefore[c.ProductId] = (await f.GetStockAsync(c.ProductId)).Total;
        var reason = reasons.Keys.Min();
        var done = await p.CompleteAsync(w.Order.Id, new CompleteWorkOrderRequest(op.Order.Version, 1, reason, null), "production@adventure-works.com");
        Assert.NotEqual("Open", done.Order.Order.State);
        Assert.Equal(1, done.Order.Order.StockedQty); Assert.Equal(1, done.Order.Order.ScrappedQty); Assert.Equal(reasons[reason], done.Order.Order.ScrapReason);
        Assert.All(done.Order.Routing, r => Assert.True(r.Done));
        Assert.Equal(before.Total + 1, (await f.GetStockAsync(plan.ProductId)).Total);
        foreach (var c in plan.Components) Assert.Equal(compBefore[c.ProductId] - c.Required, (await f.GetStockAsync(c.ProductId)).Total);
        var inv = t.For(DynamoTables.Inventory);
        var txns = await inv.QueryAll(new Amazon.DynamoDBv2.Model.QueryRequest { TableName = "aw-inventory", KeyConditionExpression = "PK = :pk AND begins_with(SK, :t)",
            FilterExpression = "reference_order_id = :wo", ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.InvProduct(plan.ProductId)), [":t"] = Av.S("TXN#"), [":wo"] = Av.N(w.Order.Id) } });
        Assert.Equal("W", Assert.Single(txns).Str("transaction_type"));
        var feed = await f.FeedAsync(100);
        Assert.Contains(feed, e => e.Event == "wo.complete" && e.Subject == w.Order.Number && e.Writes.Any(x => x.Contains("type W")));
        Assert.Contains(feed, e => e.Event == "wo.create" && e.Subject == w.Order.Number);
        await Assert.ThrowsAsync<ConflictException>(() => p.CompleteAsync(w.Order.Id, new CompleteWorkOrderRequest(done.Order.Version, 0, null, null), "x"));   // closed
    }
}
