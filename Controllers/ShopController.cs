// BEFORE BASELINE (demo-only): lets a logged-in demo customer place an order.
// Writes SalesLT.SalesOrderHeader + SalesOrderDetail in one transaction (picked up by CDC).
using System;
using System.Linq;
using System.Threading.Tasks;
using AdventureWorks.Web.Models;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace AdventureWorks.Web.Controllers
{
    [Authorize]
    public class ShopController : Controller
    {
        private readonly sampledbContext _context;
        public ShopController(sampledbContext context) { _context = context; }

        private int CustomerId => int.Parse(User.FindFirst("CustomerId").Value);
        private int AddressId => int.Parse(User.FindFirst("AddressId").Value);

        public async Task<IActionResult> Index()
        {
            var products = await _context.Product.AsNoTracking()
                .Where(p => p.SellEndDate == null && p.ListPrice > 0)
                .OrderBy(p => p.Name).Take(40).ToListAsync();
            return View(products);
        }

        [HttpPost]
        [ValidateAntiForgeryToken]
        public async Task<IActionResult> Order(int productId, short quantity = 1)
        {
            if (quantity < 1 || quantity > 20) quantity = 1;
            var product = await _context.Product.AsNoTracking().FirstOrDefaultAsync(p => p.ProductId == productId);
            if (product == null) return NotFound();

            using (var tx = await _context.Database.BeginTransactionAsync())
            {
                var header = new SalesOrderHeader
                {
                    RevisionNumber = 1,
                    OrderDate = DateTime.UtcNow,
                    DueDate = DateTime.UtcNow.AddDays(12),
                    Status = 1,
                    OnlineOrderFlag = true,
                    CustomerId = CustomerId,
                    ShipToAddressId = AddressId,
                    BillToAddressId = AddressId,
                    ShipMethod = "CARGO TRANSPORT 5",
                    PurchaseOrderNumber = "DEMO-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss"),
                    Comment = "demo-order",
                    Freight = 0m,
                    TaxAmt = 0m,
                    Rowguid = Guid.NewGuid(),
                    ModifiedDate = DateTime.UtcNow,
                };
                _context.SalesOrderHeader.Add(header);
                await _context.SaveChangesAsync();

                _context.SalesOrderDetail.Add(new SalesOrderDetail
                {
                    SalesOrderId = header.SalesOrderId,
                    OrderQty = quantity,
                    ProductId = product.ProductId,
                    UnitPrice = product.ListPrice,
                    UnitPriceDiscount = 0m,
                    Rowguid = Guid.NewGuid(),
                    ModifiedDate = DateTime.UtcNow,
                });
                await _context.SaveChangesAsync();
                tx.Commit();
                TempData["Message"] = $"Order {header.SalesOrderId} placed for {quantity} x {product.Name}.";
            }
            return RedirectToAction(nameof(MyOrders));
        }

        public async Task<IActionResult> MyOrders()
        {
            var id = CustomerId;
            var orders = await _context.SalesOrderHeader.AsNoTracking()
                .Include(h => h.SalesOrderDetail).ThenInclude(d => d.Product)
                .Where(h => h.CustomerId == id)
                .OrderByDescending(h => h.OrderDate).ToListAsync();
            return View(orders);
        }
    }
}
