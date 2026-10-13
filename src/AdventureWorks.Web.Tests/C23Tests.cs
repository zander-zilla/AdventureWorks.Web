using AdventureWorks.Web.Data;

namespace AdventureWorks.Web.Tests;

/// <summary>C2-3 pure logic: reorder suggestions, vendor choice, PO state machine, create / approve / receive transactions,
/// vendor performance.</summary>
public class ProcurementTests
{
    private static VendorProductInfo V(int vendor, decimal price, int lead, bool preferred = true, bool active = true, int min = 1, int max = 1000, int onOrder = 0) =>
        new(vendor, $"Vendor {vendor}", 1, "Adjustable Race", "AR-5381", lead, price, null, null, min, max, onOrder, "EA", preferred, active);

    [Fact] public void Best_vendor_is_active_then_preferred_then_cheapest_then_fastest()
    {
        Assert.Equal(3, ProcurementRepository.BestVendor([V(1, 10, 5, preferred: false), V(2, 9, 5, active: false), V(3, 12, 9), V(4, 12, 10)])!.VendorId);
        Assert.Equal(5, ProcurementRepository.BestVendor([V(5, 12, 3), V(6, 12, 4)])!.VendorId);
        Assert.Null(ProcurementRepository.BestVendor([V(1, 1, 1, active: false)]));
    }

    [Fact] public void Suggestion_tops_up_to_safety_stock_net_of_on_order_within_vendor_limits()
    {
        var s = ProcurementRepository.Suggest(1, "Adjustable Race", "AR-5381", 600, 750, 1000, [V(1, 10, 5, onOrder: 100)]);
        Assert.Equal(300, s.Need); Assert.Equal(300, s.SuggestedQty); Assert.Equal(100, s.OnOrder); Assert.Null(s.Note);
        var capped = ProcurementRepository.Suggest(1, "x", null, 600, 750, 1000, [V(1, 10, 5, max: 200)]);
        Assert.Equal(200, capped.SuggestedQty); Assert.Contains("maximum", capped.Note);
        var raised = ProcurementRepository.Suggest(1, "x", null, 990, 750, 1000, [V(1, 10, 5, min: 100)]);
        Assert.Equal(100, raised.SuggestedQty); Assert.Contains("minimum", raised.Note);
        var covered = ProcurementRepository.Suggest(1, "x", null, 600, 750, 1000, [V(1, 10, 5, onOrder: 500)]);
        Assert.Equal(0, covered.SuggestedQty); Assert.Contains("on order", covered.Note);
        var made = ProcurementRepository.Suggest(1, "x", null, 0, 750, 1000, []);
        Assert.Null(made.Vendor); Assert.Contains("manufactured", made.Note);
    }

    [Theory]
    [InlineData("approve", 1, true)] [InlineData("reject", 1, true)] [InlineData("receive", 2, true)]
    [InlineData("approve", 2, false)] [InlineData("receive", 1, false)] [InlineData("receive", 4, false)] [InlineData("reject", 3, false)]
    public void Po_transitions_are_enforced(string action, int from, bool ok) => Assert.Equal(ok, PoStatus.CanApply(action, from));

    [Fact] public void Status_text_matches_ufnGetPurchaseOrderStatusText() =>
        Assert.Equal(new[] { "Pending", "Approved", "Rejected", "Complete" }, Enumerable.Range(1, 4).Select(PoStatus.Text));

    [Fact] public void Historical_pos_are_read_only_and_numbered_apart()
    {
        Assert.True(new PurchaseOrder { Id = 4012, Status = 1 }.ReadOnly);
        Assert.Empty(new PurchaseOrder { Id = 4012, Status = 1 }.Actions);
        Assert.Equal(new[] { "approve", "reject" }, new PurchaseOrder { Id = 100_001, Status = 1 }.Actions);
        Assert.Equal("PO-DDB-100001", Keys.PoNumber(100_001)); Assert.Equal("PO004012", Keys.PoNumber(4012));
    }

    private static readonly DateTime Now = new(2026, 10, 12, 18, 0, 0);
    private static readonly VendorSummary Vendor = new(1492, "Australia Bike Retailer", "AUSTRALI0001", 1, true, true);
    private static readonly StaffUser Buyer = new("mikael0@adventure-works.com", "Mikael Sandberg", 251);

