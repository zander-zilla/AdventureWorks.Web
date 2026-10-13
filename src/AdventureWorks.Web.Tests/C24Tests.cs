using AdventureWorks.Web.Data;
using Amazon.DynamoDBv2.Model;

namespace AdventureWorks.Web.Tests;

/// <summary>C2-4 pure logic: derived work-order state, standard routing, BOM validity, create / operation / complete
/// transactions, scrap and on-time KPIs.</summary>
public class ProductionTests
{
    private static readonly DateTime Now = new(2026, 10, 12, 18, 0, 0);
    private static readonly DynamoTables T = new(new DynamoOptions());

    private static WorkOrderSummary Wo(int id = 100_000, int qty = 10, DateTime? end = null, DateTime? due = null, int scrapped = 0, string? reason = null) =>
        new(id, ProductionRepository.WoNumber(id), 749, "Road-150 Red, 62", qty, end is null ? 0 : qty - scrapped, scrapped, new DateTime(2026, 10, 13), end,
            due ?? new DateTime(2026, 10, 17), ProductionRepository.State(end, due ?? new DateTime(2026, 10, 17)), reason, "ddb");

    private static WorkOrderDetail Detail(WorkOrderSummary s, params RoutingStep[] steps) =>
        new(s, 3, s.Id < ProductionRepository.NativeWoIdStart, ProductionRepository.Actions(s.Id < ProductionRepository.NativeWoIdStart, s, steps.ToList()), steps.ToList(), []);

    private static RoutingStep Step(int seq, int loc, DateTime? actualEnd = null) =>
        new(seq, loc, ProductionRepository.WorkCentres[loc].Name, new DateTime(2026, 10, 12 + seq), new DateTime(2026, 10, 13 + seq), actualEnd?.AddHours(-4), actualEnd,
            actualEnd is null ? null : 4, 49, actualEnd is null ? null : 49, false, actualEnd is not null);

    private static FulfilmentRepository.Stock S(int pid, decimal total, int rop = 0, int loc = 7) => new(pid, [(loc, "Finished Goods Storage", total)], total, rop, true);

    [Theory]
    [InlineData(null, "Open")] [InlineData("2026-10-17T23:00:00", "Closed on time")] [InlineData("2026-10-18T08:00:00", "Closed late")]
    public void State_is_derived_like_the_evidence_query(string? end, string state) =>
        Assert.Equal(state, ProductionRepository.State(end is null ? null : DateTime.Parse(end), new DateTime(2026, 10, 17)));

    [Fact] public void Numbers_keys_and_buckets()
    {
        Assert.Equal("WO-DDB-100004", ProductionRepository.WoNumber(100_004));
        Assert.Equal("WO000013", ProductionRepository.WoNumber(13));
        Assert.Equal("WODUE#2026-11", ProductionRepository.DueBucket(new DateTime(2026, 11, 2)));
        Assert.Equal("ASSEMBLY#ROOT", ProductionRepository.Assembly(null));
        Assert.Equal("ASSEMBLY#000749", ProductionRepository.Assembly(749));
    }

    [Fact] public void Standard_routing_frames_vs_assemblies()
    {
        var frame = ProductionRepository.StandardRouting("HL Road Frame - Red, 62", false, new DateTime(2026, 10, 13));
        Assert.Equal(new[] { 10, 20, 30, 40 }, frame.Select(s => s.LocationId));
        Assert.Equal(new DateTime(2026, 10, 17), frame.Last().ScheduledEndDate);
        Assert.Equal(4 * 22.50m, frame[0].PlannedCost);
        Assert.Equal(new[] { 50, 60 }, ProductionRepository.StandardRouting("Road-150 Red, 62", true, Now).Select(s => s.LocationId));
        Assert.Equal(new[] { 50 }, ProductionRepository.StandardRouting("HL Crankarm", false, Now).Select(s => s.LocationId));
    }

    [Fact] public void Bom_edges_are_valid_in_their_date_window()
    {
        var e = new Dictionary<string, AttributeValue> { ["start_date"] = Av.S("2010-05-26T00:00:00"), ["end_date"] = Av.S("2011-01-01T00:00:00") };
        Assert.True(ProductionRepository.ValidAt(e, new DateTime(2010, 6, 1)));
        Assert.False(ProductionRepository.ValidAt(e, new DateTime(2011, 1, 1)));
        Assert.False(ProductionRepository.ValidAt(e, new DateTime(2010, 5, 1)));
        e.Remove("end_date");
        Assert.True(ProductionRepository.ValidAt(e, Now));
        Assert.Equal(3, ProductionRepository.Required(1.5m, 2));
        Assert.Equal(2, ProductionRepository.Required(0.2m, 10));
    }

