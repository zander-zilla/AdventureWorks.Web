using System.Globalization;
using Amazon.DynamoDBv2.Model;
using AdventureWorks.Web.Data;

namespace AdventureWorks.Web.Ai;

public sealed record DemandMonth(string Month, int Qty, int Orders);
public sealed record ForecastPoint(string Month, double Qty);
/// <summary>INV-07 forecast. Method: seasonal-naive with trend when 12+ months of history, else the 3-month mean.</summary>
public sealed record DemandForecast(int ProductId, List<DemandMonth> History, List<ForecastPoint> Next, double Monthly, double Baseline, double Growth,
    int Last3, int Same3LastYear, int LeadTimeDays, double LeadTimeDemand, string Method);
public sealed record SmartSuggestion(ReorderSuggestion Rule, DemandForecast Forecast, int SmartQty, string Reason);

/// <summary>Pure forecast maths (golden-tested; the warehouse backtest uses the same formula).</summary>
public static class Forecast
{
    public static string AddMonths(string ym, int n) =>
        DateTime.ParseExact(ym + "-01", "yyyy-MM-dd", CultureInfo.InvariantCulture).AddMonths(n).ToString("yyyy-MM", CultureInfo.InvariantCulture);

    /// <summary>Monthly series with gaps filled by zero, oldest first.</summary>
    public static List<DemandMonth> Fill(IEnumerable<DemandMonth> raw)
    {
        var by = raw.GroupBy(m => m.Month).ToDictionary(g => g.Key, g => new DemandMonth(g.Key, g.Sum(x => x.Qty), g.Sum(x => x.Orders)));
        if (by.Count == 0) return [];
        var keys = by.Keys.OrderBy(k => k, StringComparer.Ordinal).ToList();
        var res = new List<DemandMonth>();
        for (var m = keys[0]; string.CompareOrdinal(m, keys[^1]) <= 0; m = AddMonths(m, 1)) res.Add(by.GetValueOrDefault(m) ?? new DemandMonth(m, 0, 0));
        return res;
    }

    /// <summary>One-step forecast for the month after <paramref name="h"/>: f = 0.5·y(m−12)·g + 0.5·mean(last 3),
    /// g = sum(last 3) / sum(same 3 a year earlier), clamped to 0.5..2. Fewer than 12 months: mean(last 3).</summary>
    public static (double F, double G, string Method) Step(IReadOnlyList<double> h)
    {
        if (h.Count == 0) return (0, 1, "no history");
        var n = h.Count; var k = Math.Min(3, n);
        var mean3 = h.Skip(n - k).Average();
        if (n < 12) return (mean3, 1, "3-month mean (less than 12 months of history)");
        var last3 = h.Skip(n - 3).Sum(); var prev3 = n >= 15 ? h.Skip(n - 15).Take(3).Sum() : 0;
        var g = prev3 <= 0 ? 1 : Math.Clamp(last3 / prev3, 0.5, 2);
        return (0.5 * h[n - 12] * g + 0.5 * mean3, g, "seasonal naive with trend (0.5·last year·growth + 0.5·3-month mean)");
    }

    public static DemandForecast Compute(int productId, IEnumerable<DemandMonth> raw, int leadTimeDays, int horizon = 3)
    {
        var hist = Fill(raw);
        var y = hist.Select(m => (double)m.Qty).ToList();
        var (f1, g, method) = Step(y);
        var next = new List<ForecastPoint>();
        var work = new List<double>(y);
        var last = hist.Count > 0 ? hist[^1].Month : DateTime.UtcNow.ToString("yyyy-MM", CultureInfo.InvariantCulture);
        for (var i = 1; i <= horizon; i++)
        {
            var (f, _, _) = Step(work);
            f = Math.Round(Math.Max(0, f), 1);
            next.Add(new ForecastPoint(AddMonths(last, i), f)); work.Add(f);
        }
        var monthly = Math.Round(Math.Max(0, f1), 1);
        var baseline = y.Count == 0 ? 0 : Math.Round(y.Skip(Math.Max(0, y.Count - 12)).Average(), 1);
        var last3 = (int)y.Skip(Math.Max(0, y.Count - 3)).Sum();
        var same3 = y.Count >= 15 ? (int)y.Skip(y.Count - 15).Take(3).Sum() : 0;
        var lead = Math.Max(1, leadTimeDays);
        return new DemandForecast(productId, hist, next, monthly, baseline, Math.Round(g, 2), last3, same3, lead, Math.Round(monthly * lead / 30.0, 1), method);
    }

