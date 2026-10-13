using System.Globalization;
using System.Text;

namespace AdventureWorks.Web.Ai;

/// <summary>Deterministic answers for the mocked model (C2-6). Only fact values are used, always with their [key].</summary>
public static class MockTemplates
{
    static string S(Dictionary<string, object?> f, string k) => Convert.ToString(f.GetValueOrDefault(k), CultureInfo.InvariantCulture) ?? "";
    static decimal N(Dictionary<string, object?> f, string k) => decimal.TryParse(S(f, k), NumberStyles.Number, CultureInfo.InvariantCulture, out var d) ? d : 0;
    static string I(decimal d) => Math.Round(d).ToString("0", CultureInfo.InvariantCulture);
    static IEnumerable<int> Lines(Dictionary<string, object?> f) => Enumerable.Range(1, (int)N(f, "order.lines")).Where(i => f.ContainsKey($"line{i}.product"));

    public static string Render(string kind, Dictionary<string, object?> f) => kind switch
    {
        "triage-explain" => TriageExplain(f),
        "triage-approve-note" => $"Approved {S(f, "order.number")} [order.number]: all {S(f, "order.lines")} lines in stock [order.can_ship], {N(f, "order.total_due"):0.00} due [order.total_due], ships via {S(f, "order.ship_method")} [order.ship_method].",
        "triage-backorder-note" => TriageBackorder(f),
        "reorder-explain" => $"Suggest {S(f, "suggested.qty")} [suggested.qty]: forecast demand over the {S(f, "forecast.lead_time_days")}-day lead time is {I(N(f, "forecast.lead_time_demand"))} [forecast.lead_time_demand] against the reorder rule's {S(f, "rule.qty")} [rule.qty]. " +
            $"The last 3 months sold {S(f, "history.last3")} units vs {S(f, "history.same3_last_year")} a year earlier [history.last3] [history.same3_last_year].",
        "po-email" => PoEmail(f),
        "watchdog-explain" => $"{S(f, "cause.title")} [cause.key]. Replication lag is {S(f, "status.lag_last_ms")} ms (p50 {S(f, "status.lag_p50_ms")}, max {S(f, "status.lag_max_ms")}) [status.lag_last_ms] and {S(f, "status.dlq")} messages wait in the dead-letter queue [status.dlq]. " +
            $"Next step: {S(f, "cause.next_step")} [cause.next_step] (runbook: {S(f, "cause.runbook")}) [cause.runbook].",
        "shop-reply" => ShopReply(f),
        _ => "No template for this request [kind].",
    };

    static string TriageExplain(Dictionary<string, object?> f)
    {
        var reasons = new List<string>();
        foreach (var i in Lines(f))
            if (N(f, $"line{i}.short") > 0) reasons.Add($"line {i} {S(f, $"line{i}.product")} has {I(N(f, $"line{i}.stock"))} in stock but needs {S(f, $"line{i}.qty")} [line{i}.short]");
        decimal age = N(f, "order.status_age_days"), median = N(f, "queue.median_age_days");
        if (age >= 2 && age > 2 * median) reasons.Add($"it has been {S(f, "order.status")} for {I(age)} days vs a queue median of {I(median)} days [order.status_age_days] [queue.median_age_days]");
        if (N(f, "customer.prior_orders") == 0) reasons.Add("this is the customer's first order [customer.prior_orders]");
        return reasons.Count == 0
            ? $"Looks fine: every line is in stock [order.can_ship] and the order is {S(f, "order.status")} [order.status]."
            : "Needs attention: " + string.Join("; ", reasons) + ".";
    }

    static string TriageBackorder(Dictionary<string, object?> f)
    {
        var shorts = Lines(f).Where(i => N(f, $"line{i}.short") > 0)
            .Select(i => $"{S(f, $"line{i}.product")} short by {I(N(f, $"line{i}.short"))} (in stock {I(N(f, $"line{i}.stock"))}, ordered {S(f, $"line{i}.qty")}) [line{i}.short]").ToList();
        return shorts.Count == 0
            ? $"Backordered {S(f, "order.number")} [order.number] at the clerk's request; all lines are currently in stock [order.can_ship]."
            : $"Backordered {S(f, "order.number")} [order.number]: {string.Join("; ", shorts)}. Ship once stock arrives.";
    }

    static string PoEmail(Dictionary<string, object?> f)
    {
        var sb = new StringBuilder();
        sb.Append($"Subject: Purchase order {S(f, "po.number")} [po.number]\n\nDear {S(f, "vendor.contact")} [vendor.contact],\n\nplease confirm our purchase order {S(f, "po.number")} to {S(f, "vendor.name")} [vendor.name]:\n");
        for (var i = 1; f.ContainsKey($"line{i}.product"); i++)
            sb.Append($"- {S(f, $"line{i}.qty")} x {S(f, $"line{i}.product")} at {N(f, $"line{i}.unit_price"):0.00} [line{i}.qty]\n");
        sb.Append($"\nRequested delivery by {S(f, "po.need_by")} [po.need_by]. Order total {N(f, "po.total"):0.00} [po.total].\n\nKind regards,\n{S(f, "buyer.name")} [buyer.name]\nAdventure Works Cycles, purchasing");
        return sb.ToString();
    }

    static string ShopReply(Dictionary<string, object?> f)
    {
        var n = (int)N(f, "search.count");
        var sb = new StringBuilder();
        if (f.ContainsKey("search.query"))
        {
            if (n == 0) sb.Append($"I found nothing matching \"{S(f, "search.query")}\" [search.query]. Try other words, for example a category or a colour.");
            else sb.Append($"Here are {n} matches for \"{S(f, "search.query")}\" [search.count]: " +
                string.Join(", ", Enumerable.Range(1, Math.Min(n, 3)).Select(i => S(f, $"p{i}.name"))) + " [p1.name].");
        }
        var also = Enumerable.Range(1, 3).Where(i => f.ContainsKey($"also{i}.name")).Select(i => S(f, $"also{i}.name")).ToList();
        if (also.Count > 0) sb.Append($" Customers who bought {S(f, "also.for")} also bought {string.Join(", ", also)} [also.for].");
        return sb.Length == 0 ? "Ask me about bikes, components, clothing or accessories [shop]." : sb.ToString().Trim();
    }
}
