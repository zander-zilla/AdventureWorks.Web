using AdventureWorks.Web.Data;

namespace AdventureWorks.Web.Tests;

/// <summary>Against DynamoDB Local loaded by the Phase 3 loader (DDB_MULTI ports 8001.., set AW_DDB_IT=1).</summary>
public class IntegrationTests
{
    private static readonly bool On = Environment.GetEnvironmentVariable("AW_DDB_IT") == "1";
    private static DynamoTables Tables()
    {
        var b = int.Parse(Environment.GetEnvironmentVariable("DDB_PORT_BASE") ?? "8001");
        return new DynamoTables(new DynamoOptions { Endpoints = new()
        {
            ["aw-catalog"] = $"http://localhost:{b}", ["aw-customer"] = $"http://localhost:{b + 1}", ["aw-inventory"] = $"http://localhost:{b + 3}",
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
}
