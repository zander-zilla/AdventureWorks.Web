using System.Security.Claims;
using Microsoft.AspNetCore.Mvc;

namespace AdventureWorks.Web.Controllers;

public abstract class AppController : Controller
{
    protected int CustomerId => int.Parse(User.FindFirstValue("customer_id")!);
    protected string Email => User.FindFirstValue(ClaimTypes.Email)!;
}