    [Fact] public void Actions_follow_routing_progress()
    {
        Assert.Equal(new[] { "record-operation", "complete" }, Detail(Wo(), Step(1, 50), Step(2, 60)).Actions);
        Assert.Equal(new[] { "complete" }, Detail(Wo(), Step(1, 50, Now), Step(2, 60, Now)).Actions);
        Assert.Empty(Detail(Wo(end: Now)).Actions);
        Assert.Empty(Detail(Wo(id: 13)).Actions);            // SQL-era: read-only
    }

    [Fact] public void Create_plan_writes_header_with_due_month_index_routing_event_and_feed()
    {
        var routing = ProductionRepository.StandardRouting("Road-150 Red, 62", true, new DateTime(2026, 10, 13));
        var p = new ProductionPlan(749, "Road-150 Red, 62", 5, new DateTime(2026, 10, 13), new DateTime(2026, 11, 2), routing, [], true, []);
        var plan = ProductionRepository.CreatePlan(T, 100_000, p, "production@x", Now);
        Assert.Equal(1 + 2 + 2, plan.Count);
        var h = plan[0].Action.Put.Item;
        Assert.Equal("WO#100000", h["PK"].S); Assert.Equal("WODUE#2026-11", h["GSI2PK"].S); Assert.Equal("2026-11-02T00:00:00#100000", h["GSI2SK"].S);
        Assert.Equal("~app", h["src_lsn"].S); Assert.False(h.ContainsKey("end_date"));
        Assert.Equal("ROUTING#002#060", plan[2].Action.Put.Item["SK"].S);
        Assert.Equal(DynamoTables.Sales, plan[^1].Table);
    }

    [Fact] public void Operation_starts_where_the_previous_one_ended()
    {
        var done = new DateTime(2026, 10, 14, 9, 0, 0);
        var w = Detail(Wo(), Step(1, 50, done), Step(2, 60));
        var (s, start) = ProductionRepository.NextStep(w, new DateTime(2026, 10, 15));
        Assert.Equal(2, s.OperationSequence); Assert.Equal(done, start);
        var plan = ProductionRepository.OperationPlan(T, w, 3.5m, "x", new DateTime(2026, 10, 15));
        var u = plan[1].Action.Update;
        Assert.Equal("3.5", u.ExpressionAttributeValues[":h"].N); Assert.Equal((3.5m * 12.25m).ToString(System.Globalization.CultureInfo.InvariantCulture), u.ExpressionAttributeValues[":c"].N);
        Assert.Equal("ver = :v AND attribute_not_exists(end_date)", plan[0].Action.Update.ConditionExpression);
        Assert.Throws<ConflictException>(() => ProductionRepository.NextStep(Detail(Wo(), Step(1, 50, done)), Now));
    }

    [Fact] public void Completion_stocks_the_product_consumes_components_and_closes_open_steps()
    {
        var w = Detail(Wo(qty: 10), Step(1, 50, new DateTime(2026, 10, 14)), Step(2, 60));
        var comps = new List<ProductionRepository.Consumption> { new(994, "LL Bottom Bracket", 10, 6, S(994, 40, 50, 6)), new(950, "ML Crankset", 10, 6, S(950, 100, 0, 6)) };
        var plan = ProductionRepository.CompletePlan(T, w, new(3, 2, 1, null), "Brake assembly not as ordered", 7, S(749, 20, 10), comps, "production@x", Now, 10_000_500);
        Assert.Equal(ProductionRepository.CompletionItems(1, 2, true), plan.Count);
        var h = plan[0].Action.Update;
        Assert.Equal("8", h.ExpressionAttributeValues[":stk"].N); Assert.Equal("2", h.ExpressionAttributeValues[":scr"].N); Assert.Equal("1", h.ExpressionAttributeValues[":r"].N);
        Assert.Contains(plan, p => p.Action.Update?.Key["SK"].S == "ROUTING#002#060");
        var txns = plan.Where(p => p.Action.Put?.Item["type"].S == "InventoryTransaction").Select(p => p.Action.Put.Item).ToList();
        Assert.All(txns, x => Assert.Equal("W", x["transaction_type"].S));
        Assert.Equal(new[] { "8", "-10", "-10" }, txns.Select(x => x["quantity"].N));
        var compInv = plan.Single(p => p.Action.Update?.Key["PK"].S == "PRODUCT#000994" && p.Action.Update.Key["SK"].S == "INV#006").Action.Update;
        Assert.Equal("quantity >= :need", compInv.ConditionExpression);
        var compTotal = plan.Single(p => p.Action.Update?.Key["PK"].S == "PRODUCT#000994" && p.Action.Update.Key["SK"].S == "PRODUCT" && p.Table == DynamoTables.Inventory).Action.Update;
        Assert.Contains("GSI1PK = :r", compTotal.UpdateExpression);   // 40 - 10 = 30 < 50: now on the REORDER index (C2-3 suggestions)
        Assert.Equal(DynamoTables.Inventory, plan[0].Table);
        Assert.Equal(DynamoTables.Sales, plan[^1].Table);
    }

