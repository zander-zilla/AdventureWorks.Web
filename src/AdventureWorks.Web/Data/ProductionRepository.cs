using System.Collections.Concurrent;
using System.Globalization;
using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;

namespace AdventureWorks.Web.Data;

// ---------------------------------------------------------------- C2-4 production floor: DTOs

public sealed record WorkOrderSummary(int Id, string Number, int ProductId, string? ProductName, int OrderQty, int StockedQty, int ScrappedQty,
    DateTime StartDate, DateTime? EndDate, DateTime DueDate, string State, string? ScrapReason, string Source);
public sealed record RoutingStep(int OperationSequence, int LocationId, string LocationName, DateTime? ScheduledStartDate, DateTime? ScheduledEndDate,
    DateTime? ActualStartDate, DateTime? ActualEndDate, decimal? ActualResourceHrs, decimal? PlannedCost, decimal? ActualCost, bool Late, bool Done);
public sealed record WorkOrderEvent(DateTime At, string Action, string Actor, string? Note);
public sealed record WorkOrderDetail(WorkOrderSummary Order, long Version, bool ReadOnly, string[] Actions, List<RoutingStep> Routing, List<WorkOrderEvent> Events);
public sealed record WorkOrderList(string Month, List<WorkOrderSummary> Items, int Total, bool Truncated);
public sealed record BomNode(int ProductId, string Name, decimal PerAssemblyQty, string? UnitMeasureCode, int Level, DateTime? StartDate, DateTime? EndDate, List<BomNode> Children);
public sealed record BomTree(BomNode Root, string AsOf, int Queries, int Nodes, bool DepthCapped);
public sealed record AssemblyInfo(int ProductId, string Name);
public sealed record PlanComponent(int ProductId, string Name, decimal PerAssemblyQty, int Required, decimal OnHand, int? LocationId, bool Available);
public sealed record ProductionPlan(int ProductId, string Name, int OrderQty, DateTime StartDate, DateTime DueDate, List<RoutingStep> Routing,
    List<PlanComponent> Components, bool Feasible, List<string> Problems);
public sealed record CreateWorkOrderRequest(int ProductId, int OrderQty, DateTime? DueDate);
public sealed record OperationRequest(long Version, decimal ResourceHrs);
public sealed record CompleteWorkOrderRequest(long Version, int ScrappedQty, int? ScrapReasonId, int? LocationId);
public sealed record WorkOrderResult(WorkOrderDetail Order, string Outcome);
public sealed record ScrapReasonInfo(int Id, string Name);
public sealed record MonthKpi(string Month, int WorkOrders, int Closed, int OnTime, long OrderQty, long ScrappedQty, decimal ScrapRate, decimal OnTimeRate);
public sealed record ReasonCount(string Reason, int WorkOrders, long ScrappedQty);
public sealed record ProductionKpis(string From, string To, List<MonthKpi> Months, List<ReasonCount> ScrapReasons, int WorkOrders, long OrderQty, long ScrappedQty,
    decimal ScrapRate, decimal OnTimeRate, int Open);

/// <summary>
/// C2-4 production floor over aw-inventory (INV-01, INV-03, INV-04, INV-05, INV-06; all designed and loaded in Chapter 1, no key
/// changes). Work orders have no status column in AdventureWorks: state is derived (open = no end date; closed on time = end
/// &lt;= due; closed late). Create = one transaction (header + routing steps from a standard routing + event + change feed);
/// complete = one transaction (header end/stocked/scrapped/reason + remaining steps closed with planned hours + product stock in
/// (INV#loc, stock total, TXN W) + level-1 components consumed (INV#loc, stock total, TXN W with negative quantity) + catalog stock
/// copies + event + feed). Component consumption is INFERRED (AdventureWorks has no consumption records): labelled a simplification.
/// </summary>
public sealed class ProductionRepository(DynamoTables t, TimeProvider clock, FulfilmentRepository fulfilment)
{
    public const int NativeWoIdStart = 100_000;           // SQL: 1..72,591
    public const int MaxBomDepth = 4;                     // INV-04 compromise (Chapter 1 load test)
    public const int MaxTransactionItems = 100;
    public const int KpiMaxMonths = 24;
    public const int DefaultFinishedGoodsLocation = 7;    // Finished Goods Storage
    public const decimal PlannedHoursPerStep = 4m;
    public static readonly DateTime SqlDataEnd = new(2014, 6, 30);

    /// <summary>Standard routings (Production.Location work centres, cost rate per hour). AdventureWorks has no routing master; these
    /// are the step sequences seen in the SQL-era WorkOrderRouting rows (frames: forming → welding → debur → paint; assemblies:
    /// subassembly → final assembly).</summary>
    public static readonly IReadOnlyDictionary<int, (string Name, decimal CostRate)> WorkCentres = new Dictionary<int, (string, decimal)>
    {
        [10] = ("Frame Forming", 22.50m), [20] = ("Frame Welding", 25.00m), [30] = ("Debur and Polish", 14.50m), [40] = ("Paint", 15.75m),
        [45] = ("Specialized Paint", 18.00m), [50] = ("Subassembly", 12.25m), [60] = ("Final Assembly", 12.25m),
    };

    private IAmazonDynamoDB Inv => t.For(DynamoTables.Inventory);
    private string InvT => t.Name(DynamoTables.Inventory);
    private DateTime Now() { var n = clock.GetUtcNow().UtcDateTime; return n.AddTicks(-(n.Ticks % TimeSpan.TicksPerSecond)); }

    public static string WoKey(int id) => $"WO#{id:000000}";
    public static string WoNumber(int id) => id >= NativeWoIdStart ? $"WO-DDB-{id}" : $"WO{id:000000}";
    public static string DueBucket(DateTime d) => "WODUE#" + d.ToString("yyyy-MM", CultureInfo.InvariantCulture);
    public static string DueSk(DateTime d, int id) => $"{Keys.Iso(d)}#{id:000000}";
    public static string Assembly(int? id) => id is { } a ? $"ASSEMBLY#{a:000000}" : "ASSEMBLY#ROOT";

