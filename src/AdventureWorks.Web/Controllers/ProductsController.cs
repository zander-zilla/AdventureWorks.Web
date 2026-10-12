using AdventureWorks.Web.Data;
using AdventureWorks.Web.Models;
using Amazon.DynamoDBv2.Model;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Rendering;

namespace AdventureWorks.Web.Controllers;

/// <summary>Original admin screen, now over aw-catalog (CAT-04/05/06/07). Category -> subcategory (full model).</summary>
public sealed class ProductsController(CatalogRepository catalog) : Controller
{
    public async Task<IActionResult> Index(string? page, string? q)
    {
        ViewData["q"] = q;
        if (!string.IsNullOrWhiteSpace(q)) return View(new ProductPage(await catalog.SearchByPrefixAsync(q, 100), null));
        return View(await catalog.ListProductsAsync(page));
    }

    public async Task<IActionResult> Details(int id) => await catalog.GetProductAsync(id) is { } p ? View(p) : NotFound();

    public async Task<IActionResult> Create() { await Lists(null); return View(new Product()); }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Create(Product p)
    {
        if (!Valid(p)) { await Lists(p.SubcategoryId); return View(p); }
        try { var id = await catalog.CreateProductAsync(p); return RedirectToAction(nameof(Details), new { id }); }
        catch (TransactionCanceledException) { ModelState.AddModelError("", "Name or product number already exists."); await Lists(p.SubcategoryId); return View(p); }
    }

    public async Task<IActionResult> Edit(int id)
    {
        var p = await catalog.GetProductAsync(id);
        if (p is null) return NotFound();
        await Lists(p.SubcategoryId); return View(p);
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Edit(int id, Product p)
    {
        p.Id = id;
        if (!Valid(p)) { await Lists(p.SubcategoryId); return View(p); }
        try { await catalog.UpdateProductAsync(p); return RedirectToAction(nameof(Details), new { id }); }
        catch (TransactionCanceledException)
        { ModelState.AddModelError("", "Someone else changed this product, or the new name/number is taken. Reload and try again."); await Lists(p.SubcategoryId); return View(p); }
    }

    public async Task<IActionResult> Delete(int id) => await catalog.GetProductAsync(id) is { } p ? View(p) : NotFound();

    [HttpPost, ActionName("Delete"), ValidateAntiForgeryToken]
    public async Task<IActionResult> DeleteConfirmed(int id)
    {
        try { await catalog.DeleteProductAsync(id); return RedirectToAction(nameof(Index)); }
        catch (InvalidOperationException e) { TempData["Error"] = e.Message; return RedirectToAction(nameof(Delete), new { id }); }
    }

    private bool Valid(Product p)
    {
        if (string.IsNullOrWhiteSpace(p.Name)) ModelState.AddModelError(nameof(p.Name), "Required");
        if (string.IsNullOrWhiteSpace(p.ProductNumber)) ModelState.AddModelError(nameof(p.ProductNumber), "Required");
        if (p.ListPrice < 0) ModelState.AddModelError(nameof(p.ListPrice), "Must be >= 0");
        return ModelState.IsValid;
    }

    private async Task Lists(int? selected)
    {
        var tree = await catalog.GetCategoryTreeAsync();
        ViewData["Subcategories"] = tree.SelectMany(c => c.Subcategories.Select(s => new SelectListItem($"{c.Name} / {s.Name}", s.Id.ToString(), s.Id == selected))).ToList();
    }
}
