using Microsoft.AspNetCore.Mvc;

namespace AdventureWorks.Web.Controllers;

public sealed class HomeController : Controller
{
    public IActionResult About() => View();
    public IActionResult Error() => View();
}
