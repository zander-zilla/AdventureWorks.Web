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
            ["aw-catalog"] = $"http://localhost:{b}", ["aw-customer"] = $"http://localhost:{b + 1}", ["aw-sales"] = $"http://localhost:{b + 6}",
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
}
