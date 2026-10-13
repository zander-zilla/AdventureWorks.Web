using System.Globalization;
using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;

namespace AdventureWorks.Web.Data;

// ------------------------------------------------------------------ C2-3 procurement models (also the /api/v2 shapes)

public sealed record VendorSummary(int Id, string Name, string? AccountNumber, int CreditRating, bool Preferred, bool Active);
public sealed record VendorProductInfo(int VendorId, string VendorName, int ProductId, string ProductName, string? ProductNumber, int AverageLeadTime,
    decimal StandardPrice, decimal? LastReceiptCost, DateTime? LastReceiptDate, int MinOrderQty, int MaxOrderQty, int OnOrderQty, string? UnitMeasureCode,
    bool Preferred = false, bool Active = true);
public sealed record VendorAddressInfo(string? Type, string? Line1, string? City, string? State, string? PostalCode, string? Country);
public sealed record VendorContactInfo(string? Name, string? Type);
public sealed record VendorPerformance(int Orders, int Lines, decimal Ordered, decimal Received, decimal Rejected, decimal Spend,
    double? RejectRate, double? FillRate, double? OnTimeRate, double? AvgLeadDays);
public sealed record VendorDetail(VendorSummary Vendor, List<VendorAddressInfo> Addresses, List<VendorContactInfo> Contacts, List<VendorProductInfo> Products,
    VendorPerformance Performance, List<PurchaseOrderSummary> Orders);
public sealed record PurchaseOrderSummary(int Id, string Number, int VendorId, string? VendorName, int Status, string StatusText, DateTime OrderDate,
    decimal TotalDue, int? EmployeeId, string? EmployeeName, string Source);
public sealed record PoPage(List<PurchaseOrderSummary> Items, string? Next);
public sealed record PoLine(int DetailId, int ProductId, string? ProductName, int OrderQty, decimal UnitPrice, decimal LineTotal,
    decimal ReceivedQty, decimal RejectedQty, decimal StockedQty, DateTime? DueDate);
public sealed record PoEvent(DateTime At, string Action, int? FromStatus, int ToStatus, string Actor, string? Note);
public sealed record ReorderSuggestion(int ProductId, string Name, string? ProductNumber, decimal StockQty, int ReorderPoint, int SafetyStockLevel,
    int OnOrder, int Need, int SuggestedQty, string? Note, VendorProductInfo? Vendor, List<VendorProductInfo> Vendors);
public sealed record PoLineRequest(int ProductId, int Quantity);
public sealed record CreatePoRequest(int VendorId, int? ShipMethodId, List<PoLineRequest> Lines);
public sealed record ReceiveLineRequest(int DetailId, int ReceivedQty, int RejectedQty, int? LocationId);
public sealed record ReceiveRequest(long Version, List<ReceiveLineRequest> Lines);
public sealed record PoTransitionRequest(long Version, string? Note);
public sealed record PoResult(PurchaseOrder Order, string Outcome);
public sealed record StaffUser(string Email, string Name, int? EmployeeId);

public sealed class PurchaseOrder
{
    public int Id { get; set; }
    public string Number { get; set; } = "";
    public int VendorId { get; set; }
    public string? VendorName { get; set; }
    public int? EmployeeId { get; set; }
    public string? EmployeeName { get; set; }
    public int Status { get; set; }
    public string StatusText => PoStatus.Text(Status);
    public int RevisionNumber { get; set; }
    public long Version { get; set; }
    public DateTime OrderDate { get; set; }
    public DateTime? ShipDate { get; set; }
    public int? ShipMethodId { get; set; }
    public string? ShipMethodName { get; set; }
    public decimal SubTotal { get; set; }
    public decimal TaxAmt { get; set; }
    public decimal Freight { get; set; }
    public decimal TotalDue { get; set; }
    public string Source { get; set; } = "sql";
    /// <summary>Historical (SQL-era) POs are read-only: their statuses and receipt quantities are inconsistent (PR #15).</summary>
    public bool ReadOnly => Id < Keys.NativePoIdStart;
    public List<PoLine> Lines { get; } = new();
    public List<PoEvent> Events { get; } = new();
    public string[] Actions => ReadOnly ? [] : PoStatus.AllowedActions(Status);
}

/// <summary>Purchasing.PurchaseOrderHeader.Status (ufnGetPurchaseOrderStatusText) and the C2-3 transitions.</summary>
public static class PoStatus
{
    public const int Pending = 1, Approved = 2, Rejected = 3, Complete = 4;
    public static string Text(int s) => s switch { 1 => "Pending", 2 => "Approved", 3 => "Rejected", 4 => "Complete", _ => "** Invalid **" };
    /// <summary>Open = kept in the derived POSTATUS#&lt;s&gt; partitions (PUR-07).</summary>
    public static bool IsOpen(int s) => s is Pending or Approved;
    public static readonly IReadOnlyDictionary<string, (int[] From, string Role)> Actions = new Dictionary<string, (int[], string)>
    {
        ["approve"] = (new[] { Pending }, "PurchasingManager"),
        ["reject"] = (new[] { Pending }, "PurchasingManager"),
        ["receive"] = (new[] { Approved }, "Buyer"),
    };
    public static bool CanApply(string action, int status) => Actions.TryGetValue(action, out var a) && a.From.Contains(status);
    public static string[] AllowedActions(int status) => Actions.Where(a => a.Value.From.Contains(status)).Select(a => a.Key).ToArray();
}

/// <summary>Production.Location (14 rows, static reference; shown in the receive form).</summary>
public static class Locations
{
    public static readonly IReadOnlyDictionary<int, string> All = new Dictionary<int, string>
    {
        [1] = "Tool Crib", [2] = "Sheet Metal Racks", [3] = "Paint Shop", [4] = "Paint Storage", [5] = "Metal Storage", [6] = "Miscellaneous Storage",
        [7] = "Finished Goods Storage", [10] = "Frame Forming", [20] = "Frame Welding", [30] = "Debur and Polish", [40] = "Paint",
        [45] = "Specialized Paint", [50] = "Subassembly", [60] = "Final Assembly",
    };
    public const int Default = 6;
}

/// <summary>
/// C2-3 procurement over aw-purchasing (PUR-01..07, all designed and loaded in Chapter 1) and aw-inventory (INV-01/02/03).
/// Create = one transaction: PO header + lines + POSTATUS#1 marker + on-order quantity per vendor product + change feed.
/// Approve / reject = header (ver + status condition) + marker move + event (+ on-order release on reject).
/// Receive = one transaction: per line received/rejected/stocked quantities, INV#loc increment, InventoryProduct stock total
/// (REORDER marker maintained), catalog stock copy, TransactionHistory type P (INV-03), vendor product last receipt + on order;
/// header revision (Complete when every line is fully received, marker removed). Locally the actions are grouped per DynamoDB
/// Local endpoint (C2-2 decision 4); on AWS each is one TransactWriteItems.
/// </summary>
public sealed class ProcurementRepository(DynamoTables t, TimeProvider clock, FulfilmentRepository fulfilment)
{
    /// <summary>Receive: 6 actions per line + header + 2 marker actions + event + feed &lt;= 100.</summary>
    public const int MaxLines = 15;
    public const decimal TaxRate = 0.08m, FreightRate = 0.025m;   // the SubTotal ratios of the SQL-era POs (checked by the warehouse test)

