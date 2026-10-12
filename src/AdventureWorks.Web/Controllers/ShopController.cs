using AdventureWorks.Web.Data;
using Microsoft.AspNetCore.Mvc;

namespace AdventureWorks.Web.Controllers;

/// <summary>Shopper pages: browse (CAT-01/03), product detail with 6-culture descriptions (CAT-04, D9), name-prefix search (CAT-12, D2).</summary>
public sealed class ShopController(CatalogRepository catalog) : AppController
{
    public async Task<IActionResult> Index() => View(await catalog.GetCategoryTreeAsync());

    public async Task<IActionResult> Subcategory(int id)
    {
        var sub = await catalog.GetSubcategoryAsync(id);
        if (sub is null) return NotFound();
        ViewData["Sub"] = sub;
        return View(await catalog.GetProductsBySubcategoryAsync(id));
    }

    public async Task<IActionResult> Product(int id, string? culture)
    {
        var p = await catalog.GetProductAsync(id);
        if (p is null) return NotFound();
        culture = culture ?? Request.Cookies["aw.culture"] ?? "en";
        if (!CatalogRepository.Cultures.Contains(culture)) culture = "en";
        Response.Cookies.Append("aw.culture", culture);
        ViewData["Culture"] = culture;
        ViewData["Descriptions"] = p.ModelId is { } m ? await catalog.GetDescriptionsAsync(m) : new List<Models.ModelDescription>();
        return View(p);
    }

    public async Task<IActionResult> Search(string? q)
    {
        ViewData["q"] = q;
        return View(string.IsNullOrWhiteSpace(q) ? new() : await catalog.SearchByPrefixAsync(q));
    }
}