    [Fact] public void Create_is_one_transaction_with_lines_marker_on_order_and_feed()
    {
        var t = new DynamoTables(new DynamoOptions());
        var plan = ProcurementRepository.CreatePlan(t, 100_001, 100_010, Vendor,
            [(V(1492, 45.26m, 17) with { ProductId = 422, ProductName = "Thin-Jam Lock Nut 9" }, 3), (V(1492, 43.26m, 17) with { ProductId = 423 }, 2)],
            new ShipMethodInfo(3, "OVERSEAS - DELUXE", 29.95m, 2.99m), Buyer, Now);
        Assert.Equal(1 + 2 * 2 + 3, plan.Count);
        var h = plan[0].Action.Put.Item;
        Assert.Equal("PO#100001", h["PK"].S); Assert.Equal("1", h["status"].N); Assert.Equal("~app", h["src_lsn"].S);
        Assert.Equal("VENDOR#001492", h["GSI1PK"].S); Assert.Equal("EMPLOYEE#000251", h["GSI2PK"].S); Assert.Equal("PO#2026-10-12T18:00:00#100001", h["GSI2SK"].S);
        var sub = 45.26m * 3 + 43.26m * 2;
        Assert.Equal(sub, decimal.Parse(h["sub_total"].N)); Assert.Equal(Pricing.Money(sub * 0.08m), decimal.Parse(h["tax_amt"].N));
        var line = plan[1].Action.Put.Item;
        Assert.Equal("LINE#100010", line["SK"].S); Assert.Equal("2026-10-29T00:00:00", line["due_date"].S);   // + average lead time (17 days)
        Assert.Contains("on_order_qty", plan[2].Action.Update.UpdateExpression);
        Assert.Equal("POSTATUS#1", plan[^3].Action.Put.Item["PK"].S);
        Assert.Equal("aw-sales", plan[^1].Table);
        Assert.All(plan.Where(p => p.Action.Put?.Item.ContainsKey("type") == true && p.Table == DynamoTables.Purchasing), p => Assert.Equal("~app", p.Action.Put.Item["src_lsn"].S));
    }

    private static PurchaseOrder Po(int status, params (int detail, int product, int qty, decimal received)[] lines)
    {
        var o = new PurchaseOrder { Id = 100_001, Number = "PO-DDB-100001", VendorId = 1492, VendorName = "Australia Bike Retailer", Status = status, Version = 3,
            OrderDate = new DateTime(2026, 10, 1, 9, 0, 0), TotalDue = 100 };
        foreach (var l in lines) o.Lines.Add(new PoLine(l.detail, l.product, $"P{l.product}", l.qty, 10m, 10m * l.qty, l.received, 0, l.received, new DateTime(2026, 10, 18)));
        return o;
    }

    [Fact] public void Approve_moves_the_open_marker_and_reject_releases_on_order()
    {
        var t = new DynamoTables(new DynamoOptions());
        var o = Po(1, (100_010, 422, 3, 0), (100_011, 423, 2, 0));
        var ap = ProcurementRepository.TransitionPlan(t, o, "approve", "sheela0@adventure-works.com", null, Now);
        Assert.Equal("ver = :v AND #s = :from", ap[0].Action.Update.ConditionExpression);
        Assert.Equal("POSTATUS#1", ap[1].Action.Delete.Key["PK"].S); Assert.Equal("2026-10-01T09:00:00#100001", ap[1].Action.Delete.Key["SK"].S);
        Assert.Equal("POSTATUS#2", ap[2].Action.Put.Item["PK"].S);
        var rj = ProcurementRepository.TransitionPlan(t, o, "reject", "sheela0@adventure-works.com", "price too high", Now);
        Assert.Equal(2, rj.Count(a => a.Action.Update?.UpdateExpression.Contains("on_order_qty") == true));
        Assert.DoesNotContain(rj, a => a.Action.Put?.Item["PK"].S.StartsWith("POSTATUS#") == true);
        Assert.Throws<ConflictException>(() => ProcurementRepository.TransitionPlan(t, Po(2), "approve", "x", null, Now));
    }

    [Fact] public void Receipt_validation()
    {
        var o = Po(2, (100_010, 422, 10, 4));
        Assert.Throws<ArgumentException>(() => ProcurementRepository.Validate(o, [new(100_010, 7, 0, null)]));   // only 6 open
        Assert.Throws<ArgumentException>(() => ProcurementRepository.Validate(o, [new(100_010, 2, 3, null)]));   // rejected > received
        Assert.Throws<ArgumentException>(() => ProcurementRepository.Validate(o, [new(999, 1, 0, null)]));
        Assert.Throws<ArgumentException>(() => ProcurementRepository.Validate(o, [new(100_010, 1, 0, 99)]));     // unknown location
        Assert.Throws<ArgumentException>(() => ProcurementRepository.Validate(o, []));
        ProcurementRepository.Validate(o, [new(100_010, 6, 1, 6)]);
    }

    private static FulfilmentRepository.Stock S(int pid, decimal total, int rop) => new(pid, [(6, "Miscellaneous Storage", total)], total, rop, true);

