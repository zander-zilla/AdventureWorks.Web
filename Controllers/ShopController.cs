// BEFORE BASELINE (demo-only): lets a logged-in demo customer place an order.
// Reads the catalog from and writes Sales.SalesOrderHeader + SalesOrderDetail to the FULL AdventureWorks2022
// database in one transaction (captured by CDC). See Demo/FullDb.cs.
using System.Threading.Tasks;
using AdventureWorks.Web.Demo;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace AdventureWorks.Web.Controllers
{
    [Authorize]
    public class ShopController : Controller
    {
        private readonly FullDb _db;
        public ShopController(FullDb db) { _db = db; }

        private int CustomerId => int.Parse(User.FindFirst("CustomerId").Value);
        private int AddressId => int.Parse(User.FindFirst("AddressId").Value);

        public async Task<IActionResult> Index() => View(await _db.ListProductsAsync());

        [HttpPost]
        [ValidateAntiForgeryToken]
        public async Task<IActionResult> Order(int productId, short quantity = 1)
        {
            if (quantity < 1 || quantity > 20) quantity = 1;
            var (id, name) = await _db.PlaceOrderAsync(CustomerId, AddressId, productId, quantity);
            TempData["Message"] = $"Order {id} placed for {quantity} x {name}.";
            return RedirectToAction(nameof(MyOrders));
        }

        public async Task<IActionResult> MyOrders() => View(await _db.ListOrdersAsync(CustomerId));
    }
}
