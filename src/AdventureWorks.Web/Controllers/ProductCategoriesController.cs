using AdventureWorks.Web.Data;
using Microsoft.AspNetCore.Mvc;

namespace AdventureWorks.Web.Controllers;

/// <summary>Original "ProductCategories" admin screen over the CATALOG item collection (CAT-01/02).
/// LT had one self-referencing category table; the full model has Category -> Subcategory.</summary>
public sealed class ProductCategoriesController(CatalogRepository catalog) : Controller
{
    public async Task<IActionResult> Index() => View(await catalog.GetCategoryTreeAsync());

    public async Task<IActionResult> Details(int id, int? sub)
    {
        var tree = await catalog.GetCategoryTreeAsync();
        var c = tree.FirstOrDefault(x => x.Id == id);
        if (c is null) return NotFound();
        ViewData["Sub"] = sub is { } s ? c.Subcategories.FirstOrDefault(x => x.Id == s) : null;
        ViewData["Products"] = sub is { } s2 ? await catalog.GetProductsBySubcategoryAsync(s2) : null;
        return View(c);
    }

    public async Task<IActionResult> Create() { ViewData["Tree"] = await catalog.GetCategoryTreeAsync(); return View(); }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Create(string name, int? parentId)
    {
        if (string.IsNullOrWhiteSpace(name)) { ViewData["Tree"] = await catalog.GetCategoryTreeAsync(); ModelState.AddModelError("name", "Required"); return View(); }
        if (parentId is { } p) { var sid = await catalog.SaveSubcategoryAsync(null, p, name.Trim()); return RedirectToAction(nameof(Details), new { id = p, sub = sid }); }
        var id = await catalog.SaveCategoryAsync(null, name.Trim());
        return RedirectToAction(nameof(Details), new { id });
    }

    public async Task<IActionResult> Edit(int id, int? sub)
    {
        var tree = await catalog.GetCategoryTreeAsync();
        var c = tree.FirstOrDefault(x => x.Id == id);
        if (c is null) return NotFound();
        ViewData["Tree"] = tree; ViewData["Sub"] = sub is { } s ? c.Subcategories.FirstOrDefault(x => x.Id == s) : null;
        return View(c);
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Edit(int id, int? sub, string name, int? parentId)
    {
        if (sub is { } s) await catalog.SaveSubcategoryAsync(s, parentId ?? id, name.Trim());
        else await catalog.SaveCategoryAsync(id, name.Trim());
        return RedirectToAction(nameof(Details), new { id = sub is null ? id : parentId ?? id, sub });
    }

    public async Task<IActionResult> Delete(int id, int? sub) { var r = await Details(id, sub); return r is ViewResult v ? View("Details", v.Model) : r; }

    [HttpPost, ActionName("Delete"), ValidateAntiForgeryToken]
    public async Task<IActionResult> DeleteConfirmed(int id, int? sub)
    {
        try { await catalog.DeleteCategoryAsync(id, sub); return RedirectToAction(nameof(Index)); }
        catch (InvalidOperationException e) { TempData["Error"] = e.Message; return RedirectToAction(nameof(Details), new { id, sub }); }
    }
}
