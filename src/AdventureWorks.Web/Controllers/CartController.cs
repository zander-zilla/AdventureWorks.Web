using AdventureWorks.Web.Data;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AdventureWorks.Web.Controllers;

/// <summary>Cart for logged-in customers only (D3, SAL-01) and checkout (SAL-02).</summary>
[Authorize]
public sealed class CartController(SalesRepository sales, CatalogRepository catalog, CustomerRepository customers) : AppController
{
    public async Task<IActionResult> Index() => View(await sales.GetCartAsync(CustomerId));

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Add(int productId, int quantity = 1)
    {
        var p = await catalog.GetProductAsync(productId);
        if (p is null || !p.Active) return NotFound();
        var cart = await sales.GetCartAsync(CustomerId);
        if (cart.Count >= SalesRepository.MaxOrderLines && cart.All(c => c.ProductId != productId))
        { TempData["Error"] = $"A cart can hold at most {SalesRepository.MaxOrderLines} products."; return RedirectToAction(nameof(Index)); }
        await sales.AddToCartAsync(CustomerId, p, Math.Clamp(quantity, 1, 99));
        TempData["Message"] = $"Added {p.Name} to your cart.";
        return RedirectToAction(nameof(Index));
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Update(int productId, int quantity)
    {
        await sales.SetQuantityAsync(CustomerId, productId, Math.Clamp(quantity, 0, 99));
        return RedirectToAction(nameof(Index));
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Checkout()
    {
        var c = await customers.GetCustomerAsync(CustomerId);
        if (c is null) return Forbid();
        try
        {
            var o = await sales.CheckoutAsync(CustomerId, c, Email);
            TempData["Message"] = $"Order {o.Number} placed.";
            return RedirectToAction("Details", "Orders", new { id = o.Id, fresh = true });
        }
        catch (InvalidOperationException e) { TempData["Error"] = e.Message; return RedirectToAction(nameof(Index)); }
    }
}
