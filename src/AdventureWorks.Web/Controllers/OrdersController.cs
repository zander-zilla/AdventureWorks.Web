using AdventureWorks.Web.Data;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AdventureWorks.Web.Controllers;

/// <summary>Order history (SAL-03, GSI1 eventual) and order detail (SAL-04; strong right after checkout, D8).</summary>
[Authorize]
public sealed class OrdersController(SalesRepository sales) : AppController
{
    public async Task<IActionResult> Index(string? page)
    {
        var p = await sales.GetOrdersForCustomerAsync(CustomerId, page);
        // GSI1 is eventually consistent: merge the order just placed (read strongly from the base table).
        if (page is null && TempData.Peek("LastOrder") is string ls && long.TryParse(ls, out var last) && p.Items.All(o => o.Id != last) && await sales.GetOrderAsync(last, true) is { } fresh)
            p.Items.Insert(0, fresh);
        return View(p);
    }

    public async Task<IActionResult> Details(long id, bool fresh = false)
    {
        var o = await sales.GetOrderAsync(id, consistent: fresh);
        if (o is null || o.CustomerId != CustomerId) return NotFound();
        if (fresh) TempData["LastOrder"] = id.ToString();
        return View(o);
    }
}