    private IAmazonDynamoDB Pur => t.For(DynamoTables.Purchasing);
    private string PurT => t.Name(DynamoTables.Purchasing);
    private IAmazonDynamoDB Inv => t.For(DynamoTables.Inventory);
    private string InvT => t.Name(DynamoTables.Inventory);

    private DateTime Now() { var n = clock.GetUtcNow().UtcDateTime; return n.AddTicks(-(n.Ticks % TimeSpan.TicksPerSecond)); }

    // ---------------------------------------------------------------- mapping

    public static VendorSummary ToVendor(Dictionary<string, AttributeValue> i) => new(i.Int("business_entity_id") ?? 0, i.Str("name") ?? "", i.Str("account_number"),
        i.Int("credit_rating") ?? 0, i.Bool("preferred_vendor_status") ?? false, i.Bool("active_flag") ?? true);

    public static VendorProductInfo ToVendorProduct(Dictionary<string, AttributeValue> i, VendorSummary? v = null) => new(
        i.Int("business_entity_id") ?? 0, i.Str("vendor_name") ?? v?.Name ?? "", i.Int("product_id") ?? 0, i.Str("product_name") ?? "", i.Str("product_number"),
        i.Int("average_lead_time") ?? 0, i.Dec("standard_price") ?? 0, i.Dec("last_receipt_cost"), i.Date("last_receipt_date"),
        i.Int("min_order_qty") ?? 1, i.Int("max_order_qty") ?? int.MaxValue, i.Int("on_order_qty") ?? 0, i.Str("unit_measure_code"),
        v?.Preferred ?? false, v?.Active ?? true);

    public static PurchaseOrderSummary ToSummary(Dictionary<string, AttributeValue> i)
    {
        var id = i.Int("purchase_order_id") ?? 0;
        return new(id, Keys.PoNumber(id), i.Int("vendor_id") ?? 0, i.Str("vendor_name"), i.Int("status") ?? 0, PoStatus.Text(i.Int("status") ?? 0),
            i.Date("order_date") ?? DateTime.MinValue, i.Dec("total_due") ?? 0, i.Int("employee_id"), i.Str("employee_name"),
            id >= Keys.NativePoIdStart ? "ddb" : "sql");
    }

    public static PurchaseOrder ToOrder(List<Dictionary<string, AttributeValue>> items)
    {
        var h = items.FirstOrDefault(i => i.Str("SK") == "PO") ?? throw new KeyNotFoundException();
        var o = new PurchaseOrder
        {
            Id = h.Int("purchase_order_id") ?? 0, VendorId = h.Int("vendor_id") ?? 0, VendorName = h.Str("vendor_name"), EmployeeId = h.Int("employee_id"),
            EmployeeName = h.Str("employee_name"), Status = h.Int("status") ?? 0, RevisionNumber = h.Int("revision_number") ?? 0, Version = h.Long("ver") ?? 1,
            OrderDate = h.Date("order_date") ?? DateTime.MinValue, ShipDate = h.Date("ship_date"), ShipMethodId = h.Int("ship_method_id"),
            ShipMethodName = h.Str("ship_method_name"), SubTotal = h.Dec("sub_total") ?? 0, TaxAmt = h.Dec("tax_amt") ?? 0, Freight = h.Dec("freight") ?? 0,
            TotalDue = h.Dec("total_due") ?? 0, Source = h.Str("src") ?? "sql",
        };
        o.Number = Keys.PoNumber(o.Id);
        foreach (var l in items.Where(i => i.Str("type") == "PurchaseOrderLine" && i.IsLive()))
            o.Lines.Add(new PoLine(l.Int("purchase_order_detail_id") ?? 0, l.Int("product_id") ?? 0, l.Str("product_name"), l.Int("order_qty") ?? 0,
                l.Dec("unit_price") ?? 0, l.Dec("line_total") ?? 0, l.Dec("received_qty") ?? 0, l.Dec("rejected_qty") ?? 0, l.Dec("stocked_qty") ?? 0, l.Date("due_date")));
        foreach (var e in items.Where(i => i.Str("type") == "PurchaseOrderEvent").OrderBy(i => i.Str("SK")))
            o.Events.Add(new PoEvent(e.Date("at") ?? DateTime.MinValue, e.Str("action") ?? "", e.Int("from_status"), e.Int("to_status") ?? 0, e.Str("actor") ?? "", e.Str("note")));
        return o;
    }

    // ---------------------------------------------------------------- reads

