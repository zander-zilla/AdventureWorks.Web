using AdventureWorks.Web.Data;
using AdventureWorks.Web.Models;

namespace AdventureWorks.Web.Tests;

/// <summary>C2-2 pure logic: pricing, status machine, ship transaction, price history, review validation.</summary>
public class PricingTests
{
    private static readonly DateTime AsOf = new(2014, 5, 1);
    private static readonly ShipMethodInfo Truck = new(1, "XRQ - TRUCK GROUND", 3.95m, 0.99m);
    private static OfferInfo Vol(int id, decimal pct, int min, int? max) => new(id, $"Volume Discount {min} to {max}", pct, "Volume Discount", "Reseller",
        new DateTime(2011, 5, 31), new DateTime(2014, 5, 30), min, max);
    private static readonly List<OfferInfo> Tiers = [new(1, "No Discount", 0, "No Discount", "No Discount", new DateTime(2011, 5, 1), new DateTime(2014, 11, 30), 0, null),
        Vol(2, 0.02m, 11, 14), Vol(3, 0.05m, 15, 24), Vol(4, 0.10m, 25, 40), Vol(5, 0.15m, 41, 60), Vol(6, 0.20m, 61, null)];

    [Theory]
    [InlineData(1, 1, 0)]
    [InlineData(11, 2, 0.02)]
    [InlineData(14, 2, 0.02)]
    [InlineData(15, 3, 0.05)]
    [InlineData(70, 6, 0.20)]
    public void Volume_discount_tiers(int qty, int offer, double pct)
    {
        var q = Pricing.Price([new PricingItem(707, "Sport-100 Helmet, Red", "HL-U509-R", qty, 34.99m, null, null, Tiers)], null, Truck, AsOf);
        Assert.Equal(offer, q.Lines[0].SpecialOfferId);
        Assert.Equal((decimal)pct, q.Lines[0].UnitPriceDiscount);
        Assert.Equal(Math.Round(34.99m * (1 - (decimal)pct) * qty, 6), q.Lines[0].LineTotal);
    }

    [Fact] public void Expired_offers_do_not_apply()
    {
        var q = Pricing.Price([new PricingItem(707, "Helmet", "HL", 20, 34.99m, null, null, Tiers)], null, Truck, new DateTime(2026, 10, 12));
        Assert.Equal(1, q.Lines[0].SpecialOfferId); Assert.Equal(0, q.Discount);
    }

    [Fact] public void Best_offer_wins_and_ties_take_the_lowest_id()
    {
        var a = new OfferInfo(9, "A", 0.15m, "Seasonal Discount", "Customer", AsOf, AsOf, 0, null);
        var b = new OfferInfo(8, "B", 0.15m, "Seasonal Discount", "Customer", AsOf, AsOf, 0, null);
        Assert.Equal(8, Pricing.BestOffer([a, b, Vol(3, 0.05m, 1, 99)], 5, AsOf)!.Id);
    }

    [Fact] public void Tax_and_freight_and_redshift_allocation()
    {
        var tax = new TaxInfo(1, "AB", "Alberta", 6, 0.14m, "Canadian GST + Alberta Provincial Tax");
        var q = Pricing.Price([
            new PricingItem(771, "Mountain-100 Silver, 38", "BK-M82S-38", 1, 3399.99m, 20.35m, "LB", []),
            new PricingItem(707, "Helmet", "HL", 2, 34.99m, 500m, "G", []),
        ], tax, Truck, AsOf);
        Assert.Equal(3469.97m, q.SubTotal);
        Assert.Equal(Pricing.Money(3469.97m * 0.14m), q.TaxAmt);
        Assert.Equal(Pricing.Money(3.95m + 0.99m * (20.35m + 2 * 500m / 453.59237m)), q.Freight);
        // Redshift (03_facts.sql) allocates header tax/freight by line_total / sub_total; the sum differs by rounding only.
        Assert.InRange(q.Lines.Sum(l => l.TaxAllocated) - q.TaxAmt, -0.0002m, 0.0002m);
        Assert.Equal(Pricing.Money(q.TaxAmt * 3399.99m / 3469.97m), q.Lines[0].TaxAllocated);
    }