    /// <summary>Smart quantity: cover forecast demand over the lead time on top of safety stock, net of stock and open POs,
    /// within the best vendor's min / max order quantity. No vendor: 0 (made in house, C2-4).</summary>
    public static SmartSuggestion Smart(ReorderSuggestion rule, DemandForecast f)
    {
        var target = rule.SafetyStockLevel + f.LeadTimeDemand;
        var need = (int)Math.Max(0, Math.Ceiling(target - (double)rule.StockQty - rule.OnOrder));
        if (rule.Vendor is not { } v) return new(rule, f, 0, rule.Note ?? "No active vendor");
        if (need == 0) return new(rule, f, 0, "Forecast demand over the lead time is covered by stock and open orders");
        var min = Math.Max(1, v.MinOrderQty); var qty = Math.Clamp(need, min, Math.Max(min, v.MaxOrderQty));
        var why = qty > rule.SuggestedQty ? "Forecast demand is above the reorder rule" : qty < rule.SuggestedQty ? "Forecast demand is below the reorder rule" : "Forecast agrees with the reorder rule";
        if (qty < need) why += $"; capped at the vendor maximum ({v.MaxOrderQty})"; else if (qty > need) why += $"; raised to the vendor minimum ({v.MinOrderQty})";
        return new(rule, f, qty, why);
    }
}

/// <summary>DEMAND#&lt;pid&gt; / M#yyyy-MM items in aw-inventory written by scripts/loader/derive_ai.py.</summary>
public sealed class DemandRepository(DynamoTables t)
{
    public async Task<List<DemandMonth>> HistoryAsync(int productId)
    {
        var items = await t.For(DynamoTables.Inventory).QueryAll(new QueryRequest
        {
            TableName = t.Name(DynamoTables.Inventory), KeyConditionExpression = "PK = :p AND begins_with(SK, :m)",
            ExpressionAttributeValues = new() { [":p"] = Av.S($"DEMAND#{productId}"), [":m"] = Av.S("M#") },
        });
        return items.Select(i => new DemandMonth(i.Str("month") ?? i["SK"].S[2..], i.Int("qty") ?? 0, i.Int("orders") ?? 0)).ToList();
    }
}

/// <summary>Smart reorder (forecast + vendor rules) and the reorder / PO e-mail facts.</summary>
public sealed class ReorderFacts(ProcurementRepository procurement, DemandRepository demand)
{
    public async Task<DemandForecast> ForecastAsync(int productId, int leadTimeDays) => Forecast.Compute(productId, await demand.HistoryAsync(productId), leadTimeDays);

    public async Task<List<SmartSuggestion>> SmartAsync()
    {
        var rules = await procurement.SuggestionsAsync();
        var res = new List<SmartSuggestion>();
        foreach (var chunk in rules.Chunk(10))
            res.AddRange(await Task.WhenAll(chunk.Select(async r => Forecast.Smart(r, await ForecastAsync(r.ProductId, r.Vendor?.AverageLeadTime ?? 30)))));
        return res;
    }

    public async Task<Dictionary<string, object?>?> ExplainAsync(int productId)
    {
        var rule = (await procurement.SuggestionsAsync()).FirstOrDefault(r => r.ProductId == productId);
        if (rule is null) return null;
        var s = Forecast.Smart(rule, await ForecastAsync(productId, rule.Vendor?.AverageLeadTime ?? 30));
        return new()
        {
            ["product.name"] = rule.Name, ["product.stock"] = Math.Round(rule.StockQty), ["product.on_order"] = rule.OnOrder, ["product.safety_stock"] = rule.SafetyStockLevel,
            ["suggested.qty"] = s.SmartQty, ["suggested.reason"] = s.Reason, ["rule.qty"] = rule.SuggestedQty, ["vendor.name"] = rule.Vendor?.VendorName,
            ["forecast.monthly"] = s.Forecast.Monthly, ["forecast.lead_time_days"] = s.Forecast.LeadTimeDays, ["forecast.lead_time_demand"] = s.Forecast.LeadTimeDemand,
            ["forecast.method"] = s.Forecast.Method, ["forecast.growth"] = s.Forecast.Growth, ["history.last3"] = s.Forecast.Last3, ["history.same3_last_year"] = s.Forecast.Same3LastYear,
            ["history.baseline"] = s.Forecast.Baseline,
        };
    }

    public async Task<Dictionary<string, object?>?> PoEmailAsync(int poId, string buyerName)
    {
        if (await procurement.GetOrderAsync(poId) is not { } po) return null;
        var v = await procurement.GetVendorAsync(po.VendorId);
        var lead = v?.Products.Where(p => po.Lines.Any(l => l.ProductId == p.ProductId)).Select(p => p.AverageLeadTime).DefaultIfEmpty(0).Max() ?? 0;
        var due = po.Lines.Select(l => l.DueDate).Where(d => d is not null).DefaultIfEmpty(po.OrderDate.AddDays(Math.Max(lead, 1))).Max();
        var f = new Dictionary<string, object?>
        {
            ["po.number"] = po.Number, ["po.status"] = po.StatusText, ["vendor.name"] = po.VendorName ?? v?.Vendor.Name,
            ["vendor.contact"] = v?.Contacts.FirstOrDefault(c => !string.IsNullOrWhiteSpace(c.Name))?.Name ?? "Sales team",
            ["po.need_by"] = due?.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture), ["po.total"] = Math.Round(po.TotalDue, 2),
            ["buyer.name"] = po.EmployeeName ?? buyerName,
        };
        var i = 0;
        foreach (var l in po.Lines)
        {
            i++; f[$"line{i}.product"] = l.ProductName; f[$"line{i}.qty"] = l.OrderQty; f[$"line{i}.unit_price"] = Math.Round(l.UnitPrice, 2);
        }
        return f;
    }
}
