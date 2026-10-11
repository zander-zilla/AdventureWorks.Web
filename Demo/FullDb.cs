// BEFORE BASELINE (demo-only): data access for the demo shop against the FULL AdventureWorks2022 OLTP database
// (Sales.SalesOrderHeader/Detail, Production.Product, Sales.Customer). The original CRUD screens still use LT.
// Plain ADO.NET so the original LT EF model stays untouched.
using System;
using System.Collections.Generic;
using System.Data;
using System.Data.SqlClient;
using System.Threading.Tasks;
using Microsoft.Extensions.Configuration;

namespace AdventureWorks.Web.Demo
{
    public class ShopProduct { public int ProductId; public string Name; public string ProductNumber; public decimal ListPrice; public string Subcategory; }
    public class ShopOrderLine { public short Qty; public string Product; public decimal LineTotal; }
    public class ShopOrder { public int SalesOrderId; public string SalesOrderNumber; public DateTime OrderDate; public byte Status; public decimal TotalDue; public List<ShopOrderLine> Lines = new List<ShopOrderLine>(); }

    public class FullDb
    {
        // Demo orders are tagged so scripts/reset-demo.sql can remove them.
        public const string DemoComment = "demo-order";
        private readonly string _cs;

        public FullDb(IConfiguration config)
        {
            _cs = config.GetConnectionString("AdventureWorks");
            if (string.IsNullOrEmpty(_cs))
            {
                // Default: same server/credentials as the LT connection, database AdventureWorks2022.
                var b = new SqlConnectionStringBuilder(config.GetConnectionString("sampledbContext")) { InitialCatalog = "AdventureWorks2022" };
                _cs = b.ConnectionString;
            }
        }

        private SqlConnection Open() { var c = new SqlConnection(_cs); c.Open(); return c; }

        public async Task<List<ShopProduct>> ListProductsAsync()
        {
            var list = new List<ShopProduct>();
            using (var c = Open())
            using (var cmd = new SqlCommand(@"SELECT TOP 40 p.ProductID, p.Name, p.ProductNumber, p.ListPrice, s.Name
                FROM Production.Product p LEFT JOIN Production.ProductSubcategory s ON s.ProductSubcategoryID = p.ProductSubcategoryID
                WHERE p.SellEndDate IS NULL AND p.ListPrice > 0
                  AND EXISTS (SELECT 1 FROM Sales.SpecialOfferProduct so WHERE so.ProductID = p.ProductID AND so.SpecialOfferID = 1)
                ORDER BY p.Name", c))
            using (var r = await cmd.ExecuteReaderAsync())
                while (await r.ReadAsync())
                    list.Add(new ShopProduct { ProductId = r.GetInt32(0), Name = r.GetString(1), ProductNumber = r.GetString(2), ListPrice = r.GetDecimal(3), Subcategory = r.IsDBNull(4) ? null : r.GetString(4) });
            return list;
        }

        /// Writes Sales.SalesOrderHeader + one Sales.SalesOrderDetail in a transaction. The table trigger maintains SubTotal.
        public async Task<(int id, string product)> PlaceOrderAsync(int customerId, int addressId, int productId, short qty)
        {
            using (var c = Open())
            using (var tx = c.BeginTransaction())
            {
                decimal price; string name;
                using (var cmd = new SqlCommand("SELECT ListPrice, Name FROM Production.Product WHERE ProductID = @p", c, tx))
                {
                    cmd.Parameters.AddWithValue("@p", productId);
                    using (var r = await cmd.ExecuteReaderAsync())
                    {
                        if (!await r.ReadAsync()) throw new InvalidOperationException("Unknown product");
                        price = r.GetDecimal(0); name = r.GetString(1);
                    }
                }
                int id;
                using (var cmd = new SqlCommand(@"INSERT Sales.SalesOrderHeader
                    (RevisionNumber, OrderDate, DueDate, Status, OnlineOrderFlag, PurchaseOrderNumber, CustomerID,
                     BillToAddressID, ShipToAddressID, ShipMethodID, SubTotal, TaxAmt, Freight, Comment)
                    VALUES (1, SYSUTCDATETIME(), DATEADD(day, 12, SYSUTCDATETIME()), 1, 1, @po, @cust, @addr, @addr, 5, 0, 0, 0, @comment);
                    SELECT CAST(SCOPE_IDENTITY() AS int);", c, tx))
                {
                    cmd.Parameters.AddWithValue("@po", "DEMO-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss"));
                    cmd.Parameters.AddWithValue("@cust", customerId);
                    cmd.Parameters.AddWithValue("@addr", addressId);
                    cmd.Parameters.AddWithValue("@comment", DemoComment);
                    id = (int)await cmd.ExecuteScalarAsync();
                }
                using (var cmd = new SqlCommand(@"INSERT Sales.SalesOrderDetail (SalesOrderID, OrderQty, ProductID, SpecialOfferID, UnitPrice, UnitPriceDiscount)
                    VALUES (@id, @q, @p, 1, @price, 0);", c, tx))
                {
                    cmd.Parameters.AddWithValue("@id", id);
                    cmd.Parameters.AddWithValue("@q", qty);
                    cmd.Parameters.AddWithValue("@p", productId);
                    cmd.Parameters.Add("@price", SqlDbType.Money).Value = price;
                    await cmd.ExecuteNonQueryAsync();
                }
                tx.Commit();
                return (id, name);
            }
        }

        public async Task<List<ShopOrder>> ListOrdersAsync(int customerId)
        {
            var map = new Dictionary<int, ShopOrder>(); var list = new List<ShopOrder>();
            using (var c = Open())
            using (var cmd = new SqlCommand(@"SELECT h.SalesOrderID, h.SalesOrderNumber, h.OrderDate, h.Status, h.TotalDue, d.OrderQty, p.Name, d.LineTotal
                FROM Sales.SalesOrderHeader h JOIN Sales.SalesOrderDetail d ON d.SalesOrderID = h.SalesOrderID
                JOIN Production.Product p ON p.ProductID = d.ProductID
                WHERE h.CustomerID = @c ORDER BY h.OrderDate DESC, h.SalesOrderID DESC, d.SalesOrderDetailID", c))
            {
                cmd.Parameters.AddWithValue("@c", customerId);
                using (var r = await cmd.ExecuteReaderAsync())
                    while (await r.ReadAsync())
                    {
                        var id = r.GetInt32(0);
                        if (!map.TryGetValue(id, out var o))
                        {
                            o = new ShopOrder { SalesOrderId = id, SalesOrderNumber = r.GetString(1), OrderDate = r.GetDateTime(2), Status = r.GetByte(3), TotalDue = r.GetDecimal(4) };
                            map[id] = o; list.Add(o);
                        }
                        o.Lines.Add(new ShopOrderLine { Qty = r.GetInt16(5), Product = r.GetString(6), LineTotal = r.GetDecimal(7) });
                    }
            }
            return list;
        }
    }
}