    // ---------------------------------------------------------------- mapping (pure)

    public static string State(DateTime? end, DateTime due) => end is null ? "Open" : end.Value.Date <= due.Date ? "Closed on time" : "Closed late";

    public static WorkOrderSummary ToSummary(Dictionary<string, AttributeValue> i, IReadOnlyDictionary<int, string>? reasons = null)
    {
        var id = i.Int("work_order_id") ?? 0; var due = i.Date("due_date") ?? DateTime.MinValue; var end = i.Date("end_date");
        var r = i.Int("scrap_reason_id");
        return new(id, WoNumber(id), i.Int("product_id") ?? 0, i.Str("product_name"), i.Int("order_qty") ?? 0, i.Int("stocked_qty") ?? 0, i.Int("scrapped_qty") ?? 0,
            i.Date("start_date") ?? DateTime.MinValue, end, due, State(end, due), r is { } x ? reasons?.GetValueOrDefault(x) ?? $"Reason {x}" : null, i.Str("src") ?? "sql");
    }

    public static RoutingStep ToStep(Dictionary<string, AttributeValue> i)
    {
        var loc = i.Int("location_id") ?? 0; var se = i.Date("scheduled_end_date"); var ae = i.Date("actual_end_date");
        return new(i.Int("operation_sequence") ?? 0, loc, WorkCentres.TryGetValue(loc, out var w) ? w.Name : Locations.All.GetValueOrDefault(loc, $"Location {loc}"),
            i.Date("scheduled_start_date"), se, i.Date("actual_start_date"), ae, i.Dec("actual_resource_hrs"), i.Dec("planned_cost"), i.Dec("actual_cost"),
            ae is { } a && se is { } s && a > s, ae is not null);
    }

    public static WorkOrderDetail ToDetail(List<Dictionary<string, AttributeValue>> items, IReadOnlyDictionary<int, string>? reasons = null)
    {
        var head = items.First(i => i.Str("SK") == "WO");
        var s = ToSummary(head, reasons);
        var routing = items.Where(i => i.Str("SK")?.StartsWith("ROUTING#") == true && i.IsLive()).Select(ToStep).OrderBy(r => r.OperationSequence).ToList();
        var events = items.Where(i => i.Str("SK")?.StartsWith("EVENT#") == true)
            .Select(e => new WorkOrderEvent(e.Date("at") ?? DateTime.MinValue, e.Str("action") ?? "", e.Str("actor") ?? "", e.Str("note"))).OrderBy(e => e.At).ToList();
        var ro = s.Id < NativeWoIdStart;
        return new(s, head.Long("ver") ?? 1, ro, Actions(ro, s, routing), routing, events);
    }

    public static string[] Actions(bool readOnly, WorkOrderSummary s, List<RoutingStep> routing) =>
        readOnly || s.EndDate is not null ? [] : routing.Any(r => !r.Done) ? ["record-operation", "complete"] : ["complete"];

    // ---------------------------------------------------------------- reference

    private (DateTimeOffset At, Dictionary<int, string> Map)? _reasons;
    public async Task<Dictionary<int, string>> ScrapReasonsAsync()
    {
        if (_reasons is { } c && clock.GetUtcNow() - c.At < TimeSpan.FromHours(1)) return c.Map;
        var items = await Inv.QueryAll(new QueryRequest { TableName = InvT, KeyConditionExpression = "PK = :pk", ExpressionAttributeValues = new() { [":pk"] = Av.S("SCRAPREASON") } });
        var map = items.Where(i => i.IsLive()).ToDictionary(i => i.Int("scrap_reason_id") ?? int.Parse(i.Str("SK")!, CultureInfo.InvariantCulture), i => i.Str("name") ?? "");
        _reasons = (clock.GetUtcNow(), map);
        return map;
    }

    // ---------------------------------------------------------------- INV-06 work orders

    public async Task<WorkOrderList> ForMonthAsync(string month, bool openOnly = false, int? productId = null, int max = 500)
    {
        if (!DateTime.TryParseExact(month, "yyyy-MM", CultureInfo.InvariantCulture, DateTimeStyles.None, out _)) throw new ArgumentException("month must be yyyy-MM.");
        var reasons = await ScrapReasonsAsync();
        var q = new QueryRequest { TableName = InvT, IndexName = "GSI2", KeyConditionExpression = "GSI2PK = :pk",
            ExpressionAttributeValues = new() { [":pk"] = Av.S("WODUE#" + month) } };
        var filters = new List<string>();
        if (openOnly) filters.Add("attribute_not_exists(end_date)");
        if (productId is { } p) { filters.Add("product_id = :p"); q.ExpressionAttributeValues[":p"] = Av.N(p); }
        if (filters.Count > 0) q.FilterExpression = string.Join(" AND ", filters);
        var items = (await Inv.QueryAll(q)).Where(i => i.IsLive()).Select(i => ToSummary(i, reasons)).ToList();
        return new(month, items.Take(max).ToList(), items.Count, items.Count > max);
    }

    /// <summary>Open work orders: one INV-06 query per due month from 3 months back to 6 months ahead (FilterExpression open).</summary>
    public async Task<List<WorkOrderSummary>> OpenAsync()
    {
        var now = Now(); var months = Enumerable.Range(-3, 10).Select(k => now.AddMonths(k).ToString("yyyy-MM", CultureInfo.InvariantCulture));
        var lists = await Task.WhenAll(months.Select(m => ForMonthAsync(m, openOnly: true)));
        return lists.SelectMany(l => l.Items).OrderBy(w => w.DueDate).ToList();
    }

    public async Task<WorkOrderDetail?> GetAsync(int id)
    {
        var items = await Inv.QueryAll(new QueryRequest { TableName = InvT, ConsistentRead = true, KeyConditionExpression = "PK = :pk",
            ExpressionAttributeValues = new() { [":pk"] = Av.S(WoKey(id)) } });
        return items.Any(i => i.Str("SK") == "WO" && i.IsLive()) ? ToDetail(items, await ScrapReasonsAsync()) : null;
    }

    // ---------------------------------------------------------------- scrap and on-time KPIs