    [Fact] public void Retail_rate_prefers_type_1_then_3_and_ignores_wholesale()
    {
        Assert.Equal(0.14m, Pricing.RetailRate([(1, 14m), (2, 7m), (3, 7m)]));
        Assert.Equal(0.07m, Pricing.RetailRate([(3, 7m), (2, 5m)]));
        Assert.Null(Pricing.RetailRate([(2, 5m)]));
        Assert.Null(Pricing.RetailRate([]));
    }

    [Fact] public void Missing_weight_ships_as_one_pound() => Assert.Equal(1m, Pricing.WeightLb(null, null));
}

public class OrderStatusTests
{
    [Theory]
    [InlineData("approve", 1, true)] [InlineData("approve", 2, false)] [InlineData("ship", 2, true)] [InlineData("ship", 3, true)]
    [InlineData("ship", 1, false)] [InlineData("cancel", 5, false)] [InlineData("cancel", 3, true)] [InlineData("backorder", 2, true)]
    [InlineData("reject", 1, true)] [InlineData("reject", 2, false)] [InlineData("nope", 1, false)]
    public void Transitions_are_enforced(string action, int from, bool ok) => Assert.Equal(ok, OrderStatus.CanApply(action, from));

    [Fact] public void Text_matches_ufnGetSalesOrderStatusText()
    {
        Assert.Equal(new[] { "In process", "Approved", "Backordered", "Rejected", "Shipped", "Cancelled" }, Enumerable.Range(1, 6).Select(OrderStatus.Text));
        Assert.True(OrderStatus.IsOpen(3)); Assert.False(OrderStatus.IsOpen(5));
        Assert.Equal(new[] { "approve", "reject", "backorder", "cancel" }, OrderStatus.AllowedActions(1));
    }

    [Fact] public void Leaving_open_statuses_removes_the_sparse_gsi()
    {
        var o = new Order { Id = 1_000_000_001, Status = 2, Version = 4, OrderDate = new DateTime(2026, 10, 12, 1, 2, 3) };
        var u = FulfilmentRepository.HeaderUpdate("aw-sales", o, OrderStatus.Cancelled, DateTime.UtcNow);
        Assert.EndsWith("REMOVE GSI2PK, GSI2SK", u.UpdateExpression);
        Assert.Equal("ver = :v AND #s = :from", u.ConditionExpression);
        Assert.Equal("4", u.ExpressionAttributeValues[":v"].N);
        var b = FulfilmentRepository.HeaderUpdate("aw-sales", o, OrderStatus.Backordered, DateTime.UtcNow);
        Assert.Equal("ORDERSTATUS#3", b.ExpressionAttributeValues[":g"].S);
        Assert.Equal("2026-10-12T01:02:03#1000000001", b.ExpressionAttributeValues[":gs"].S);
    }
}

public class ShipPlanTests
{
    private static FulfilmentRepository.Stock S(int pid, params (int loc, decimal q)[] l) =>
        new(pid, l.Select(x => (x.loc, (string?)$"L{x.loc}", x.q)).ToList(), l.Sum(x => x.q), 10, true);

    [Fact] public void Allocation_picks_one_location_that_covers_the_quantity()
    {
        var (a, s) = FulfilmentRepository.Allocate([(771, "Bike", 2), (771, "Bike", 1), (707, "Helmet", 5)],
            new Dictionary<int, FulfilmentRepository.Stock> { [771] = S(771, (1, 2), (7, 4)), [707] = S(707, (7, 4)) });
        Assert.Equal(7, a.Single().LocationId); Assert.Equal(3, a.Single().Quantity);
        Assert.Single(s); Assert.Contains("need 5", s[0]);
    }