    /// <summary>PUR-01 (vendor, addresses, contacts) + PUR-03 (products) in one Query of the vendor partition.</summary>
    public async Task<(VendorSummary Vendor, List<VendorAddressInfo> Addresses, List<VendorContactInfo> Contacts, List<VendorProductInfo> Products)?> GetVendorAsync(int id)
    {
        var items = await Pur.QueryAll(new QueryRequest { TableName = PurT, KeyConditionExpression = "PK = :pk",
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Vendor(id)) } });
        var head = items.FirstOrDefault(i => i.Str("SK") == "VENDOR");
        if (head is null) return null;
        var v = ToVendor(head);
        return (v,
            items.Where(i => i.Str("type") == "VendorAddress").Select(a => new VendorAddressInfo(a.Str("address_type"), a.Str("address_line1"), a.Str("city"),
                a.Str("state_province_code"), a.Str("postal_code"), a.Str("country_region_code"))).ToList(),
            items.Where(i => i.Str("type") == "VendorContact").Select(c => new VendorContactInfo(c.Str("contact_name"), c.Str("contact_type"))).ToList(),
            items.Where(i => i.Str("type") == "VendorProduct" && i.IsLive()).Select(p => ToVendorProduct(p, v)).OrderBy(p => p.ProductName).ToList());
    }

    /// <summary>All vendors (104 items). There is no "list vendors" access pattern in the Chapter 1 design; a Scan with a
    /// FilterExpression on SK = VENDOR reads the whole (13,918-item) table, so the result is cached for 10 minutes.</summary>
    private (DateTimeOffset At, List<VendorSummary> Vendors)? _vendors;
    public async Task<List<VendorSummary>> ListVendorsAsync()
    {
        if (_vendors is { } c && clock.GetUtcNow() - c.At < TimeSpan.FromMinutes(10)) return c.Vendors;
        var all = new List<VendorSummary>(); Dictionary<string, AttributeValue>? start = null;
        do
        {
            var r = await Pur.ScanAsync(new ScanRequest { TableName = PurT, ExclusiveStartKey = start, FilterExpression = "SK = :v",
                ExpressionAttributeValues = new() { [":v"] = Av.S("VENDOR") } });
            all.AddRange((r.Items ?? new()).Where(i => i.IsLive()).Select(ToVendor));
            start = r.LastEvaluatedKey is { Count: > 0 } k ? k : null;
        } while (start is not null);
        all.Sort((a, b) => string.Compare(a.Name, b.Name, StringComparison.OrdinalIgnoreCase));
        _vendors = (clock.GetUtcNow(), all);
        return all;
    }

    /// <summary>PUR-02: who supplies this product (vendor flags from the vendor items, BatchGet).</summary>
    public async Task<List<VendorProductInfo>> SuppliersAsync(int productId)
    {
        var items = await Pur.QueryAll(new QueryRequest { TableName = PurT, IndexName = "GSI1", KeyConditionExpression = "GSI1PK = :p AND begins_with(GSI1SK, :v)",
            ExpressionAttributeValues = new() { [":p"] = Av.S(Keys.Product(productId)), [":v"] = Av.S("VENDOR#") } });
        var vendors = await VendorsByIdAsync(items.Select(i => i.Int("business_entity_id") ?? 0).Distinct());
        return items.Where(i => i.IsLive()).Select(i => ToVendorProduct(i, vendors.GetValueOrDefault(i.Int("business_entity_id") ?? 0))).ToList();
    }

    private async Task<Dictionary<int, VendorSummary>> VendorsByIdAsync(IEnumerable<int> ids)
    {
        var d = new Dictionary<int, VendorSummary>();
        foreach (var chunk in ids.Where(i => i > 0).Chunk(100))
        {
            var req = new Dictionary<string, KeysAndAttributes> { [PurT] = new() { Keys = chunk.Select(v => new Dictionary<string, AttributeValue> { ["PK"] = Av.S(Keys.Vendor(v)), ["SK"] = Av.S("VENDOR") }).ToList() } };
            while (req.Count > 0)
            {
                var r = await Pur.BatchGetItemAsync(new BatchGetItemRequest { RequestItems = req });
                foreach (var i in r.Responses?.GetValueOrDefault(PurT) ?? new()) { var v = ToVendor(i); d[v.Id] = v; }
                req = r.UnprocessedKeys is { Count: > 0 } u ? u : new();
            }
        }
        return d;
    }

    /// <summary>PUR-04 read: the PO partition (header, lines, events), strongly consistent.</summary>
    public async Task<PurchaseOrder?> GetOrderAsync(int id)
    {
        var items = await Pur.QueryAll(new QueryRequest { TableName = PurT, ConsistentRead = true, KeyConditionExpression = "PK = :pk",
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Po(id)) } });
        return items.Any(i => i.Str("SK") == "PO" && i.IsLive()) ? ToOrder(items) : null;
    }

    /// <summary>PUR-07: open POs (derived POSTATUS#1 / POSTATUS#2 partitions), newest first.</summary>
    public async Task<PoPage> OpenAsync(int status, string? token, int pageSize = 50)
    {
        if (!PoStatus.IsOpen(status)) throw new ArgumentException("Only Pending (1) and Approved (2) POs are indexed (PUR-07).");
        var r = await Pur.QueryAsync(new QueryRequest { TableName = PurT, KeyConditionExpression = "PK = :pk", ScanIndexForward = false, Limit = pageSize,
            ExclusiveStartKey = Paging.Decode(token), ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.PoStatus(status)) } });
        return new PoPage((r.Items ?? new()).Where(i => i.IsLive()).Select(ToSummary).ToList(), Paging.Encode(r.LastEvaluatedKey));
    }

    public async Task<Dictionary<int, int>> OpenCountsAsync()
    {
        var d = new Dictionary<int, int>();
        foreach (var s in new[] { PoStatus.Pending, PoStatus.Approved })
            d[s] = (await Pur.QueryAll(new QueryRequest { TableName = PurT, KeyConditionExpression = "PK = :pk", ProjectionExpression = "PK",
                ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.PoStatus(s)) } })).Count;
        return d;
    }

    /// <summary>PUR-05: a vendor's POs newest first, optional status filter.</summary>
    public async Task<List<PurchaseOrderSummary>> ForVendorAsync(int vendorId, int? status = null, int max = 200)
    {
        var q = new QueryRequest { TableName = PurT, IndexName = "GSI1", ScanIndexForward = false, KeyConditionExpression = "GSI1PK = :v AND begins_with(GSI1SK, :po)",
            ExpressionAttributeValues = new() { [":v"] = Av.S(Keys.Vendor(vendorId)), [":po"] = Av.S("PO#") } };
        if (status is { } s) { q.FilterExpression = "#s = :s"; q.ExpressionAttributeNames = new() { ["#s"] = "status" }; q.ExpressionAttributeValues[":s"] = Av.N(s); }
        return (await Pur.QueryAll(q, max)).Where(i => i.IsLive()).Take(max).Select(ToSummary).ToList();
    }

    /// <summary>PUR-06: POs raised by an employee, newest first.</summary>
    public async Task<PoPage> ForEmployeeAsync(int employeeId, string? token, int pageSize = 50)
    {
        var r = await Pur.QueryAsync(new QueryRequest { TableName = PurT, IndexName = "GSI2", ScanIndexForward = false, Limit = pageSize, ExclusiveStartKey = Paging.Decode(token),
            KeyConditionExpression = "GSI2PK = :e AND begins_with(GSI2SK, :po)", ExpressionAttributeValues = new() { [":e"] = Av.S(Keys.Employee(employeeId)), [":po"] = Av.S("PO#") } });
        return new PoPage((r.Items ?? new()).Where(i => i.IsLive()).Select(ToSummary).ToList(), Paging.Encode(r.LastEvaluatedKey));
    }

    /// <summary>Vendor performance over the vendor's POs (PUR-05 + one PO-partition Query each). Same definitions as the
    /// Redshift view dw.v_vendor_performance (warehouse/sql/star/04_views.sql).</summary>
    public async Task<VendorPerformance> PerformanceAsync(int vendorId, List<PurchaseOrderSummary> orders)
    {
        var pos = new List<PurchaseOrder>();
        foreach (var chunk in orders.Chunk(8))
            pos.AddRange((await Task.WhenAll(chunk.Select(o => GetOrderAsync(o.Id)))).Where(p => p is not null)!);
        return Performance(pos);
    }

    /// <summary>Pure: reject rate = rejected / received; fill rate = received / ordered; on time = lines of shipped POs whose ship
    /// (= first receipt for app POs) date is on or before the line due date; spend = line totals of approved/complete POs.</summary>
    public static VendorPerformance Performance(IReadOnlyList<PurchaseOrder> pos)
    {
        var lines = pos.SelectMany(p => p.Lines.Select(l => (p, l))).ToList();
        decimal ordered = lines.Sum(x => (decimal)x.l.OrderQty), received = lines.Sum(x => x.l.ReceivedQty), rejected = lines.Sum(x => x.l.RejectedQty);
        var shipped = lines.Where(x => x.p.ShipDate is not null && x.l.DueDate is not null).ToList();
        var lead = pos.Where(p => p.ShipDate is not null).Select(p => (p.ShipDate!.Value - p.OrderDate).TotalDays).ToList();
        return new VendorPerformance(pos.Count, lines.Count, ordered, received, rejected,
            lines.Where(x => x.p.Status is PoStatus.Approved or PoStatus.Complete).Sum(x => x.l.LineTotal),
            received == 0 ? null : Math.Round((double)(rejected / received), 4), ordered == 0 ? null : Math.Round((double)(received / ordered), 4),
            shipped.Count == 0 ? null : Math.Round(shipped.Count(x => x.p.ShipDate!.Value.Date <= x.l.DueDate!.Value.Date) / (double)shipped.Count, 4),
            lead.Count == 0 ? null : Math.Round(lead.Average(), 1));
    }

    // ---------------------------------------------------------------- INV-02 reorder suggestions

    /// <summary>INV-02 (sparse REORDER index: stock below reorder point) + PUR-02 per product. Suggested quantity tops stock up to
    /// the safety stock level net of quantities already on order, within the vendor's min/max order quantity.</summary>
    public async Task<List<ReorderSuggestion>> SuggestionsAsync()
    {
        var low = await Inv.QueryAll(new QueryRequest { TableName = InvT, IndexName = "GSI1", KeyConditionExpression = "GSI1PK = :r",
            ExpressionAttributeValues = new() { [":r"] = Av.S("REORDER") } });
        var products = low.Where(i => i.IsLive()).ToList();
        var supplierLists = new List<List<VendorProductInfo>>();
        foreach (var chunk in products.Chunk(10))
            supplierLists.AddRange(await Task.WhenAll(chunk.Select(p => SuppliersAsync(p.Int("product_id") ?? 0))));
        return products.Select((p, i) => Suggest(p.Int("product_id") ?? 0, p.Str("name") ?? "", p.Str("product_number"), p.Dec("stock_qty") ?? 0,
                p.Int("reorder_point") ?? 0, p.Int("safety_stock_level") ?? 0, supplierLists[i]))
            .OrderBy(s => s.Vendor is null).ThenBy(s => s.Vendor?.VendorName).ThenBy(s => s.Name).ToList();
    }

    /// <summary>Pure: best vendor = active, then preferred, then lowest standard price, then shortest lead time.</summary>
    public static VendorProductInfo? BestVendor(IEnumerable<VendorProductInfo> vendors) => vendors.Where(v => v.Active)
        .OrderByDescending(v => v.Preferred).ThenBy(v => v.StandardPrice).ThenBy(v => v.AverageLeadTime).ThenBy(v => v.VendorId).FirstOrDefault();

    public static ReorderSuggestion Suggest(int productId, string name, string? number, decimal stock, int reorderPoint, int safetyStock, List<VendorProductInfo> vendors)
    {
        var onOrder = vendors.Sum(v => Math.Max(0, v.OnOrderQty));
        var target = Math.Max(safetyStock, reorderPoint);
        var need = (int)Math.Max(0, Math.Ceiling(target - stock - onOrder));
        var best = BestVendor(vendors);
        string? note = null; var qty = 0;
        if (best is null) note = vendors.Count == 0 ? "No vendor: manufactured in house (production floor, C2-4)" : "No active vendor";
        else if (need == 0) note = "Covered by quantities already on order";
        else
        {
            qty = Math.Clamp(need, Math.Max(1, best.MinOrderQty), Math.Max(Math.Max(1, best.MinOrderQty), best.MaxOrderQty));
            if (qty < need) note = $"Capped at the vendor's maximum order quantity ({best.MaxOrderQty})";
            else if (qty > need) note = $"Raised to the vendor's minimum order quantity ({best.MinOrderQty})";
        }
        return new ReorderSuggestion(productId, name, number, stock, reorderPoint, safetyStock, onOrder, need, qty, note, best, vendors);
    }

    // ---------------------------------------------------------------- PUR-04 create

    private async Task<(int PoId, int FirstLineId)> NextIdsAsync(int lines)
    {
        var r = await Pur.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = PurT, Key = new() { ["PK"] = Av.S("COUNTER"), ["SK"] = Av.S("PO") }, ReturnValues = ReturnValue.UPDATED_NEW,
            UpdateExpression = "ADD next_po :one, next_line :n SET #t = if_not_exists(#t, :t), src = :src", ExpressionAttributeNames = new() { ["#t"] = "type" },
            ExpressionAttributeValues = new() { [":one"] = Av.N(1), [":n"] = Av.N(lines), [":t"] = Av.S("PoIdCounter"), [":src"] = Av.S("ddb") },
        });
        return (Keys.NativePoIdStart + int.Parse(r.Attributes["next_po"].N) - 1, Keys.NativePoIdStart + int.Parse(r.Attributes["next_line"].N) - lines);
    }

    public async Task<PurchaseOrder> CreateAsync(CreatePoRequest req, StaffUser buyer, List<ShipMethodInfo> methods, string? token = null)
    {
        if (req.Lines is not { Count: > 0 }) throw new ArgumentException("A purchase order needs at least one line.");
        if (req.Lines.Count > MaxLines) throw new ArgumentException($"At most {MaxLines} lines per purchase order (one receipt transaction).");
        if (req.Lines.GroupBy(l => l.ProductId).Any(g => g.Count() > 1)) throw new ArgumentException("Each product may appear once per purchase order.");
        var v = await GetVendorAsync(req.VendorId) ?? throw new KeyNotFoundException();
        if (!v.Vendor.Active) throw new ArgumentException($"{v.Vendor.Name} is not an active vendor.");
        var offers = new List<(VendorProductInfo Offer, int Qty)>();
        foreach (var l in req.Lines)
        {
            var offer = v.Products.FirstOrDefault(p => p.ProductId == l.ProductId) ?? throw new ArgumentException($"{v.Vendor.Name} does not supply product {l.ProductId} (PUR-03).");
            if (l.Quantity < 1 || l.Quantity > 100_000) throw new ArgumentException($"Quantity for {offer.ProductName} must be 1-100,000.");
            offers.Add((offer, l.Quantity));
        }
        var method = methods.FirstOrDefault(m => m.Id == (req.ShipMethodId ?? 3)) ?? methods.FirstOrDefault() ?? throw new ArgumentException("No ship methods (REF-04).");
        var (poId, firstLine) = await NextIdsAsync(offers.Count);
        var now = Now();
        var actions = CreatePlan(t, poId, firstLine, v.Vendor, offers, method, buyer, now);
        await t.TransactAsync(actions, token);
        return (await GetOrderAsync(poId))!;
    }

    private static Dictionary<string, AttributeValue> AppMeta(Dictionary<string, AttributeValue> i, string srcTable, string srcPk)
    {
        i["src_lsn"] = Av.S(Keys.AppLsn); i["src_table"] = Av.S(srcTable); i["src_pk"] = Av.S(srcPk);
        return i;
    }

    public static Dictionary<string, AttributeValue> Event(int poId, DateTime now, int seq, string action, int? from, int to, string actor, string? note)
    {
        var e = Av.Item(Keys.Po(poId), Keys.OrderEvent(now, seq), "PurchaseOrderEvent");
        e["purchase_order_id"] = Av.N(poId); e["action"] = Av.S(action); e["to_status"] = Av.N(to); e["actor"] = Av.S(actor);
        e["at"] = Av.S(Keys.Iso(now) + "Z"); e["src_lsn"] = Av.S(Keys.AppLsn);
        if (from is { } f) e["from_status"] = Av.N(f);
        e.Set("note", note);
        return e;
    }

    private static Dictionary<string, AttributeValue> Marker(int status, int poId, VendorSummary v, DateTime orderDate, decimal total)
    {
        var m = AppMeta(Av.Item(Keys.PoStatus(status), Keys.PoIndexSk(orderDate, poId), "OpenPurchaseOrder"), "Purchasing.PurchaseOrderHeader", $"PurchaseOrderID={poId}");
        m["derived"] = Av.B(true); m["purchase_order_id"] = Av.N(poId); m["vendor_id"] = Av.N(v.Id); m["vendor_name"] = Av.S(v.Name);
        m["status"] = Av.N(status); m["order_date"] = Av.S(Keys.Iso(orderDate)); m["total_due"] = Av.N(total);
        return m;
    }

    /// <summary>Pure (unit-tested): the create transaction.</summary>
    public static List<(string Table, TransactWriteItem Action)> CreatePlan(DynamoTables t, int poId, int firstLineId, VendorSummary v,
        List<(VendorProductInfo Offer, int Qty)> lines, ShipMethodInfo method, StaffUser buyer, DateTime now)
    {
        string pur = t.Name(DynamoTables.Purchasing), sales = t.Name(DynamoTables.Sales);
        var a = new List<(string, TransactWriteItem)>();
        var writes = new List<string>();
        var sub = lines.Sum(l => Pricing.Money(l.Offer.StandardPrice * l.Qty));
        decimal tax = Pricing.Money(sub * TaxRate), freight = Pricing.Money(sub * FreightRate), total = sub + tax + freight;
        var pk = Keys.Po(poId);
        var h = AppMeta(Av.Item(pk, "PO", "PurchaseOrder"), "Purchasing.PurchaseOrderHeader", $"PurchaseOrderID={poId}");
        h["purchase_order_id"] = Av.N(poId); h["revision_number"] = Av.N(0); h["status"] = Av.N(PoStatus.Pending); h["vendor_id"] = Av.N(v.Id); h["vendor_name"] = Av.S(v.Name);
        if (buyer.EmployeeId is { } e) { h["employee_id"] = Av.N(e); h["GSI2PK"] = Av.S(Keys.Employee(e)); h["GSI2SK"] = Av.S("PO#" + Keys.PoIndexSk(now, poId)); }
        h["employee_name"] = Av.S(buyer.Name); h["created_by"] = Av.S(buyer.Email);
        h["ship_method_id"] = Av.N(method.Id); h["ship_method_name"] = Av.S(method.Name); h["order_date"] = Av.S(Keys.Iso(now)); h["modified_date"] = Av.S(Keys.Iso(now));
        h["sub_total"] = Av.N(sub); h["tax_amt"] = Av.N(tax); h["freight"] = Av.N(freight); h["total_due"] = Av.N(total);
        h["GSI1PK"] = Av.S(Keys.Vendor(v.Id)); h["GSI1SK"] = Av.S("PO#" + Keys.PoIndexSk(now, poId));
        a.Add((DynamoTables.Purchasing, new() { Put = new Put { TableName = pur, Item = h, ConditionExpression = "attribute_not_exists(PK)" } }));
        writes.Add($"aw-purchasing {pk} PO status 1 Pending, total {total:0.00} (PurchaseOrder -> stg.purchase_order)");
        var n = 0;
        foreach (var (offer, qty) in lines)
        {
            var id = firstLineId + n++;
            var l = AppMeta(Av.Item(pk, Keys.PoLine(id), "PurchaseOrderLine"), "Purchasing.PurchaseOrderDetail", $"PurchaseOrderID={poId},PurchaseOrderDetailID={id}");
            l["purchase_order_id"] = Av.N(poId); l["purchase_order_detail_id"] = Av.N(id); l["product_id"] = Av.N(offer.ProductId); l["product_name"] = Av.S(offer.ProductName);
            l["order_qty"] = Av.N(qty); l["unit_price"] = Av.N(offer.StandardPrice); l["line_total"] = Av.N(Pricing.Money(offer.StandardPrice * qty));
            l["received_qty"] = Av.N(0); l["rejected_qty"] = Av.N(0); l["stocked_qty"] = Av.N(0);
            l["due_date"] = Av.S(Keys.Iso(now.Date.AddDays(Math.Max(1, offer.AverageLeadTime)))); l["modified_date"] = Av.S(Keys.Iso(now));
            a.Add((DynamoTables.Purchasing, new() { Put = new Put { TableName = pur, Item = l, ConditionExpression = "attribute_not_exists(PK)" } }));
            a.Add((DynamoTables.Purchasing, new() { Update = OnOrder(pur, v.Id, offer.ProductId, qty, now) }));
            writes.Add($"aw-purchasing {pk} {Keys.PoLine(id)} {offer.ProductName} x{qty} (PurchaseOrderLine -> stg.purchase_order_line)");
            writes.Add($"aw-purchasing {Keys.Vendor(v.Id)} {Keys.Product(offer.ProductId)} on_order_qty +{qty} (VendorProduct -> stg.vendor_product)");
        }
        a.Add((DynamoTables.Purchasing, new() { Put = new Put { TableName = pur, Item = Marker(PoStatus.Pending, poId, v, now, total) } }));
        a.Add((DynamoTables.Purchasing, new() { Put = new Put { TableName = pur, Item = Event(poId, now, 1, "create", null, PoStatus.Pending, buyer.Email, $"{lines.Count} lines via {method.Name}") } }));
        writes.Add($"aw-purchasing {Keys.PoStatus(1)} {Keys.PoIndexSk(now, poId)} (OpenPurchaseOrder, PUR-07)");
        a.Add((DynamoTables.Sales, new() { Put = new Put { TableName = sales, Item = ChangeFeed.Entry(now, "po.create", Keys.PoNumber(poId), buyer.Email, writes) } }));
        return a;
    }

    private static Update OnOrder(string table, int vendorId, int productId, decimal delta, DateTime now, Dictionary<string, AttributeValue>? extra = null)
    {
        var values = new Dictionary<string, AttributeValue> { [":d"] = Av.N(delta), [":z"] = Av.N(0), [":u"] = Av.S(Keys.Iso(now) + "Z"), [":src"] = Av.S("ddb"), [":lsn"] = Av.S(Keys.AppLsn), [":one"] = Av.N(1) };
        var sets = new List<string> { "on_order_qty = if_not_exists(on_order_qty, :z) + :d", "updated_at = :u", "src = :src", "src_lsn = :lsn" };
        foreach (var (k, v) in extra ?? new()) { sets.Add($"{k} = :x_{k}"); values[$":x_{k}"] = v; }
        return new Update { TableName = table, Key = new() { ["PK"] = Av.S(Keys.Vendor(vendorId)), ["SK"] = Av.S(Keys.Product(productId)) },
            UpdateExpression = "SET " + string.Join(", ", sets) + " ADD ver :one", ConditionExpression = "attribute_exists(PK)", ExpressionAttributeValues = values };
    }

    /// <summary>Header update: ver + status checked; revision + 1; optional extra SETs.</summary>
    public static Update HeaderUpdate(string table, PurchaseOrder o, int to, DateTime now, Dictionary<string, AttributeValue>? extraSets = null)
    {
        var values = new Dictionary<string, AttributeValue>
        {
            [":to"] = Av.N(to), [":v"] = Av.N(o.Version), [":from"] = Av.N(o.Status), [":one"] = Av.N(1), [":zero"] = Av.N(0), [":now"] = Av.S(Keys.Iso(now)),
            [":u"] = Av.S(Keys.Iso(now) + "Z"), [":src"] = Av.S("ddb"), [":lsn"] = Av.S(Keys.AppLsn),
        };
        var sets = new List<string> { "#s = :to", "modified_date = :now", "updated_at = :u", "src = :src", "src_lsn = :lsn",
            "revision_number = if_not_exists(revision_number, :zero) + :one", "ver = ver + :one" };
        foreach (var (k, v) in extraSets ?? new()) { sets.Add($"{k} = :x_{k}"); values[$":x_{k}"] = v; }
        return new Update { TableName = table, Key = new() { ["PK"] = Av.S(Keys.Po(o.Id)), ["SK"] = Av.S("PO") },
            UpdateExpression = "SET " + string.Join(", ", sets), ConditionExpression = "ver = :v AND #s = :from",
            ExpressionAttributeNames = new() { ["#s"] = "status" }, ExpressionAttributeValues = values };
    }

    private static VendorSummary VendorOf(PurchaseOrder o) => new(o.VendorId, o.VendorName ?? "", null, 0, false, true);

    // ---------------------------------------------------------------- approve / reject

    public static List<(string Table, TransactWriteItem Action)> TransitionPlan(DynamoTables t, PurchaseOrder o, string action, string actor, string? note, DateTime now)
    {
        if (!PoStatus.CanApply(action, o.Status) || action == "receive") throw new ConflictException($"Cannot {action} {o.Number}: it is {PoStatus.Text(o.Status)}.");
        string pur = t.Name(DynamoTables.Purchasing), sales = t.Name(DynamoTables.Sales);
        var to = action == "approve" ? PoStatus.Approved : PoStatus.Rejected;
        var a = new List<(string, TransactWriteItem)> { (DynamoTables.Purchasing, new() { Update = HeaderUpdate(pur, o, to, now) }) };
        var writes = new List<string> { $"aw-purchasing {Keys.Po(o.Id)} PO status {o.Status}->{to} (PurchaseOrder -> stg.purchase_order)" };
        a.Add((DynamoTables.Purchasing, new() { Delete = new Delete { TableName = pur, Key = new() { ["PK"] = Av.S(Keys.PoStatus(o.Status)), ["SK"] = Av.S(Keys.PoIndexSk(o.OrderDate, o.Id)) } } }));
        if (to == PoStatus.Approved)
        {
            a.Add((DynamoTables.Purchasing, new() { Put = new Put { TableName = pur, Item = Marker(to, o.Id, VendorOf(o), o.OrderDate, o.TotalDue) } }));
            writes.Add($"aw-purchasing POSTATUS#1 -> POSTATUS#2 (OpenPurchaseOrder, PUR-07)");
        }
        else
        {
            foreach (var l in o.Lines)
            {
                a.Add((DynamoTables.Purchasing, new() { Update = OnOrder(pur, o.VendorId, l.ProductId, -l.OrderQty, now) }));
                writes.Add($"aw-purchasing {Keys.Vendor(o.VendorId)} {Keys.Product(l.ProductId)} on_order_qty -{l.OrderQty}");
            }
            writes.Add("aw-purchasing POSTATUS#1 marker deleted (no longer open)");
        }
        a.Add((DynamoTables.Purchasing, new() { Put = new Put { TableName = pur, Item = Event(o.Id, now, o.Events.Count + 1, action, o.Status, to, actor, note) } }));
        a.Add((DynamoTables.Sales, new() { Put = new Put { TableName = sales, Item = ChangeFeed.Entry(now, $"po.{action}", o.Number, actor, writes) } }));
        return a;
    }

    public async Task<PoResult> TransitionAsync(int id, string action, long version, string actor, string? note, string? token = null)
    {
        var o = await GetOrderAsync(id) ?? throw new KeyNotFoundException();
        Check(o, action, version);
        if (note is { Length: > 200 }) throw new ArgumentException("Note: at most 200 characters.");
        try { await t.TransactAsync(TransitionPlan(t, o, action, actor, note, Now()), token); }
        catch (TransactionCanceledException) { throw new ConflictException($"{o.Number} changed meanwhile. Reload and retry."); }
        return new((await GetOrderAsync(id))!, action == "approve" ? "approved" : "rejected");
    }

    private static void Check(PurchaseOrder o, string action, long version)
    {
        if (o.ReadOnly) throw new ConflictException($"{o.Number} is a historical (SQL-era) purchase order and is read-only.");
        if (o.Version != version) throw new ConflictException($"{o.Number} was changed by someone else (version {o.Version}, you had {version}). Reload and retry.");
        if (!PoStatus.CanApply(action, o.Status)) throw new ConflictException($"Cannot {action} {o.Number}: it is {PoStatus.Text(o.Status)}.");
    }

    // ---------------------------------------------------------------- receive (PUR-07 -> INV-01/02/03)

    public sealed record ReceiptLine(PoLine Line, int Received, int Rejected, int LocationId, string LocationName, FulfilmentRepository.Stock Stock);

    /// <summary>Pure validation: received (incl. rejected) per line &lt;= still open quantity; rejected &lt;= received.</summary>
    public static void Validate(PurchaseOrder o, IReadOnlyList<ReceiveLineRequest> lines)
    {
        if (lines.Count == 0 || lines.All(l => l.ReceivedQty == 0)) throw new ArgumentException("Enter a received quantity for at least one line.");
        if (lines.GroupBy(l => l.DetailId).Any(g => g.Count() > 1)) throw new ArgumentException("Each line may appear once per receipt.");
        foreach (var r in lines)
        {
            var l = o.Lines.FirstOrDefault(x => x.DetailId == r.DetailId) ?? throw new ArgumentException($"{o.Number} has no line {r.DetailId}.");
            var open = l.OrderQty - l.ReceivedQty;
            if (r.ReceivedQty < 0 || r.RejectedQty < 0) throw new ArgumentException("Quantities cannot be negative.");
            if (r.ReceivedQty > open) throw new ArgumentException($"{l.ProductName}: received {r.ReceivedQty} is more than the {open} still open.");
            if (r.RejectedQty > r.ReceivedQty) throw new ArgumentException($"{l.ProductName}: rejected {r.RejectedQty} is more than received {r.ReceivedQty}.");
            if (r.LocationId is { } loc && !Locations.All.ContainsKey(loc)) throw new ArgumentException($"Unknown location {loc}.");
        }
    }

    /// <summary>Pure: is the PO complete after this receipt (every line fully received)?</summary>
    public static bool CompletesOrder(PurchaseOrder o, IEnumerable<(int DetailId, int Received)> receipt)
    {
        var d = receipt.ToDictionary(x => x.DetailId, x => x.Received);
        return o.Lines.All(l => l.ReceivedQty + d.GetValueOrDefault(l.DetailId) >= l.OrderQty);
    }

    /// <summary>Pure (unit-tested): the receipt transaction. Group order (matters only for per-table DynamoDB Local):
    /// purchasing (PO version condition) first, then inventory (stock-total condition), catalog copy, sales feed.</summary>
    public static List<(string Table, TransactWriteItem Action)> ReceivePlan(DynamoTables t, PurchaseOrder o, List<ReceiptLine> lines, string actor, DateTime now, long txnStart)
    {
        string pur = t.Name(DynamoTables.Purchasing), inv = t.Name(DynamoTables.Inventory), cat = t.Name(DynamoTables.Catalog), sales = t.Name(DynamoTables.Sales);
        var a = new List<(string, TransactWriteItem)>();
        var writes = new List<string>();
        var complete = CompletesOrder(o, lines.Select(l => (l.Line.DetailId, l.Received)));
        var to = complete ? PoStatus.Complete : PoStatus.Approved;
        var u = Av.S(Keys.Iso(now) + "Z"); var lsn = Av.S(Keys.AppLsn); var src = Av.S("ddb"); var one = Av.N(1);
        var extra = new Dictionary<string, AttributeValue>();
        if (o.ShipDate is null) extra["ship_date"] = Av.S(Keys.Iso(now));   // first receipt = vendor shipment arrived (on-time measure)
        a.Add((DynamoTables.Purchasing, new() { Update = HeaderUpdate(pur, o, to, now, extra) }));
        writes.Add($"aw-purchasing {Keys.Po(o.Id)} PO revision+1{(complete ? ", status 2->4 Complete" : "")} (PurchaseOrder -> stg.purchase_order)");
        if (complete)
        {
            a.Add((DynamoTables.Purchasing, new() { Delete = new Delete { TableName = pur, Key = new() { ["PK"] = Av.S(Keys.PoStatus(PoStatus.Approved)), ["SK"] = Av.S(Keys.PoIndexSk(o.OrderDate, o.Id)) } } }));
            writes.Add("aw-purchasing POSTATUS#2 marker deleted (complete)");
        }
        foreach (var r in lines)
        {
            var stocked = r.Received - r.Rejected;
            a.Add((DynamoTables.Purchasing, new() { Update = new Update { TableName = pur, Key = new() { ["PK"] = Av.S(Keys.Po(o.Id)), ["SK"] = Av.S(Keys.PoLine(r.Line.DetailId)) },
                UpdateExpression = "SET received_qty = :rcv, rejected_qty = :rej, stocked_qty = :stk, modified_date = :now, updated_at = :u, src = :src, src_lsn = :lsn ADD ver :one",
                ConditionExpression = "received_qty = :old",
                ExpressionAttributeValues = new() { [":rcv"] = Av.N(r.Line.ReceivedQty + r.Received), [":rej"] = Av.N(r.Line.RejectedQty + r.Rejected),
                    [":stk"] = Av.N(r.Line.StockedQty + stocked), [":old"] = Av.N(r.Line.ReceivedQty), [":now"] = Av.S(Keys.Iso(now)), [":u"] = u, [":src"] = src, [":lsn"] = lsn, [":one"] = one } } }));
            a.Add((DynamoTables.Purchasing, new() { Update = OnOrder(pur, o.VendorId, r.Line.ProductId, -r.Received, now, new()
                { ["last_receipt_date"] = Av.S(Keys.Iso(now)), ["last_receipt_cost"] = Av.N(r.Line.UnitPrice) }) }));
            writes.Add($"aw-purchasing {Keys.Po(o.Id)} {Keys.PoLine(r.Line.DetailId)} received +{r.Received}, rejected +{r.Rejected} (PurchaseOrderLine -> stg.purchase_order_line)");
        }
        // stock: one INV#loc increment + one stock-total update per product (products are unique per PO)
        long txn = txnStart;
        foreach (var r in lines.Where(l => l.Received - l.Rejected > 0))
        {
            var stocked = r.Received - r.Rejected; var pk = Av.S(Keys.InvProduct(r.Line.ProductId));
            a.Add((DynamoTables.Inventory, new() { Update = new Update { TableName = inv, Key = new() { ["PK"] = pk, ["SK"] = Av.S($"INV#{r.LocationId:000}") },
                UpdateExpression = "SET quantity = if_not_exists(quantity, :z) + :q, #t = if_not_exists(#t, :type), product_id = :pid, location_id = :loc, location_name = if_not_exists(location_name, :ln), " +
                    "shelf = if_not_exists(shelf, :shelf), bin = if_not_exists(bin, :z), modified_date = :now, updated_at = :u, src = :src, src_lsn = :lsn, src_table = if_not_exists(src_table, :st), src_pk = if_not_exists(src_pk, :sp) ADD ver :one",
                ExpressionAttributeNames = new() { ["#t"] = "type" },
                ExpressionAttributeValues = new() { [":q"] = Av.N(stocked), [":z"] = Av.N(0), [":type"] = Av.S("ProductInventory"), [":pid"] = Av.N(r.Line.ProductId), [":loc"] = Av.N(r.LocationId),
                    [":ln"] = Av.S(r.LocationName), [":shelf"] = Av.S("N/A"), [":now"] = Av.S(Keys.Iso(now)), [":u"] = u, [":src"] = src, [":lsn"] = lsn, [":one"] = one,
                    [":st"] = Av.S("Production.ProductInventory"), [":sp"] = Av.S($"ProductID={r.Line.ProductId},LocationID={r.LocationId}") } } }));
            var old = r.Stock.Total; var nw = old + stocked; var below = nw < r.Stock.ReorderPoint;
            var vals = new Dictionary<string, AttributeValue> { [":new"] = Av.N(nw), [":old"] = Av.N(old), [":u"] = u, [":src"] = src, [":lsn"] = lsn, [":one"] = one };
            if (below) { vals[":r"] = Av.S("REORDER"); vals[":rs"] = pk; }
            a.Add((DynamoTables.Inventory, new() { Update = new Update { TableName = inv, Key = new() { ["PK"] = pk, ["SK"] = Av.S("PRODUCT") },
                UpdateExpression = "SET stock_qty = :new, updated_at = :u, src = :src, src_lsn = :lsn" + (below ? ", GSI1PK = :r, GSI1SK = :rs" : " REMOVE GSI1PK, GSI1SK") + " ADD ver :one",
                ConditionExpression = "attribute_exists(PK) AND (attribute_not_exists(stock_qty) OR stock_qty = :old)", ExpressionAttributeValues = vals } }));
            writes.Add($"aw-inventory {pk.S} INV#{r.LocationId:000} +{stocked} (ProductInventory -> stg.product_inventory)");
            writes.Add($"aw-inventory {pk.S} PRODUCT stock_qty {old}->{nw}{(below ? " (still REORDER)" : " (REORDER marker removed)")}");
        }
        foreach (var r in lines.Where(l => l.Received - l.Rejected > 0))
        {
            var id = txn++;
            var item = Av.Item(Keys.InvProduct(r.Line.ProductId), Keys.Txn(now, id), "InventoryTransaction");
            item["transaction_id"] = Av.N(id); item["product_id"] = Av.N(r.Line.ProductId); item["reference_order_id"] = Av.N(o.Id);
            item["reference_order_line_id"] = Av.N(r.Line.DetailId); item["transaction_date"] = Av.S(Keys.Iso(now)); item["transaction_type"] = Av.S("P");
            item["quantity"] = Av.N(r.Received - r.Rejected); item["actual_cost"] = Av.N(r.Line.UnitPrice); item["modified_date"] = Av.S(Keys.Iso(now));
            item["archived"] = Av.B(false); item["src_lsn"] = lsn;
            a.Add((DynamoTables.Inventory, new() { Put = new Put { TableName = inv, Item = item, ConditionExpression = "attribute_not_exists(PK)" } }));
            writes.Add($"aw-inventory {Keys.InvProduct(r.Line.ProductId)} {Keys.Txn(now, id)} type P qty {r.Received - r.Rejected} (InventoryTransaction -> stg.inventory_transaction)");
        }
        foreach (var r in lines.Where(l => l.Received - l.Rejected > 0))
            a.Add((DynamoTables.Catalog, new() { Update = new Update { TableName = cat, Key = new() { ["PK"] = Av.S(Keys.Product(r.Line.ProductId)), ["SK"] = Av.S("PRODUCT") },
                UpdateExpression = "SET stock_qty = :new, updated_at = :u", ConditionExpression = "attribute_exists(PK)",
                ExpressionAttributeValues = new() { [":new"] = Av.N(r.Stock.Total + r.Received - r.Rejected), [":u"] = u } } }));
        var summary = string.Join("; ", lines.Select(l => $"{l.Line.ProductName} +{l.Received}{(l.Rejected > 0 ? $" ({l.Rejected} rejected)" : "")} → {l.LocationName}"));
        a.Add((DynamoTables.Purchasing, new() { Put = new Put { TableName = pur, Item = Event(o.Id, now, o.Events.Count + 1, "receive", o.Status, to, actor, summary.Length > 400 ? summary[..400] : summary) } }));
        a.Add((DynamoTables.Sales, new() { Put = new Put { TableName = sales, Item = ChangeFeed.Entry(now, "po.receive", o.Number, actor, writes) } }));
        return a;
    }

    public async Task<PoResult> ReceiveAsync(int id, ReceiveRequest req, string actor, string? token = null)
    {
        var o = await GetOrderAsync(id) ?? throw new KeyNotFoundException();
        Check(o, "receive", req.Version);
        var lines = (req.Lines ?? []).Where(l => l.ReceivedQty > 0 || l.RejectedQty > 0).ToList();
        Validate(o, lines);
        var receipt = new List<ReceiptLine>();
        foreach (var r in lines)
        {
            var l = o.Lines.First(x => x.DetailId == r.DetailId);
            var stock = await fulfilment.GetStockAsync(l.ProductId);
            var loc = r.LocationId ?? stock.Locations.OrderByDescending(x => x.Quantity).Select(x => (int?)x.LocationId).FirstOrDefault() ?? Locations.Default;
            receipt.Add(new ReceiptLine(l, r.ReceivedQty, r.RejectedQty, loc, Locations.All.GetValueOrDefault(loc, $"Location {loc}"), stock));
        }
        var txnStart = await fulfilment.NextTxnIdsAsync(receipt.Count);
        try { await t.TransactAsync(ReceivePlan(t, o, receipt, actor, Now(), txnStart), token); }
        catch (TransactionCanceledException e)
        {
            throw new ConflictException($"Receipt for {o.Number} was rejected by a condition (PO or stock changed meanwhile): " +
                string.Join(", ", e.CancellationReasons?.Where(r => r.Code != "None").Select(r => r.Code).Distinct() ?? []) + ". Reload and retry.");
        }
        var after = (await GetOrderAsync(id))!;
        return new(after, after.Status == PoStatus.Complete ? "complete" : "partially-received");
    }
}