    public static IEnumerable<string> MonthRange(string from, string to)
    {
        var f = DateTime.ParseExact(from, "yyyy-MM", CultureInfo.InvariantCulture); var e = DateTime.ParseExact(to, "yyyy-MM", CultureInfo.InvariantCulture);
        if (e < f) throw new ArgumentException("to must not be before from.");
        if ((e.Year - f.Year) * 12 + e.Month - f.Month + 1 > KpiMaxMonths) throw new ArgumentException($"At most {KpiMaxMonths} months.");
        for (var d = f; d <= e; d = d.AddMonths(1)) yield return d.ToString("yyyy-MM", CultureInfo.InvariantCulture);
    }

    /// <summary>Pure: scrap rate = scrapped / ordered; on-time = closed with end date &lt;= due date / closed (by due month).
    /// Same definitions as dw.v_production_scrap_on_time.</summary>
    public static ProductionKpis Kpis(string from, string to, IReadOnlyList<(string Month, List<WorkOrderSummary> Items)> months)
    {
        static decimal Rate(decimal a, decimal b) => b == 0 ? 0 : Math.Round(a / b, 4, MidpointRounding.AwayFromZero);
        var ms = months.Select(m =>
        {
            var closed = m.Items.Where(w => w.EndDate is not null).ToList();
            long oq = m.Items.Sum(w => (long)w.OrderQty), sq = m.Items.Sum(w => (long)w.ScrappedQty);
            var on = closed.Count(w => w.State == "Closed on time");
            return new MonthKpi(m.Month, m.Items.Count, closed.Count, on, oq, sq, Rate(sq, oq), Rate(on, closed.Count));
        }).ToList();
        var all = months.SelectMany(m => m.Items).ToList();
        var reasons = all.Where(w => w.ScrapReason is not null).GroupBy(w => w.ScrapReason!)
            .Select(g => new ReasonCount(g.Key, g.Count(), g.Sum(w => (long)w.ScrappedQty))).OrderByDescending(r => r.ScrappedQty).ThenBy(r => r.Reason).ToList();
        long toq = all.Sum(w => (long)w.OrderQty), tsq = all.Sum(w => (long)w.ScrappedQty);
        int tc = ms.Sum(m => m.Closed), ton = ms.Sum(m => m.OnTime);
        return new(from, to, ms, reasons, all.Count, toq, tsq, Rate(tsq, toq), Rate(ton, tc), all.Count(w => w.EndDate is null));
    }

    private readonly ConcurrentDictionary<string, (DateTimeOffset At, List<WorkOrderSummary> Items)> _monthCache = new();
    public async Task<ProductionKpis> KpisAsync(string from, string to)
    {
        var months = MonthRange(from, to).ToList();
        var now = clock.GetUtcNow(); var current = Now().ToString("yyyy-MM", CultureInfo.InvariantCulture);
        var rows = await Task.WhenAll(months.Select(async m =>
        {
            // SQL-era months never change (CDC aside): cache 10 minutes; months with app work orders (>= this year) always fresh
            if (string.CompareOrdinal(m, current[..4]) < 0 && _monthCache.TryGetValue(m, out var c) && now - c.At < TimeSpan.FromMinutes(10)) return (m, c.Items);
            var l = await ForMonthAsync(m, max: int.MaxValue);
            _monthCache[m] = (now, l.Items);
            return (m, l.Items);
        }));
        return Kpis(from, to, rows);
    }

    // ---------------------------------------------------------------- INV-04 / INV-05 BOM

    public static bool ValidAt(Dictionary<string, AttributeValue> e, DateTime d) =>
        e.IsLive() && (e.Date("start_date") ?? DateTime.MinValue) <= d && (e.Date("end_date") is not { } end || d < end);

    public async Task<List<AssemblyInfo>> AssembliesAsync()
    {
        var items = await Inv.QueryAll(new QueryRequest { TableName = InvT, KeyConditionExpression = "PK = :pk", ExpressionAttributeValues = new() { [":pk"] = Av.S(Assembly(null)) } });
        var now = Now();
        return items.Where(i => ValidAt(i, now)).GroupBy(i => i.Int("component_id") ?? 0)
            .Select(g => new AssemblyInfo(g.Key, g.First().Str("component_name") ?? $"Product {g.Key}")).OrderBy(a => a.Name).ToList();
    }

    private async Task<List<Dictionary<string, AttributeValue>>> EdgesAsync(int assemblyId) =>
        await Inv.QueryAll(new QueryRequest { TableName = InvT, KeyConditionExpression = "PK = :pk", ExpressionAttributeValues = new() { [":pk"] = Av.S(Assembly(assemblyId)) } });

    private async Task<Dictionary<int, string>> NamesAsync(IEnumerable<int> ids)
    {
        var map = new Dictionary<int, string>();
        foreach (var chunk in ids.Distinct().Chunk(100))
        {
            var r = await Inv.BatchGetItemAsync(new BatchGetItemRequest { RequestItems = new() { [InvT] = new KeysAndAttributes {
                Keys = chunk.Select(id => new Dictionary<string, AttributeValue> { ["PK"] = Av.S(Keys.InvProduct(id)), ["SK"] = Av.S("PRODUCT") }).ToList(),
                ProjectionExpression = "product_id, #n", ExpressionAttributeNames = new() { ["#n"] = "name" } } } });
            foreach (var i in r.Responses.GetValueOrDefault(InvT) ?? []) map[i.Int("product_id") ?? 0] = i.Str("name") ?? "";
        }
        return map;
    }