    [Fact] public void Ship_is_one_transaction_with_stock_movement_and_status()
    {
        var t = new DynamoTables(new DynamoOptions());
        var o = new Order { Id = 1_000_000_009, Number = "SO-DDB-1000000009", Status = 2, Version = 2, OrderDate = new DateTime(2026, 10, 12) };
        o.Lines.Add(new OrderLine(1, 771, "Bike", "BK", 1, 3399.99m, 3399.99m));
        o.Lines.Add(new OrderLine(2, 707, "Helmet", "HL", 3, 34.99m, 104.97m));
        var alloc = new List<StockAllocation> { new(771, 7, 1, 4, 6, 10), new(707, 7, 3, 50, 50, 10) };
        var now = new DateTime(2026, 10, 12, 18, 0, 0);
        var plan = FulfilmentRepository.ShipPlan(t, o, alloc, new ShipMethodInfo(5, "CARGO TRANSPORT 5", 8.99m, 1.49m), "1Z999", "ops@x", now, 10_000_001);
        Assert.True(plan.Count <= 100);
        Assert.Equal(1 + 2 * 3 + 2 * 2 + 2, plan.Count);
        Assert.Equal(DynamoTables.Inventory, plan[0].Table);                      // stock conditions first
        Assert.Equal("quantity >= :q", plan[0].Action.Update.ConditionExpression);
        var bikeProduct = plan[1].Action.Update;
        Assert.Contains("GSI1PK = :r", bikeProduct.UpdateExpression);           // 6 - 1 = 5 < reorder point 10 -> REORDER index
        Assert.Contains("REMOVE GSI1PK", plan[3].Action.Update.UpdateExpression);
        var txns = plan.Where(p => p.Action.Put?.Item["type"].S == "InventoryTransaction").Select(p => p.Action.Put.Item).ToList();
        Assert.Equal(2, txns.Count);
        Assert.All(txns, x => { Assert.Equal("S", x["transaction_type"].S); Assert.Equal("1000000009", x["reference_order_id"].N); Assert.Equal(Keys.AppLsn, x["src_lsn"].S); });
        Assert.Equal("TXN#2026-10-12T18:00:00#10000001", txns[0]["SK"].S);
        var header = plan.Single(p => p.Action.Update?.Key["SK"].S == "ORDER").Action.Update;
        Assert.Equal("5", header.ExpressionAttributeValues[":to"].N);
        Assert.Equal("1Z999", header.ExpressionAttributeValues[":x_carrier_tracking_number"].S);
        Assert.Equal("ChangeFeed", plan[^1].Action.Put.Item["type"].S);
        Assert.Contains(plan[^1].Action.Put.Item["writes"].L, w => w.S.Contains("stg.inventory_transaction"));
    }

    [Fact] public void Groups_follow_table_order_for_the_per_table_local_layout()
    {
        var local = new DynamoTables(new DynamoOptions { Endpoints = new() { ["aw-sales"] = "http://localhost:8007", ["aw-inventory"] = "http://localhost:8004", ["aw-catalog"] = "http://localhost:8001" } });
        Assert.False(local.SingleEndpoint(DynamoTables.Sales, DynamoTables.Inventory));
        Assert.True(new DynamoTables(new DynamoOptions()).SingleEndpoint(DynamoTables.Sales, DynamoTables.Inventory, DynamoTables.Catalog));
    }
}

public class CatalogFixTests
{
    [Fact] public void Price_change_closes_the_open_history_item_and_adds_today()
    {
        var today = new DateTime(2026, 10, 12);
        var hist = new List<CatalogRepository.PricePoint> { new(new DateTime(2011, 5, 31), new DateTime(2012, 5, 29), 3399.99m, "sql"), new(new DateTime(2013, 5, 30), null, 3374.99m, "sql") };
        var tx = CatalogRepository.PriceHistoryActions("aw-catalog", 771, 3199.99m, today, hist);
        Assert.Equal(2, tx.Count);
        Assert.Equal("PRICE#2013-05-30T00:00:00", tx[0].Update.Key["SK"].S);
        Assert.Equal("2026-10-11T00:00:00", tx[0].Update.ExpressionAttributeValues[":e"].S);
        var put = tx[1].Put.Item;
        Assert.Equal("PRICE#2026-10-12T00:00:00", put["SK"].S); Assert.Equal("ListPriceHistory", put["type"].S);
        Assert.Equal("3199.99", put["list_price"].N); Assert.False(put.ContainsKey("end_date"));
    }

    [Fact] public void Second_change_on_the_same_day_replaces_todays_item()
    {
        var today = new DateTime(2026, 10, 12);
        var tx = CatalogRepository.PriceHistoryActions("aw-catalog", 771, 10m, today, [new(today, null, 11m, "ddb")]);
        Assert.Single(tx);
    }

    [Theory]
    [InlineData(5, "Great bike, rides well.", null)]
    [InlineData(0, "Great bike, rides well.", "Rating must be 1 to 5.")]
    [InlineData(4, "short", "Please write at least 10 characters.")]
    [InlineData(4, "This is crap, honestly.", "Please keep it friendly (blocked word).")]
    public void Review_validation(int rating, string text, string? error) => Assert.Equal(error, CatalogRepository.ValidateReview(rating, text));
}