    [Fact] public void Fully_scrapped_order_stocks_nothing()
    {
        var w = Detail(Wo(qty: 2), Step(1, 50, Now));
        var plan = ProductionRepository.CompletePlan(T, w, new(3, 2, 7, null), "Gouge in metal", 7, S(749, 20), [], "x", Now, 1);
        Assert.DoesNotContain(plan, p => p.Table == DynamoTables.Catalog || p.Action.Put?.Item["type"].S == "InventoryTransaction");
    }

    [Fact] public void Completion_validation()
    {
        var w = Detail(Wo(qty: 5));
        var reasons = new Dictionary<int, string> { [1] = "Brake assembly not as ordered" };
        Assert.Throws<ArgumentException>(() => ProductionRepository.ValidateCompletion(w, new(3, 6, 1, null), reasons));
        Assert.Throws<ArgumentException>(() => ProductionRepository.ValidateCompletion(w, new(3, 1, null, null), reasons));
        Assert.Throws<ArgumentException>(() => ProductionRepository.ValidateCompletion(w, new(3, 0, 1, null), reasons));
        Assert.Throws<ArgumentException>(() => ProductionRepository.ValidateCompletion(w, new(3, 0, null, 99), reasons));
        ProductionRepository.ValidateCompletion(w, new(3, 1, 1, 7), reasons);
    }

    [Fact] public void Largest_completion_fits_one_transaction()
    {
        // a bike has at most ~15 level-1 components; 22 with 7 routing steps passes the 100-item limit
        Assert.True(ProductionRepository.CompletionItems(7, 21, true) <= ProductionRepository.MaxTransactionItems);
        Assert.True(ProductionRepository.CompletionItems(7, 22, true) > ProductionRepository.MaxTransactionItems);
    }

    [Fact] public void Kpis_scrap_rate_and_on_time_rate()
    {
        var due = new DateTime(2014, 5, 10);
        var may = new List<WorkOrderSummary>
        {
            Wo(1, 100, due.AddDays(-1), due, 2, "Gouge in metal"), Wo(2, 100, due.AddDays(3), due), Wo(3, 50, due, due, 1, "Gouge in metal"), Wo(4, 50, null, due),
        };
        var k = ProductionRepository.Kpis("2014-05", "2014-06", [("2014-05", may), ("2014-06", [])]);
        Assert.Equal(4, k.WorkOrders); Assert.Equal(300, k.OrderQty); Assert.Equal(3, k.ScrappedQty);
        Assert.Equal(0.01m, k.ScrapRate); Assert.Equal(0.6667m, k.OnTimeRate); Assert.Equal(1, k.Open);
        Assert.Equal(new ReasonCount("Gouge in metal", 2, 3), k.ScrapReasons.Single());
        Assert.Equal(0, k.Months[1].ScrapRate);
        Assert.Equal(24, ProductionRepository.MonthRange("2013-01", "2014-12").Count());
        Assert.Throws<ArgumentException>(() => ProductionRepository.MonthRange("2013-01", "2015-01").ToList());
        Assert.Throws<ArgumentException>(() => ProductionRepository.MonthRange("2014-02", "2014-01").ToList());
    }
}