    [Fact] public void Partial_receipt_stocks_accepted_units_and_keeps_the_po_open()
    {
        var t = new DynamoTables(new DynamoOptions());
        var o = Po(2, (100_010, 422, 10, 0), (100_011, 423, 5, 0));
        var plan = ProcurementRepository.ReceivePlan(t, o, [new(o.Lines[0], 6, 1, 6, "Miscellaneous Storage", S(422, 100, 300))], "mikael0@x", Now, 10_000_100);
        Assert.Equal(1 + 6 + 2, plan.Count);   // header, line, on-order, INV, total, TXN, catalog, event, feed
        Assert.Equal("2", plan[0].Action.Update.ExpressionAttributeValues[":to"].N);                       // still Approved
        Assert.Equal("2026-10-12T18:00:00", plan[0].Action.Update.ExpressionAttributeValues[":x_ship_date"].S);
        var line = plan[1].Action.Update;
        Assert.Equal("6", line.ExpressionAttributeValues[":rcv"].N); Assert.Equal("1", line.ExpressionAttributeValues[":rej"].N); Assert.Equal("5", line.ExpressionAttributeValues[":stk"].N);
        Assert.Equal("received_qty = :old", line.ConditionExpression);
        var inv = plan.Single(p => p.Action.Update?.Key["SK"].S == "INV#006").Action.Update;
        Assert.Equal("5", inv.ExpressionAttributeValues[":q"].N);
        var total = plan.Single(p => p.Action.Update?.Key["SK"].S == "PRODUCT" && p.Table == DynamoTables.Inventory).Action.Update;
        Assert.Contains("GSI1PK = :r", total.UpdateExpression);                                             // 105 < 300: still below reorder point
        var txn = plan.Single(p => p.Action.Put?.Item["type"].S == "InventoryTransaction").Action.Put.Item;
        Assert.Equal("P", txn["transaction_type"].S); Assert.Equal("5", txn["quantity"].N); Assert.Equal("100001", txn["reference_order_id"].N);
        Assert.Equal(DynamoTables.Purchasing, plan[0].Table);                                               // purchasing first (local grouping)
    }

    [Fact] public void Final_receipt_completes_the_po_removes_the_marker_and_clears_reorder()
    {
        var t = new DynamoTables(new DynamoOptions());
        var o = Po(2, (100_010, 422, 10, 6));
        o.ShipDate = new DateTime(2026, 10, 5);
        var plan = ProcurementRepository.ReceivePlan(t, o, [new(o.Lines[0], 4, 0, 6, "Miscellaneous Storage", S(422, 296, 300))], "x", Now, 1);
        Assert.Equal("4", plan[0].Action.Update.ExpressionAttributeValues[":to"].N);
        Assert.False(plan[0].Action.Update.ExpressionAttributeValues.ContainsKey(":x_ship_date"));
        Assert.Equal("POSTATUS#2", plan[1].Action.Delete.Key["PK"].S);
        Assert.Contains(plan, p => p.Action.Update?.UpdateExpression.EndsWith("REMOVE GSI1PK, GSI1SK ADD ver :one") == true);   // 296 + 4 = 300: back at the reorder point
        Assert.True(plan.Count <= 100);
    }

    [Fact] public void Fully_rejected_line_writes_no_stock_movement()
    {
        var t = new DynamoTables(new DynamoOptions());
        var o = Po(2, (100_010, 422, 10, 0));
        var plan = ProcurementRepository.ReceivePlan(t, o, [new(o.Lines[0], 3, 3, 6, "Miscellaneous Storage", S(422, 100, 300))], "x", Now, 1);
        Assert.DoesNotContain(plan, p => p.Table == DynamoTables.Inventory || p.Table == DynamoTables.Catalog);
    }

    [Fact] public void Largest_receipt_fits_one_transaction()
    {
        var t = new DynamoTables(new DynamoOptions());
        var lines = Enumerable.Range(0, ProcurementRepository.MaxLines).Select(i => (100_010 + i, 400 + i, 10, 0m)).ToArray();
        var o = Po(2, lines);
        var receipt = o.Lines.Select(l => new ProcurementRepository.ReceiptLine(l, 10, 1, 6, "M", S(l.ProductId, 0, 10))).ToList();
        Assert.True(ProcurementRepository.ReceivePlan(t, o, receipt, "x", Now, 1).Count <= 100);
    }

    [Fact] public void Vendor_performance_definitions()
    {
        var a = Po(4, (1, 1, 10, 10)); a.ShipDate = new DateTime(2026, 10, 10);          // on time (due 18th), lead 8.6 d
        a.Lines[0] = a.Lines[0] with { RejectedQty = 1, StockedQty = 9 };
        var b = Po(2, (2, 2, 10, 5)); b.ShipDate = new DateTime(2026, 10, 20);           // late
        var c = Po(1, (3, 3, 10, 0));                                                     // pending: no spend, not shipped
        var p = ProcurementRepository.Performance([a, b, c]);
        Assert.Equal(3, p.Orders); Assert.Equal(30, p.Ordered); Assert.Equal(15, p.Received); Assert.Equal(1, p.Rejected);
        Assert.Equal(200, p.Spend); Assert.Equal(Math.Round(1 / 15.0, 4), p.RejectRate); Assert.Equal(0.5, p.FillRate); Assert.Equal(0.5, p.OnTimeRate);
    }
}