    /// <summary>INV-04: multi-level explosion as of a date, one Query per assembly per level (levels in parallel), max depth 4.</summary>
    public async Task<BomTree> ExplodeAsync(int productId, DateTime asOf, int depth = MaxBomDepth)
    {
        depth = Math.Clamp(depth, 1, MaxBomDepth);
        var names = await NamesAsync([productId]);
        var root = new BomNode(productId, names.GetValueOrDefault(productId, $"Product {productId}"), 1, null, 0, null, null, new());
        var level = new List<BomNode> { root }; int queries = 0, nodes = 1; var capped = false;
        for (var lv = 1; lv <= depth && level.Count > 0; lv++)
        {
            var edges = await Task.WhenAll(level.Select(async n => (n, Edges: await EdgesAsync(n.ProductId))));
            queries += level.Count;
            var next = new List<BomNode>();
            foreach (var (parent, es) in edges)
                foreach (var e in es.Where(e => ValidAt(e, asOf)).OrderBy(e => e.Str("component_name")))
                {
                    var c = new BomNode(e.Int("component_id") ?? 0, e.Str("component_name") ?? "", e.Dec("per_assembly_qty") ?? 1, e.Str("unit_measure_code"), lv,
                        e.Date("start_date"), e.Date("end_date"), new());
                    parent.Children.Add(c); next.Add(c); nodes++;
                }
            if (lv == depth && next.Count > 0) capped = true;
            level = next;
        }
        if (capped)   // one probe: does any leaf at the cap still have children?
        {
            var probe = await Task.WhenAll(level.Take(25).Select(n => EdgesAsync(n.ProductId)));
            queries += Math.Min(level.Count, 25);
            capped = probe.Any(p => p.Any(e => ValidAt(e, asOf)));
        }
        return new(root, asOf.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture), queries, nodes, capped);
    }

    /// <summary>INV-05: where used, upwards through GSI1 COMPONENT#c, one Query per component per level, max depth 4.
    /// Children of a node here are the assemblies that use it.</summary>
    public async Task<BomTree> WhereUsedAsync(int componentId, DateTime asOf, int depth = MaxBomDepth)
    {
        depth = Math.Clamp(depth, 1, MaxBomDepth);
        var root = new BomNode(componentId, "", 1, null, 0, null, null, new());
        var level = new List<BomNode> { root }; int queries = 0, nodes = 1; var capped = false;
        var pending = new List<(BomNode Node, int Id)>();
        for (var lv = 1; lv <= depth && level.Count > 0; lv++)
        {
            var ups = await Task.WhenAll(level.Select(async n => (n, Items: await Inv.QueryAll(new QueryRequest { TableName = InvT, IndexName = "GSI1",
                KeyConditionExpression = "GSI1PK = :pk", ExpressionAttributeValues = new() { [":pk"] = Av.S($"COMPONENT#{n.ProductId:000000}") } }))));
            queries += level.Count;
            var next = new List<BomNode>();
            foreach (var (child, es) in ups)
                foreach (var e in es.Where(e => ValidAt(e, asOf) && e.Str("PK") != Assembly(null)))
                {
                    var aid = e.Int("product_assembly_id") ?? 0;
                    var n = new BomNode(aid, "", e.Dec("per_assembly_qty") ?? 1, e.Str("unit_measure_code"), lv, e.Date("start_date"), e.Date("end_date"), new());
                    child.Children.Add(n); next.Add(n); nodes++;
                }
            if (lv == depth && next.Count > 0) capped = true;
            level = next;
        }
        var names = await NamesAsync(Flatten(root).Select(n => n.ProductId));
        return new(Rename(root, names), asOf.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture), queries, nodes, capped);
    }

    public static IEnumerable<BomNode> Flatten(BomNode n) => new[] { n }.Concat(n.Children.SelectMany(Flatten));
    private static BomNode Rename(BomNode n, IReadOnlyDictionary<int, string> names) =>
        n with { Name = names.GetValueOrDefault(n.ProductId, $"Product {n.ProductId}"), Children = n.Children.Select(c => Rename(c, names)).OrderBy(c => c.Name).ToList() };

    // ---------------------------------------------------------------- plan + create

    /// <summary>Pure: the standard routing for a product (frames: 10-20-30-40; anything with components: 50-60; else 50),
    /// scheduled back to back from the start date, one working day (8h) per step, planned cost = planned hours x cost rate.</summary>
    public static List<RoutingStep> StandardRouting(string productName, bool hasComponents, DateTime start)
    {
        int[] locs = productName.Contains("Frame", StringComparison.OrdinalIgnoreCase) && !productName.Contains("Assembly", StringComparison.OrdinalIgnoreCase)
            ? [10, 20, 30, 40] : hasComponents ? [50, 60] : [50];
        var steps = new List<RoutingStep>(); var s = start;
        for (var k = 0; k < locs.Length; k++)
        {
            var w = WorkCentres[locs[k]];
            steps.Add(new RoutingStep(k + 1, locs[k], w.Name, s, s.AddDays(1), null, null, null, Math.Round(PlannedHoursPerStep * w.CostRate, 4), null, false, false));
            s = s.AddDays(1);
        }
        return steps;
    }

    public static int Required(decimal perAssembly, int orderQty) => (int)Math.Ceiling(perAssembly * orderQty);

    /// <summary>Transaction size of a completion: header, event, feed, remaining steps, product (INV, total, TXN, catalog),
    /// 4 per consumed component.</summary>
    public static int CompletionItems(int openSteps, int components, bool stocked) => 3 + openSteps + (stocked ? 4 : 0) + 4 * components;

    public async Task<ProductionPlan> PlanAsync(int productId, int orderQty, DateTime? due = null)
    {
        if (orderQty < 1 || orderQty > 10_000) throw new ArgumentException("Order quantity must be 1-10,000.");
        var now = Now();
        var tree = await ExplodeAsync(productId, now, 1);
        var comps = tree.Root.Children;
        var start = now.Date.AddDays(1);
        var routing = StandardRouting(tree.Root.Name, comps.Count > 0, start);
        var dueDate = due?.Date ?? routing.Last().ScheduledEndDate!.Value.Date.AddDays(2);
        var problems = new List<string>();
        var stock = new Dictionary<int, FulfilmentRepository.Stock>();
        foreach (var c in comps.Select(c => c.ProductId).Distinct()) stock[c] = await fulfilment.GetStockAsync(c);
        var need = comps.GroupBy(c => c.ProductId).Select(g => (g.Key, g.First().Name, Required(g.Sum(x => x.PerAssemblyQty), orderQty))).ToList();
        var (alloc, shortages) = FulfilmentRepository.Allocate(need, stock);
        var pcs = need.Select(n => new PlanComponent(n.Key, n.Name, comps.Where(c => c.ProductId == n.Key).Sum(c => c.PerAssemblyQty), n.Item3, stock[n.Key].Total,
            alloc.FirstOrDefault(a => a.ProductId == n.Key)?.LocationId, alloc.Any(a => a.ProductId == n.Key))).ToList();
        problems.AddRange(shortages.Select(s => "Short: " + s));
        if (tree.Root.Name.StartsWith("Product ", StringComparison.Ordinal) && comps.Count == 0) problems.Add($"Unknown product {productId}.");
        if (CompletionItems(routing.Count, need.Count, true) > MaxTransactionItems) problems.Add($"{need.Count} components exceed one completion transaction ({MaxTransactionItems} items).");
        if (dueDate < start) problems.Add("Due date is before the start date.");
        return new(productId, tree.Root.Name, orderQty, start, dueDate, routing, pcs, problems.Count == 0, problems);
    }

    private async Task<int> NextWoIdAsync()
    {
        var r = await Inv.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = InvT, Key = new() { ["PK"] = Av.S("COUNTER"), ["SK"] = Av.S("WO") }, ReturnValues = ReturnValue.UPDATED_NEW,
            UpdateExpression = "ADD next_id :one SET #t = if_not_exists(#t, :t), src = :src", ExpressionAttributeNames = new() { ["#t"] = "type" },
            ExpressionAttributeValues = new() { [":one"] = Av.N(1), [":t"] = Av.S("WoIdCounter"), [":src"] = Av.S("ddb") },
        });
        return NativeWoIdStart + int.Parse(r.Attributes["next_id"].N, CultureInfo.InvariantCulture) - 1;
    }

    public static Dictionary<string, AttributeValue> Event(int woId, DateTime now, int seq, string action, string actor, string? note)
    {
        var e = Av.Item(WoKey(woId), Keys.OrderEvent(now, seq), "WorkOrderEvent");
        e["work_order_id"] = Av.N(woId); e["action"] = Av.S(action); e["actor"] = Av.S(actor); e["at"] = Av.S(Keys.Iso(now) + "Z"); e["src_lsn"] = Av.S(Keys.AppLsn);
        e.Set("note", note);
        return e;
    }

    /// <summary>Pure (unit-tested): the create transaction - header (GSI2 WODUE#due-month for INV-06), one routing item per step,
    /// event, change feed. All in aw-inventory except the feed.</summary>
    public static List<(string Table, TransactWriteItem Action)> CreatePlan(DynamoTables t, int id, ProductionPlan p, string actor, DateTime now)
    {
        string inv = t.Name(DynamoTables.Inventory), sales = t.Name(DynamoTables.Sales);
        var lsn = Av.S(Keys.AppLsn);
        var h = Av.Item(WoKey(id), "WO", "WorkOrder");
        h["work_order_id"] = Av.N(id); h["product_id"] = Av.N(p.ProductId); h["product_name"] = Av.S(p.Name); h["order_qty"] = Av.N(p.OrderQty);
        h["stocked_qty"] = Av.N(0); h["scrapped_qty"] = Av.N(0); h["start_date"] = Av.S(Keys.Iso(p.StartDate)); h["due_date"] = Av.S(Keys.Iso(p.DueDate));
        h["modified_date"] = Av.S(Keys.Iso(now)); h["GSI2PK"] = Av.S(DueBucket(p.DueDate)); h["GSI2SK"] = Av.S(DueSk(p.DueDate, id));
        h["src_lsn"] = lsn; h["src_table"] = Av.S("Production.WorkOrder"); h["src_pk"] = Av.S($"WorkOrderID={id}"); h["created_by"] = Av.S(actor);
        var a = new List<(string, TransactWriteItem)> { (DynamoTables.Inventory, new() { Put = new Put { TableName = inv, Item = h, ConditionExpression = "attribute_not_exists(PK)" } }) };
        var writes = new List<string> { $"aw-inventory {WoKey(id)} WO (WorkOrder -> stg.work_order), GSI2 {DueBucket(p.DueDate)} (INV-06)" };
        foreach (var s in p.Routing)
        {
            var r = Av.Item(WoKey(id), $"ROUTING#{s.OperationSequence:000}#{s.LocationId:000}", "WorkOrderRouting");
            r["work_order_id"] = Av.N(id); r["product_id"] = Av.N(p.ProductId); r["operation_sequence"] = Av.N(s.OperationSequence); r["location_id"] = Av.N(s.LocationId);
            r["scheduled_start_date"] = Av.S(Keys.Iso(s.ScheduledStartDate!.Value)); r["scheduled_end_date"] = Av.S(Keys.Iso(s.ScheduledEndDate!.Value));
            r["planned_cost"] = Av.N(s.PlannedCost ?? 0); r["modified_date"] = Av.S(Keys.Iso(now));
            r["src_lsn"] = lsn; r["src_table"] = Av.S("Production.WorkOrderRouting"); r["src_pk"] = Av.S($"WorkOrderID={id},ProductID={p.ProductId},OperationSequence={s.OperationSequence}");
            a.Add((DynamoTables.Inventory, new() { Put = new Put { TableName = inv, Item = r, ConditionExpression = "attribute_not_exists(PK)" } }));
        }
        writes.Add($"aw-inventory {WoKey(id)} ROUTING x{p.Routing.Count} ({string.Join(" → ", p.Routing.Select(r => r.LocationName))}) (WorkOrderRouting -> stg.work_order_routing)");
        a.Add((DynamoTables.Inventory, new() { Put = new Put { TableName = inv, Item = Event(id, now, 1, "create", actor, $"{p.OrderQty} x {p.Name}, due {p.DueDate:yyyy-MM-dd}") } }));
        a.Add((DynamoTables.Sales, new() { Put = new Put { TableName = sales, Item = ChangeFeed.Entry(now, "wo.create", WoNumber(id), actor, writes) } }));
        return a;
    }

    public async Task<WorkOrderDetail> CreateAsync(CreateWorkOrderRequest req, string actor, string? token = null)
    {
        var plan = await PlanAsync(req.ProductId, req.OrderQty, req.DueDate);
        if (plan.Components.Count == 0 && plan.Problems.Any(p => p.StartsWith("Unknown", StringComparison.Ordinal))) throw new KeyNotFoundException();
        if (!plan.Feasible) throw new ArgumentException(string.Join(" ", plan.Problems));
        var id = await NextWoIdAsync();
        await t.TransactAsync(CreatePlan(t, id, plan, actor, Now()), token);
        return (await GetAsync(id))!;
    }

    // ---------------------------------------------------------------- record an operation

    private static void Check(WorkOrderDetail w, string action, long version)
    {
        if (w.ReadOnly) throw new ConflictException($"{w.Order.Number} is a SQL-era work order (read-only).");
        if (w.Version != version) throw new ConflictException($"{w.Order.Number} was changed by someone else (version {w.Version}, you had {version}). Reload and retry.");
        if (!w.Actions.Contains(action)) throw new ConflictException($"Cannot {action} {w.Order.Number}: it is {w.Order.State}.");
    }

    private static Update Header(string inv, WorkOrderDetail w, DateTime now, string? extraSet = null, Dictionary<string, AttributeValue>? extra = null)
    {
        var vals = new Dictionary<string, AttributeValue> { [":v"] = Av.N(w.Version), [":one"] = Av.N(1), [":now"] = Av.S(Keys.Iso(now)),
            [":u"] = Av.S(Keys.Iso(now) + "Z"), [":src"] = Av.S("ddb"), [":lsn"] = Av.S(Keys.AppLsn) };
        foreach (var kv in extra ?? new()) vals[kv.Key] = kv.Value;
        return new Update { TableName = inv, Key = new() { ["PK"] = Av.S(WoKey(w.Order.Id)), ["SK"] = Av.S("WO") },
            UpdateExpression = "SET modified_date = :now, updated_at = :u, src = :src, src_lsn = :lsn" + (extraSet is null ? "" : ", " + extraSet) + " ADD ver :one",
            ConditionExpression = "ver = :v AND attribute_not_exists(end_date)", ExpressionAttributeValues = vals };
    }

    private static Update StepUpdate(string inv, int woId, RoutingStep s, DateTime start, DateTime end, decimal hrs)
    {
        var rate = WorkCentres.TryGetValue(s.LocationId, out var w) ? w.CostRate : 0m;
        return new Update { TableName = inv, Key = new() { ["PK"] = Av.S(WoKey(woId)), ["SK"] = Av.S($"ROUTING#{s.OperationSequence:000}#{s.LocationId:000}") },
            UpdateExpression = "SET actual_start_date = :as, actual_end_date = :ae, actual_resource_hrs = :h, actual_cost = :c, modified_date = :ae, updated_at = :u, src = :src, src_lsn = :lsn ADD ver :one",
            ConditionExpression = "attribute_not_exists(actual_end_date)",
            ExpressionAttributeValues = new() { [":as"] = Av.S(Keys.Iso(start)), [":ae"] = Av.S(Keys.Iso(end)), [":h"] = Av.N(hrs), [":c"] = Av.N(Math.Round(hrs * rate, 4)),
                [":u"] = Av.S(Keys.Iso(end) + "Z"), [":src"] = Av.S("ddb"), [":lsn"] = Av.S(Keys.AppLsn), [":one"] = Av.N(1) } };
    }

    /// <summary>Pure: the next operation to record and its actual start (= previous step's actual end, else the work-order start, never after now).</summary>
    public static (RoutingStep Step, DateTime Start) NextStep(WorkOrderDetail w, DateTime now)
    {
        var s = w.Routing.FirstOrDefault(r => !r.Done) ?? throw new ConflictException($"All operations of {w.Order.Number} are recorded.");
        var prev = w.Routing.Where(r => r.Done && r.OperationSequence < s.OperationSequence).Select(r => r.ActualEndDate).Max();
        var start = prev ?? w.Order.StartDate;
        return (s, start > now ? now : start);
    }

    public static List<(string Table, TransactWriteItem Action)> OperationPlan(DynamoTables t, WorkOrderDetail w, decimal hrs, string actor, DateTime now)
    {
        string inv = t.Name(DynamoTables.Inventory), sales = t.Name(DynamoTables.Sales);
        var (s, start) = NextStep(w, now);
        var note = $"op {s.OperationSequence} {s.LocationName}: {hrs:0.##} h";
        return
        [
            (DynamoTables.Inventory, new() { Update = Header(inv, w, now) }),
            (DynamoTables.Inventory, new() { Update = StepUpdate(inv, w.Order.Id, s, start, now, hrs) }),
            (DynamoTables.Inventory, new() { Put = new Put { TableName = inv, Item = Event(w.Order.Id, now, w.Events.Count + 1, "operation", actor, note) } }),
            (DynamoTables.Sales, new() { Put = new Put { TableName = sales, Item = ChangeFeed.Entry(now, "wo.operation", w.Order.Number, actor,
                [$"aw-inventory {WoKey(w.Order.Id)} ROUTING#{s.OperationSequence:000}#{s.LocationId:000} actual {hrs:0.##} h (WorkOrderRouting -> stg.work_order_routing)"]) } }),
        ];
    }

    public async Task<WorkOrderResult> RecordOperationAsync(int id, OperationRequest req, string actor, string? token = null)
    {
        if (req.ResourceHrs <= 0 || req.ResourceHrs > 100) throw new ArgumentException("Resource hours must be between 0 and 100.");
        var w = await GetAsync(id) ?? throw new KeyNotFoundException();
        Check(w, "record-operation", req.Version);
        try { await t.TransactAsync(OperationPlan(t, w, Math.Round(req.ResourceHrs, 4), actor, Now()), token); }
        catch (TransactionCanceledException) { throw new ConflictException($"{w.Order.Number} changed meanwhile. Reload and retry."); }
        return new((await GetAsync(id))!, "operation-recorded");
    }

    // ---------------------------------------------------------------- complete

    public sealed record Consumption(int ProductId, string Name, int Quantity, int LocationId, FulfilmentRepository.Stock Stock);

    public static void ValidateCompletion(WorkOrderDetail w, CompleteWorkOrderRequest req, IReadOnlyDictionary<int, string> reasons)
    {
        if (req.ScrappedQty < 0 || req.ScrappedQty > w.Order.OrderQty) throw new ArgumentException($"Scrapped quantity must be 0-{w.Order.OrderQty}.");
        if (req.ScrappedQty > 0 && (req.ScrapReasonId is not { } r || !reasons.ContainsKey(r))) throw new ArgumentException("A scrap reason is required when units are scrapped.");
        if (req.ScrappedQty == 0 && req.ScrapReasonId is not null) throw new ArgumentException("No scrap reason without scrapped units.");
        if (req.LocationId is { } l && !Locations.All.ContainsKey(l)) throw new ArgumentException($"Unknown location {l}.");
    }

    /// <summary>Pure (unit-tested): the completion transaction. AdventureWorks: StockedQty = OrderQty - ScrappedQty. Components are consumed
    /// for the whole order quantity (scrapped units used material too). Group order: inventory first (conditions), catalog, sales.</summary>
    public static List<(string Table, TransactWriteItem Action)> CompletePlan(DynamoTables t, WorkOrderDetail w, CompleteWorkOrderRequest req, string? reasonName,
        int locationId, FulfilmentRepository.Stock productStock, List<Consumption> components, string actor, DateTime now, long txnStart)
    {
        string inv = t.Name(DynamoTables.Inventory), cat = t.Name(DynamoTables.Catalog), sales = t.Name(DynamoTables.Sales);
        var o = w.Order; var stocked = o.OrderQty - req.ScrappedQty;
        var u = Av.S(Keys.Iso(now) + "Z"); var lsn = Av.S(Keys.AppLsn); var src = Av.S("ddb"); var one = Av.N(1);
        var a = new List<(string, TransactWriteItem)>(); var writes = new List<string>();
        var extra = new Dictionary<string, AttributeValue> { [":end"] = Av.S(Keys.Iso(now)), [":stk"] = Av.N(stocked), [":scr"] = Av.N(req.ScrappedQty) };
        var set = "end_date = :end, stocked_qty = :stk, scrapped_qty = :scr";
        if (req.ScrapReasonId is { } r) { extra[":r"] = Av.N(r); set += ", scrap_reason_id = :r"; }
        a.Add((DynamoTables.Inventory, new() { Update = Header(inv, w, now, set, extra) }));
        writes.Add($"aw-inventory {WoKey(o.Id)} WO end {now:yyyy-MM-dd}, stocked {stocked}, scrapped {req.ScrappedQty}{(reasonName is null ? "" : $" ({reasonName})")} ({State(now, o.DueDate)})");
        // remaining steps closed with planned hours, back to back
        var prevEnd = w.Routing.Where(s => s.Done).Select(s => s.ActualEndDate).Max() ?? o.StartDate;
        var open = w.Routing.Where(s => !s.Done).ToList();
        foreach (var s in open)
        {
            var st = prevEnd > now ? now : prevEnd;
            a.Add((DynamoTables.Inventory, new() { Update = StepUpdate(inv, o.Id, s, st, now, PlannedHoursPerStep) }));
            prevEnd = now;
        }
        if (open.Count > 0) writes.Add($"aw-inventory {WoKey(o.Id)} ROUTING x{open.Count} closed at planned {PlannedHoursPerStep} h");
        long txn = txnStart;
        void Move(int productId, string name, int locId, string locName, int delta, FulfilmentRepository.Stock st, string what)
        {
            var pk = Av.S(Keys.InvProduct(productId));
            var invVals = new Dictionary<string, AttributeValue> { [":q"] = Av.N(delta), [":z"] = Av.N(0), [":type"] = Av.S("ProductInventory"), [":pid"] = Av.N(productId),
                [":loc"] = Av.N(locId), [":ln"] = Av.S(locName), [":shelf"] = Av.S("N/A"), [":now"] = Av.S(Keys.Iso(now)), [":u"] = u, [":src"] = src, [":lsn"] = lsn, [":one"] = one,
                [":st"] = Av.S("Production.ProductInventory"), [":sp"] = Av.S($"ProductID={productId},LocationID={locId}") };
            string? cond = null;
            if (delta < 0) { invVals[":need"] = Av.N(-delta); cond = "quantity >= :need"; }
            a.Add((DynamoTables.Inventory, new() { Update = new Update { TableName = inv, Key = new() { ["PK"] = pk, ["SK"] = Av.S($"INV#{locId:000}") },
                UpdateExpression = "SET quantity = if_not_exists(quantity, :z) + :q, #t = if_not_exists(#t, :type), product_id = :pid, location_id = :loc, location_name = if_not_exists(location_name, :ln), " +
                    "shelf = if_not_exists(shelf, :shelf), bin = if_not_exists(bin, :z), modified_date = :now, updated_at = :u, src = :src, src_lsn = :lsn, src_table = if_not_exists(src_table, :st), src_pk = if_not_exists(src_pk, :sp) ADD ver :one",
                ConditionExpression = cond, ExpressionAttributeNames = new() { ["#t"] = "type" }, ExpressionAttributeValues = invVals } }));
            var old = st.Total; var nw = old + delta; var below = nw < st.ReorderPoint;
            var vals = new Dictionary<string, AttributeValue> { [":new"] = Av.N(nw), [":old"] = Av.N(old), [":u"] = u, [":src"] = src, [":lsn"] = lsn, [":one"] = one };
            if (below) { vals[":r"] = Av.S("REORDER"); vals[":rs"] = pk; }
            a.Add((DynamoTables.Inventory, new() { Update = new Update { TableName = inv, Key = new() { ["PK"] = pk, ["SK"] = Av.S("PRODUCT") },
                UpdateExpression = "SET stock_qty = :new, updated_at = :u, src = :src, src_lsn = :lsn" + (below ? ", GSI1PK = :r, GSI1SK = :rs" : " REMOVE GSI1PK, GSI1SK") + " ADD ver :one",
                ConditionExpression = "attribute_exists(PK) AND (attribute_not_exists(stock_qty) OR stock_qty = :old)", ExpressionAttributeValues = vals } }));
            var id = txn++;
            var item = Av.Item(Keys.InvProduct(productId), Keys.Txn(now, id), "InventoryTransaction");
            item["transaction_id"] = Av.N(id); item["product_id"] = Av.N(productId); item["reference_order_id"] = Av.N(o.Id); item["reference_order_line_id"] = Av.N(0);
            item["transaction_date"] = Av.S(Keys.Iso(now)); item["transaction_type"] = Av.S("W"); item["quantity"] = Av.N(delta); item["actual_cost"] = Av.N(0);
            item["modified_date"] = Av.S(Keys.Iso(now)); item["archived"] = Av.B(false); item["src_lsn"] = lsn;
            a.Add((DynamoTables.Inventory, new() { Put = new Put { TableName = inv, Item = item, ConditionExpression = "attribute_not_exists(PK)" } }));
            writes.Add($"aw-inventory {pk.S} INV#{locId:000} {delta:+#;-#;0}, stock {old}->{nw}{(below ? " REORDER" : "")}, {Keys.Txn(now, id)} type W {delta:+#;-#;0} ({what})");
        }
        if (stocked > 0) Move(o.ProductId, o.ProductName ?? "", locationId, Locations.All.GetValueOrDefault(locationId, $"Location {locationId}"), stocked, productStock, "product in");
        foreach (var c in components)
            Move(c.ProductId, c.Name, c.LocationId, c.Stock.Locations.FirstOrDefault(l => l.LocationId == c.LocationId).Name ?? Locations.All.GetValueOrDefault(c.LocationId, ""), -c.Quantity, c.Stock, "component consumed, inferred");
        if (stocked > 0)
            a.Add((DynamoTables.Catalog, new() { Update = new Update { TableName = cat, Key = new() { ["PK"] = Av.S(Keys.Product(o.ProductId)), ["SK"] = Av.S("PRODUCT") },
                UpdateExpression = "SET stock_qty = :new, updated_at = :u", ConditionExpression = "attribute_exists(PK)",
                ExpressionAttributeValues = new() { [":new"] = Av.N(productStock.Total + stocked), [":u"] = u } } }));
        foreach (var c in components)
            a.Add((DynamoTables.Catalog, new() { Update = new Update { TableName = cat, Key = new() { ["PK"] = Av.S(Keys.Product(c.ProductId)), ["SK"] = Av.S("PRODUCT") },
                UpdateExpression = "SET stock_qty = :new, updated_at = :u", ConditionExpression = "attribute_exists(PK)",
                ExpressionAttributeValues = new() { [":new"] = Av.N(c.Stock.Total - c.Quantity), [":u"] = u } } }));
        var note = $"stocked {stocked} → {Locations.All.GetValueOrDefault(locationId)}" + (req.ScrappedQty > 0 ? $", scrapped {req.ScrappedQty} ({reasonName})" : "") +
            (components.Count > 0 ? $", {components.Count} components consumed" : "");
        a.Add((DynamoTables.Inventory, new() { Put = new Put { TableName = inv, Item = Event(o.Id, now, w.Events.Count + 1, "complete", actor, note) } }));
        a.Add((DynamoTables.Sales, new() { Put = new Put { TableName = sales, Item = ChangeFeed.Entry(now, "wo.complete", o.Number, actor, writes) } }));
        return a;
    }

    public async Task<WorkOrderResult> CompleteAsync(int id, CompleteWorkOrderRequest req, string actor, string? token = null)
    {
        var w = await GetAsync(id) ?? throw new KeyNotFoundException();
        Check(w, "complete", req.Version);
        var reasons = await ScrapReasonsAsync();
        ValidateCompletion(w, req, reasons);
        var now = Now();
        var tree = await ExplodeAsync(w.Order.ProductId, now, 1);
        var need = tree.Root.Children.GroupBy(c => c.ProductId).Select(g => (g.Key, g.First().Name, Required(g.Sum(x => x.PerAssemblyQty), w.Order.OrderQty))).ToList();
        var stock = new Dictionary<int, FulfilmentRepository.Stock>();
        foreach (var n in need) stock[n.Key] = await fulfilment.GetStockAsync(n.Key);
        var (alloc, shortages) = FulfilmentRepository.Allocate(need, stock);
        if (shortages.Count > 0) throw new ConflictException("Not enough components in stock: " + string.Join("; ", shortages) + ".");
        var comps = alloc.Select(x => new Consumption(x.ProductId, need.First(n => n.Key == x.ProductId).Name, x.Quantity, x.LocationId, stock[x.ProductId])).ToList();
        var stocked = w.Order.OrderQty - req.ScrappedQty;
        if (CompletionItems(w.Routing.Count(r => !r.Done), comps.Count, stocked > 0) > MaxTransactionItems)
            throw new ArgumentException($"Too many components for one completion transaction ({MaxTransactionItems} items).");
        var productStock = await fulfilment.GetStockAsync(w.Order.ProductId);
        var loc = req.LocationId ?? DefaultFinishedGoodsLocation;
        var txnStart = await fulfilment.NextTxnIdsAsync(comps.Count + (stocked > 0 ? 1 : 0));
        try
        {
            await t.TransactAsync(CompletePlan(t, w, req, req.ScrapReasonId is { } r ? reasons.GetValueOrDefault(r) : null, loc, productStock, comps, actor, now, txnStart), token);
        }
        catch (TransactionCanceledException e)
        {
            throw new ConflictException($"Completion of {w.Order.Number} was rejected by a condition (work order or stock changed meanwhile): " +
                string.Join(", ", e.CancellationReasons?.Where(x => x.Code != "None").Select(x => x.Code).Distinct() ?? []) + ". Reload and retry.");
        }
        var after = (await GetAsync(id))!;
        return new(after, after.Order.State == "Closed on time" ? "closed-on-time" : "closed-late");
    }
}
