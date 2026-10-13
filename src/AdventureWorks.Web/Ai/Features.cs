using System.Globalization;
using AdventureWorks.Web.Data;
using AdventureWorks.Web.Models;

namespace AdventureWorks.Web.Ai;

/// <summary>C2-6 fact builders: everything the model may say comes from here (DynamoDB reads through the existing repositories).</summary>
public sealed class TriageFacts(SalesRepository sales, FulfilmentRepository fulfilment, PricingRepository pricing, TimeProvider clock)
{
    public static readonly string[] Kinds = ["explain", "approve-note", "backorder-note"];

    public async Task<Dictionary<string, object?>?> BuildAsync(long orderId)
    {
        if (await sales.GetOrderAsync(orderId, consistent: true) is not { } o) return null;
        var now = clock.GetUtcNow().UtcDateTime;
        var since = o.Events.Count > 0 ? o.Events.Max(e => e.At) : o.OrderDate;
        var queue = await fulfilment.QueueAsync(o.Status, null, null, null, null, 50);
        var ages = queue.Items.Select(x => (now - x.OrderDate).TotalDays).OrderBy(x => x).ToList();
        var counts = await fulfilment.CountsAsync();
        var history = await sales.GetOrdersForCustomerAsync(o.CustomerId, null, 20);
        var prior = history.Items.Where(x => x.Id != o.Id && x.OrderDate <= o.OrderDate).ToList();
        string? method = o.ShipMethodName;
        if (method is null && o.ShipMethodId is int sm) method = (await pricing.GetShipMethodsAsync()).FirstOrDefault(m => m.Id == sm)?.Name;
        var f = new Dictionary<string, object?>
        {
            ["order.number"] = o.Number, ["order.status"] = Order.StatusName(o.Status), ["order.status_age_days"] = (int)Math.Floor((now - since).TotalDays),
            ["order.total_due"] = Math.Round(o.TotalDue, 2), ["order.lines"] = o.Lines.Count, ["order.ship_method"] = method ?? "not set", ["order.source"] = o.Source,
            ["queue.count"] = counts.GetValueOrDefault(o.Status), ["queue.median_age_days"] = ages.Count == 0 ? 0 : (int)Math.Floor(ages[ages.Count / 2]),
            ["customer.prior_orders"] = prior.Count, ["customer.last_order_date"] = prior.Count == 0 ? null : prior.Max(x => x.OrderDate).ToString("yyyy-MM-dd"),
        };
        var canShip = true;
        var i = 0;
        foreach (var l in o.Lines)
        {
            i++;
            var st = await fulfilment.GetStockAsync(l.ProductId);
            var shortBy = Math.Max(0, l.Quantity - st.Total);
            if (shortBy > 0) canShip = false;
            f[$"line{i}.product"] = l.Name; f[$"line{i}.qty"] = l.Quantity; f[$"line{i}.stock"] = Math.Round(st.Total); f[$"line{i}.short"] = Math.Round(shortBy);
            f[$"line{i}.reorder_point"] = st.ReorderPoint;
        }
        f["order.can_ship"] = canShip;
        return f;
    }
}
