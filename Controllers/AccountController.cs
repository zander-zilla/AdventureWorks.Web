// BEFORE BASELINE (demo-only): cookie login for seeded demo customers.
using System.Collections.Generic;
using System.Security.Claims;
using System.Threading.Tasks;
using AdventureWorks.Web.Demo;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Mvc;

namespace AdventureWorks.Web.Controllers
{
    public class AccountController : Controller
    {
        [HttpGet]
        public IActionResult Login(string returnUrl = null)
        {
            ViewData["ReturnUrl"] = returnUrl;
            return View(DemoCustomers.All);
        }

        [HttpPost]
        [ValidateAntiForgeryToken]
        public async Task<IActionResult> Login(string email, string password, string returnUrl = null)
        {
            var user = DemoCustomers.Find(email);
            if (user == null || password != DemoCustomers.Password)
            {
                ViewData["Error"] = "Unknown demo user or wrong password.";
                return View(DemoCustomers.All);
            }
            var claims = new List<Claim>
            {
                new Claim(ClaimTypes.Name, user.DisplayName),
                new Claim(ClaimTypes.Email, user.Email),
                new Claim("CustomerId", user.CustomerId.ToString()),
                new Claim("AddressId", user.AddressId.ToString()),
            };
            var identity = new ClaimsIdentity(claims, CookieAuthenticationDefaults.AuthenticationScheme);
            await HttpContext.SignInAsync(CookieAuthenticationDefaults.AuthenticationScheme, new ClaimsPrincipal(identity));
            return LocalRedirect(Url.IsLocalUrl(returnUrl) ? returnUrl : "/Shop");
        }

        [HttpPost]
        [ValidateAntiForgeryToken]
        public async Task<IActionResult> Logout()
        {
            await HttpContext.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
            return RedirectToAction("Index", "ProductCategories");
        }
    }
}
