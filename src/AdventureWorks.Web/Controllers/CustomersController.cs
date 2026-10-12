using AdventureWorks.Web.Data;
using Amazon.DynamoDBv2.Model;
using Microsoft.AspNetCore.Mvc;

namespace AdventureWorks.Web.Controllers;

/// <summary>Original "Customers" admin screen over aw-customer (CUS-02/04/05). Person, store and store-contact customers.</summary>
public sealed class CustomersController(CustomerRepository customers) : Controller
{
    public async Task<IActionResult> Index(string? page) => View(await customers.ListAsync(page));

    public async Task<IActionResult> Details(int id) => await customers.GetCustomerAsync(id) is { } c ? View(c) : NotFound();

    public IActionResult Create() => View();

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Create(string? title, string firstName, string? middleName, string lastName, string email)
    {
        if (string.IsNullOrWhiteSpace(firstName) || string.IsNullOrWhiteSpace(lastName) || string.IsNullOrWhiteSpace(email))
        { ModelState.AddModelError("", "First name, last name and email are required."); return View(); }
        try { var id = await customers.CreateAsync(Blank(title), firstName.Trim(), Blank(middleName), lastName.Trim(), email.Trim()); return RedirectToAction(nameof(Details), new { id }); }
        catch (TransactionCanceledException) { ModelState.AddModelError("", "That email address is already in use."); return View(); }
    }

    public async Task<IActionResult> Edit(int id) => await customers.GetCustomerAsync(id) is { } c ? View(c) : NotFound();

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Edit(int id, string? title, string firstName, string? middleName, string lastName)
    {
        try { await customers.UpdateNameAsync(id, Blank(title), firstName.Trim(), Blank(middleName), lastName.Trim()); }
        catch (InvalidOperationException e) { TempData["Error"] = e.Message; }
        return RedirectToAction(nameof(Details), new { id });
    }

    private static string? Blank(string? s) => string.IsNullOrWhiteSpace(s) ? null : s.Trim();
}
