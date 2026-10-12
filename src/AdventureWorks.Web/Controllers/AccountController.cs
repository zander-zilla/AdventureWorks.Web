using System.Security.Claims;
using AdventureWorks.Web.Data;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Mvc;

namespace AdventureWorks.Web.Controllers;

/// <summary>Demo login against aw-customer (CUS-01, strong reads). Same 5 demo customers and shared password as the before app.</summary>
public sealed class AccountController(CustomerRepository customers, DemoOptions demo) : Controller
{
    [HttpGet]
    public IActionResult Login(string? returnUrl) { ViewData["ReturnUrl"] = returnUrl; ViewData["Emails"] = demo.Emails; return View(); }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Login(string email, string password, string? returnUrl)
    {
        ViewData["Emails"] = demo.Emails;
        var allowed = demo.Emails.Contains(email?.Trim() ?? "", StringComparer.OrdinalIgnoreCase) && password == demo.Password;
        var login = allowed ? await customers.FindLoginAsync(email!) : null;
        if (login is null) { ViewData["Error"] = "Unknown demo customer or wrong password."; return View(); }
        var id = new ClaimsIdentity([
            new Claim(ClaimTypes.Name, login.DisplayName), new Claim(ClaimTypes.Email, login.Email),
            new Claim("customer_id", login.CustomerId.ToString()), new Claim("person_id", login.PersonId.ToString()),
        ], CookieAuthenticationDefaults.AuthenticationScheme);
        await HttpContext.SignInAsync(new ClaimsPrincipal(id));
        return LocalRedirect(Url.IsLocalUrl(returnUrl) ? returnUrl! : "/");
    }

    [HttpPost, ValidateAntiForgeryToken]
    public async Task<IActionResult> Logout() { await HttpContext.SignOutAsync(); return RedirectToAction("Index", "Shop"); }
}
