using System.Security.Claims;
using AdventureWorks.Web.Ai;
using AdventureWorks.Web.Data;
using AdventureWorks.Web.Models;
using Amazon.DynamoDBv2.Model;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;

namespace AdventureWorks.Web.Api;

public sealed record MeDto(bool Authenticated, string? Name, string? Email, int? CustomerId, string[] Roles);
public sealed record LoginRequest(string Email, string Password);
public sealed record CartItemRequest(int ProductId, int Quantity);
public sealed record QuantityRequest(int Quantity);
public sealed record CheckoutRequest(int? ShipMethodId);
public sealed record ReviewRequest(int Rating, string Comments);
public sealed record TransitionRequest(long Version, int? ShipMethodId, string? TrackingNumber);
public sealed record BulkItem(long Id, long Version);
public sealed record BulkRequest(List<BulkItem> Orders);
public sealed record BulkResult(long Id, bool Ok, string Message);
public sealed record PriceRequest(decimal ListPrice, long Version);
public sealed record ProductDetail(Product Product, List<OfferInfo> Offers, List<CatalogRepository.PricePoint> PriceHistory);
public sealed record LineStock(int ProductId, decimal OnHand, int ReorderPoint, List<StockAt> Locations);
public sealed record StockAt(int LocationId, string? Name, decimal Quantity);
public sealed record BackOfficeOrder(Order Order, string StatusText, string[] Actions, List<LineStock> Stock);
public sealed record StatusCount(int Status, string Text, int Count);

/// <summary>
/// Chapter 2 JSON API (ADR 0010): minimal APIs under /api/v2, same cookie auth as the Chapter 1 Razor app (removed in C2-3), problem+json errors,
/// 401/403 instead of login redirects, and a CSRF guard (custom header on unsafe methods). C2-2 adds shop (cart, quote,
/// checkout, orders, reviews) and back office (orders queue + transitions, change feed, price edit) with roles.
/// Every endpoint declares its response type so /api/v2/openapi.json drives the generated SPA client (src/web/src/api/schema.d.ts).
/// </summary>
public static class V2
{
    public const string ClientHeader = "X-AW-Client";
    public const string CustomerPolicy = "customer";
    public const string FulfilmentPolicy = "fulfilment";
    public const string CatalogAdminPolicy = "catalog-admin";
    public const string FulfilmentRole = "Fulfilment", CatalogAdminRole = "CatalogAdmin", CustomerRole = "Customer";
    // C2-3 procurement: Buyer (vendors, suggestions, create + receive POs) and PurchasingManager (approve / reject; also buys).
    public const string ProcurementPolicy = "procurement", PurchasingManagerPolicy = "purchasing-manager", StaffPolicy = "staff";
    public const string BuyerRole = "Buyer", PurchasingManagerRole = "PurchasingManager";
    // C2-4 production floor: ProductionSupervisor (create / record / complete work orders). BOM and KPIs are open to all staff.
    public const string ProductionPolicy = "production", ProductionRole = "ProductionSupervisor";
    public static readonly string[] StaffRoles = [FulfilmentRole, CatalogAdminRole, BuyerRole, PurchasingManagerRole, ProductionRole];

    public static bool IsApi(PathString p) => p.StartsWithSegments("/api");

    private static int CustomerId(ClaimsPrincipal u) => int.Parse(u.FindFirstValue("customer_id")!);
    private static string Actor(ClaimsPrincipal u) => u.FindFirstValue(ClaimTypes.Email) ?? u.Identity?.Name ?? "unknown";
    private static StaffUser Staff(ClaimsPrincipal u) => new(Actor(u), u.Identity?.Name ?? Actor(u),
        int.TryParse(u.FindFirstValue("employee_id"), out var e) ? e : null);
    private static IResult AiOff() => Results.Problem(title: "The AI layer is off (enable_ai = false).", statusCode: 404);
    /// <summary>Budget key: the signed-in user, else a per-browser cookie.</summary>
    private static string AiSession(HttpContext h)
    {
        if (h.User.Identity?.IsAuthenticated == true) return "u:" + Actor(h.User);
        if (h.Request.Cookies["aw_ai"] is { Length: 32 } c) return "c:" + c;
        var id = Guid.NewGuid().ToString("N");
        h.Response.Cookies.Append("aw_ai", id, new CookieOptions { HttpOnly = true, SameSite = SameSiteMode.Lax, Secure = h.Request.IsHttps });
        return "c:" + id;
    }
    private static string? Token(HttpContext h) => h.Request.Headers["Idempotency-Key"].FirstOrDefault() is { Length: > 0 and <= 36 } k ? k : null;

    /// <summary>Domain exceptions -> problem+json (400 validation, 404, 409 conflict / failed condition).</summary>
    private static async Task<IResult> Guard(Func<Task<IResult>> f)
    {
        try { return await f(); }
        catch (KeyNotFoundException) { return Results.Problem(title: "Not found", statusCode: 404); }
        catch (ConflictException e) { return Results.Problem(title: e.Message, statusCode: 409); }
        catch (ArgumentException e) { return Results.Problem(title: e.Message, statusCode: 400); }
        catch (InvalidOperationException e) { return Results.Problem(title: e.Message, statusCode: 409); }
        catch (TransactionCanceledException) { return Results.Problem(title: "The data changed meanwhile (condition failed). Reload and retry.", statusCode: 409); }
        catch (ConditionalCheckFailedException) { return Results.Problem(title: "The data changed meanwhile (condition failed). Reload and retry.", statusCode: 409); }
    }

    public static RouteGroupBuilder MapApiV2(this IEndpointRouteBuilder app)
    {
        var g = app.MapGroup("/api/v2").WithTags("v2");
        g.AddEndpointFilter(async (ctx, next) =>
        {
            // CSRF: browsers cannot send a custom header cross-site without a CORS preflight, which this API never allows.
            var req = ctx.HttpContext.Request;
            if (!HttpMethods.IsGet(req.Method) && !HttpMethods.IsHead(req.Method) && !req.Headers.ContainsKey(ClientHeader))
                return Results.Problem(title: $"Missing {ClientHeader} header", statusCode: StatusCodes.Status400BadRequest);
            return await next(ctx);
        });

        g.MapGet("/me", (ClaimsPrincipal u) => Me(u)).WithName("me");

        g.MapPost("/auth/login", async (LoginRequest body, HttpContext http, CustomerRepository customers, DemoOptions demo) =>
        {
            var email = body.Email?.Trim() ?? "";
            if (body.Password != demo.Password) return Results.Problem(title: "Unknown demo customer or wrong password", statusCode: StatusCodes.Status401Unauthorized);
            ClaimsPrincipal? principal = null;
            if (demo.Staff.FirstOrDefault(s => s.Email.Equals(email, StringComparison.OrdinalIgnoreCase)) is { } staff) principal = StaffPrincipal(staff);
            else if (demo.Emails.Contains(email, StringComparer.OrdinalIgnoreCase) && await customers.FindLoginAsync(email) is { } login) principal = Principal(login);
            if (principal is null) return Results.Problem(title: "Unknown demo customer or wrong password", statusCode: StatusCodes.Status401Unauthorized);
            await http.SignInAsync(principal);
            return Results.Ok(Me(principal));
        }).WithName("login").Produces<MeDto>().ProducesProblem(401);

        g.MapPost("/auth/logout", async (HttpContext http) => { await http.SignOutAsync(); return Results.NoContent(); }).WithName("logout").Produces(204);

        // ------------------------------------------------------------ catalog (CAT-01/03/04/06/10/11)
        g.MapGet("/products", async (CatalogRepository c, string? next, int? pageSize) =>
            Results.Ok(await c.ListProductsAsync(next, Math.Clamp(pageSize ?? 25, 1, 100)))).WithName("listProducts").Produces<ProductPage>();
        g.MapGet("/products/{id:int}", async (int id, CatalogRepository c) => await c.GetProductAsync(id) is { } p ? Results.Ok(p) : Results.NotFound())
            .WithName("getProduct").Produces<Product>().Produces(404);
        g.MapGet("/products/{id:int}/detail", async (int id, CatalogRepository c, PricingRepository pr) =>
            await c.GetProductAsync(id) is { } p ? Results.Ok(new ProductDetail(p, await pr.GetOffersAsync(id), await c.GetPriceHistoryAsync(id))) : Results.NotFound())
            .WithName("getProductDetail").Produces<ProductDetail>().Produces(404);
        g.MapGet("/categories", async (CatalogRepository c) => Results.Ok(await c.GetCategoryTreeAsync())).WithName("listCategories").Produces<List<Category>>();
        g.MapGet("/subcategories/{id:int}/products", async (int id, CatalogRepository c) => Results.Ok(await c.GetProductsBySubcategoryAsync(id)))
            .WithName("listSubcategoryProducts").Produces<List<Product>>();
        g.MapGet("/products/{id:int}/reviews", async (int id, CatalogRepository c) => Results.Ok(await c.GetReviewsAsync(id)))
            .WithName("listReviews").Produces<List<CatalogRepository.Review>>();
        g.MapPost("/products/{id:int}/reviews", (int id, ReviewRequest body, ClaimsPrincipal u, CatalogRepository c, FulfilmentRepository f, TimeProvider clock) => Guard(async () =>
        {
            var now = clock.GetUtcNow().UtcDateTime; now = now.AddTicks(-(now.Ticks % TimeSpan.TicksPerSecond));
            try
            {
                var r = await c.AddReviewAsync(id, CustomerId(u), u.Identity!.Name!, Actor(u), body.Rating, body.Comments, now);
                await f.AppendFeedAsync(now, "review.added", $"product {id}", Actor(u),
                    [$"aw-catalog {Keys.Product(id)} {Keys.Review(now, r.Id)} rating {r.Rating} (ProductReview -> stg.product_review)"]);
                return Results.Created($"/api/v2/products/{id}/reviews", r);
            }
            catch (TransactionCanceledException) { return Results.Problem(title: "You have already reviewed this product.", statusCode: 409); }
        })).RequireAuthorization(CustomerPolicy).WithName("addReview").Produces<CatalogRepository.Review>(201).ProducesProblem(400).ProducesProblem(409);

        // ------------------------------------------------------------ shop: cart (SAL-01), quote + checkout (SAL-02), orders (SAL-03/04)
        g.MapGet("/cart", async (ClaimsPrincipal u, SalesRepository s) => Results.Ok(await s.GetCartAsync(CustomerId(u))))
            .RequireAuthorization(CustomerPolicy).WithName("getCart").Produces<List<CartLine>>();
        g.MapPost("/cart/items", (CartItemRequest body, ClaimsPrincipal u, SalesRepository s, CatalogRepository c) => Guard(async () =>
        {
            var p = await c.GetProductAsync(body.ProductId);
            if (p is null || !p.Active) return Results.Problem(title: "Product not for sale", statusCode: 404);
            var cart = await s.GetCartAsync(CustomerId(u));
            if (cart.Count >= SalesRepository.MaxOrderLines && cart.All(x => x.ProductId != p.Id))
                return Results.Problem(title: $"A cart can hold at most {SalesRepository.MaxOrderLines} products.", statusCode: 409);
            await s.AddToCartAsync(CustomerId(u), p, Math.Clamp(body.Quantity, 1, 99));
            return Results.Ok(await s.GetCartAsync(CustomerId(u)));
        })).RequireAuthorization(CustomerPolicy).WithName("addToCart").Produces<List<CartLine>>();
        g.MapPut("/cart/items/{productId:int}", (int productId, QuantityRequest body, ClaimsPrincipal u, SalesRepository s) => Guard(async () =>
        {
            await s.SetQuantityAsync(CustomerId(u), productId, Math.Clamp(body.Quantity, 0, 99));
            return Results.Ok(await s.GetCartAsync(CustomerId(u)));
        })).RequireAuthorization(CustomerPolicy).WithName("setCartQuantity").Produces<List<CartLine>>();
        g.MapDelete("/cart/items/{productId:int}", async (int productId, ClaimsPrincipal u, SalesRepository s) =>
        {
            await s.RemoveAsync(CustomerId(u), productId);
            return Results.Ok(await s.GetCartAsync(CustomerId(u)));
        }).RequireAuthorization(CustomerPolicy).WithName("removeFromCart").Produces<List<CartLine>>();

        g.MapGet("/ship-methods", async (PricingRepository p) => Results.Ok(await p.GetShipMethodsAsync())).WithName("listShipMethods").Produces<List<ShipMethodInfo>>();
        g.MapGet("/checkout/quote", (int? shipMethodId, ClaimsPrincipal u, SalesRepository s, CustomerRepository customers) => Guard(async () =>
        {
            var c = await customers.GetCustomerAsync(CustomerId(u)) ?? throw new KeyNotFoundException();
            return Results.Ok(await s.QuoteAsync(CustomerId(u), c, shipMethodId));
        })).RequireAuthorization(CustomerPolicy).WithName("getQuote").Produces<Quote>();
        g.MapPost("/checkout", (CheckoutRequest body, ClaimsPrincipal u, SalesRepository s, CustomerRepository customers) => Guard(async () =>
        {
            var c = await customers.GetCustomerAsync(CustomerId(u)) ?? throw new KeyNotFoundException();
            var o = await s.CheckoutAsync(CustomerId(u), c, Actor(u), body.ShipMethodId);
            return Results.Created($"/api/v2/orders/{o.Id}", o);
        })).RequireAuthorization(CustomerPolicy).WithName("checkout").Produces<Order>(201).ProducesProblem(409);
        g.MapGet("/orders", async (ClaimsPrincipal u, SalesRepository s, string? next) => Results.Ok(await s.GetOrdersForCustomerAsync(CustomerId(u), next)))
            .RequireAuthorization(CustomerPolicy).WithName("listMyOrders").Produces<OrderPage>();
        g.MapGet("/orders/{id:long}", async (long id, ClaimsPrincipal u, SalesRepository s) =>
            await s.GetOrderAsync(id, consistent: true) is { } o && o.CustomerId == CustomerId(u) ? Results.Ok(o) : Results.NotFound())
            .RequireAuthorization(CustomerPolicy).WithName("getMyOrder").Produces<Order>().Produces(404);

        // ------------------------------------------------------------ back office: fulfilment (SAL-05/06, INV-01/03)
        var bo = g.MapGroup("/back-office");
        bo.MapGet("/orders", (int? status, DateTime? from, DateTime? to, int? territoryId, string? next, FulfilmentRepository f) => Guard(async () =>
            Results.Ok(await f.QueueAsync(status ?? OrderStatus.InProcess, from, to, territoryId, next))))
            .RequireAuthorization(FulfilmentPolicy).WithName("listOrderQueue").Produces<OrderPage>();
        bo.MapGet("/orders/counts", async (FulfilmentRepository f) =>
            Results.Ok((await f.CountsAsync()).Select(kv => new StatusCount(kv.Key, OrderStatus.Text(kv.Key), kv.Value)).ToList()))
            .RequireAuthorization(FulfilmentPolicy).WithName("orderQueueCounts").Produces<List<StatusCount>>();
        bo.MapGet("/orders/{id:long}", async (long id, SalesRepository s, FulfilmentRepository f) =>
        {
            if (await s.GetOrderAsync(id, consistent: true) is not { } o) return Results.NotFound();
            var stock = new List<LineStock>();
            foreach (var pid in o.Lines.Select(l => l.ProductId).Distinct())
            {
                var st = await f.GetStockAsync(pid);
                stock.Add(new LineStock(pid, st.Total, st.ReorderPoint, st.Locations.Select(l => new StockAt(l.LocationId, l.Name, l.Quantity)).ToList()));
            }
            return Results.Ok(new BackOfficeOrder(o, OrderStatus.Text(o.Status), OrderStatus.AllowedActions(o.Status), stock));
        }).RequireAuthorization(FulfilmentPolicy).WithName("getBackOfficeOrder").Produces<BackOfficeOrder>().Produces(404);
        bo.MapPost("/orders/{id:long}/{op:regex(^(approve|reject|backorder|ship|cancel)$)}",
            (long id, string op, TransitionRequest body, ClaimsPrincipal u, HttpContext http, FulfilmentRepository f) => Guard(async () =>
            {
                var ship = op == "ship" ? new ShipRequest(body.ShipMethodId ?? 0, body.TrackingNumber ?? "") : null;
                return Results.Ok(await f.ApplyAsync(id, op, body.Version, Actor(u), ship, Token(http)));
            })).RequireAuthorization(FulfilmentPolicy).WithName("transitionOrder").Produces<TransitionResult>().ProducesProblem(400).ProducesProblem(409);
        bo.MapPost("/orders/bulk-approve", async (BulkRequest body, ClaimsPrincipal u, FulfilmentRepository f) =>
        {
            var results = new List<BulkResult>();
            foreach (var o in body.Orders.Take(50))
            {
                try { var r = await f.ApplyAsync(o.Id, "approve", o.Version, Actor(u)); results.Add(new(o.Id, true, $"{r.Order.Number} approved")); }
                catch (Exception e) when (e is ConflictException or ArgumentException or KeyNotFoundException) { results.Add(new(o.Id, false, e.Message)); }
            }
            return Results.Ok(results);
        }).RequireAuthorization(FulfilmentPolicy).WithName("bulkApprove").Produces<List<BulkResult>>();
        bo.MapGet("/changes", async (int? limit, FulfilmentRepository f) => Results.Ok(await f.FeedAsync(Math.Clamp(limit ?? 50, 1, 200))))
            .RequireAuthorization(StaffPolicy).WithName("listChanges").Produces<List<FeedEntry>>();
        bo.MapGet("/products/{id:int}/stock", async (int id, FulfilmentRepository f) =>
        {
            var st = await f.GetStockAsync(id);
            return Results.Ok(new LineStock(id, st.Total, st.ReorderPoint, st.Locations.Select(l => new StockAt(l.LocationId, l.Name, l.Quantity)).ToList()));
        }).RequireAuthorization(StaffPolicy).WithName("getStock").Produces<LineStock>();

        // ------------------------------------------------------------ back office: catalog admin (CAT-07 with the price-history fix)
        bo.MapPut("/products/{id:int}/price", (int id, PriceRequest body, ClaimsPrincipal u, CatalogRepository c, FulfilmentRepository f, TimeProvider clock) => Guard(async () =>
        {
            var p = await c.SetListPriceAsync(id, body.ListPrice, body.Version);
            var now = clock.GetUtcNow().UtcDateTime;
            await f.AppendFeedAsync(now, "product.price", p.ProductNumber, Actor(u),
                [$"aw-catalog {Keys.Product(id)} PRODUCT list_price {body.ListPrice} (Product -> stg.product)",
                 $"aw-catalog {Keys.Product(id)} {Keys.Price(now.Date)} (ListPriceHistory -> stg.list_price_history -> dw.dim_product SCD2)"]);
            return Results.Ok(new ProductDetail(p, [], await c.GetPriceHistoryAsync(id)));
        })).RequireAuthorization(CatalogAdminPolicy).WithName("setListPrice").Produces<ProductDetail>().ProducesProblem(409);

        // ------------------------------------------------------------ back office: procurement (C2-3: PUR-01..07, INV-01/02/03)
        var pr = bo.MapGroup("/procurement");
        pr.MapGet("/suggestions", async (ProcurementRepository p) => Results.Ok(await p.SuggestionsAsync()))
            .RequireAuthorization(ProcurementPolicy).WithName("listReorderSuggestions").Produces<List<ReorderSuggestion>>();
        pr.MapGet("/vendors", async (ProcurementRepository p) => Results.Ok(await p.ListVendorsAsync()))
            .RequireAuthorization(ProcurementPolicy).WithName("listVendors").Produces<List<VendorSummary>>();
        pr.MapGet("/vendors/{id:int}", async (int id, ProcurementRepository p) =>
        {
            if (await p.GetVendorAsync(id) is not { } v) return Results.NotFound();
            var orders = await p.ForVendorAsync(id);
            return Results.Ok(new VendorDetail(v.Vendor, v.Addresses, v.Contacts, v.Products, await p.PerformanceAsync(id, orders), orders.Take(50).ToList()));
        }).RequireAuthorization(ProcurementPolicy).WithName("getVendor").Produces<VendorDetail>().Produces(404);
        pr.MapGet("/products/{id:int}/vendors", async (int id, ProcurementRepository p) => Results.Ok(await p.SuppliersAsync(id)))
            .RequireAuthorization(ProcurementPolicy).WithName("listProductVendors").Produces<List<VendorProductInfo>>();
        pr.MapGet("/purchase-orders", (int? status, string? next, ProcurementRepository p) => Guard(async () =>
            Results.Ok(await p.OpenAsync(status ?? PoStatus.Pending, next))))
            .RequireAuthorization(ProcurementPolicy).WithName("listOpenPurchaseOrders").Produces<PoPage>().ProducesProblem(400);
        pr.MapGet("/purchase-orders/counts", async (ProcurementRepository p) =>
            Results.Ok((await p.OpenCountsAsync()).Select(kv => new StatusCount(kv.Key, PoStatus.Text(kv.Key), kv.Value)).ToList()))
            .RequireAuthorization(ProcurementPolicy).WithName("purchaseOrderCounts").Produces<List<StatusCount>>();
        pr.MapGet("/purchase-orders/mine", async (string? next, ClaimsPrincipal u, ProcurementRepository p) =>
            Staff(u).EmployeeId is { } e ? Results.Ok(await p.ForEmployeeAsync(e, next)) : Results.Ok(new PoPage([], null)))
            .RequireAuthorization(ProcurementPolicy).WithName("listMyPurchaseOrders").Produces<PoPage>();
        pr.MapGet("/purchase-orders/{id:int}", async (int id, ProcurementRepository p) => await p.GetOrderAsync(id) is { } o ? Results.Ok(o) : Results.NotFound())
            .RequireAuthorization(ProcurementPolicy).WithName("getPurchaseOrder").Produces<PurchaseOrder>().Produces(404);
        pr.MapPost("/purchase-orders", (CreatePoRequest body, ClaimsPrincipal u, HttpContext http, ProcurementRepository p, PricingRepository pricing) => Guard(async () =>
        {
            var o = await p.CreateAsync(body, Staff(u), await pricing.GetShipMethodsAsync(), Token(http));
            return Results.Created($"/api/v2/back-office/procurement/purchase-orders/{o.Id}", o);
        })).RequireAuthorization(ProcurementPolicy).WithName("createPurchaseOrder").Produces<PurchaseOrder>(201).ProducesProblem(400).ProducesProblem(404).ProducesProblem(409);
        pr.MapPost("/purchase-orders/{id:int}/{op:regex(^(approve|reject)$)}", (int id, string op, PoTransitionRequest body, ClaimsPrincipal u, HttpContext http, ProcurementRepository p) =>
            Guard(async () => Results.Ok(await p.TransitionAsync(id, op, body.Version, Actor(u), body.Note, Token(http)))))
            .RequireAuthorization(PurchasingManagerPolicy).WithName("transitionPurchaseOrder").Produces<PoResult>().ProducesProblem(400).ProducesProblem(409);
        pr.MapPost("/purchase-orders/{id:int}/receive", (int id, ReceiveRequest body, ClaimsPrincipal u, HttpContext http, ProcurementRepository p) =>
            Guard(async () => Results.Ok(await p.ReceiveAsync(id, body, Actor(u), Token(http)))))
            .RequireAuthorization(ProcurementPolicy).WithName("receivePurchaseOrder").Produces<PoResult>().ProducesProblem(400).ProducesProblem(409);
        pr.MapGet("/locations", () => Results.Ok(Locations.All.Select(kv => new StockAt(kv.Key, kv.Value, 0)).ToList()))
            .RequireAuthorization(ProcurementPolicy).WithName("listLocations").Produces<List<StockAt>>();

        // ------------------------------------------------------------ back office: production floor (C2-4: INV-01/03/04/05/06)
        var pf = bo.MapGroup("/production");
        pf.MapGet("/work-orders", (string? month, bool? openOnly, int? productId, ProductionRepository p) => Guard(async () =>
            Results.Ok(await p.ForMonthAsync(month ?? "2014-06", openOnly ?? false, productId))))
            .RequireAuthorization(StaffPolicy).WithName("listWorkOrders").Produces<WorkOrderList>().ProducesProblem(400);
        pf.MapGet("/work-orders/open", async (ProductionRepository p) => Results.Ok(await p.OpenAsync()))
            .RequireAuthorization(StaffPolicy).WithName("listOpenWorkOrders").Produces<List<WorkOrderSummary>>();
        pf.MapGet("/work-orders/{id:int}", async (int id, ProductionRepository p) => await p.GetAsync(id) is { } w ? Results.Ok(w) : Results.NotFound())
            .RequireAuthorization(StaffPolicy).WithName("getWorkOrder").Produces<WorkOrderDetail>().Produces(404);
        pf.MapPost("/work-orders", (CreateWorkOrderRequest body, ClaimsPrincipal u, HttpContext http, ProductionRepository p) => Guard(async () =>
        {
            var w = await p.CreateAsync(body, Actor(u), Token(http));
            return Results.Created($"/api/v2/back-office/production/work-orders/{w.Order.Id}", w);
        })).RequireAuthorization(ProductionPolicy).WithName("createWorkOrder").Produces<WorkOrderDetail>(201).ProducesProblem(400).ProducesProblem(404).ProducesProblem(409);
        pf.MapPost("/work-orders/{id:int}/operations", (int id, OperationRequest body, ClaimsPrincipal u, HttpContext http, ProductionRepository p) =>
            Guard(async () => Results.Ok(await p.RecordOperationAsync(id, body, Actor(u), Token(http)))))
            .RequireAuthorization(ProductionPolicy).WithName("recordOperation").Produces<WorkOrderResult>().ProducesProblem(400).ProducesProblem(409);
        pf.MapPost("/work-orders/{id:int}/complete", (int id, CompleteWorkOrderRequest body, ClaimsPrincipal u, HttpContext http, ProductionRepository p) =>
            Guard(async () => Results.Ok(await p.CompleteAsync(id, body, Actor(u), Token(http)))))
            .RequireAuthorization(ProductionPolicy).WithName("completeWorkOrder").Produces<WorkOrderResult>().ProducesProblem(400).ProducesProblem(409);
        pf.MapGet("/plan/{productId:int}", (int productId, int? qty, DateTime? due, ProductionRepository p) => Guard(async () =>
            Results.Ok(await p.PlanAsync(productId, qty ?? 1, due))))
            .RequireAuthorization(ProductionPolicy).WithName("planWorkOrder").Produces<ProductionPlan>().ProducesProblem(400);
        pf.MapGet("/assemblies", async (ProductionRepository p) => Results.Ok(await p.AssembliesAsync()))
            .RequireAuthorization(StaffPolicy).WithName("listAssemblies").Produces<List<AssemblyInfo>>();
        pf.MapGet("/bom/{productId:int}", async (int productId, DateTime? asOf, int? depth, ProductionRepository p) =>
            Results.Ok(await p.ExplodeAsync(productId, asOf ?? DateTime.UtcNow, depth ?? ProductionRepository.MaxBomDepth)))
            .RequireAuthorization(StaffPolicy).WithName("explodeBom").Produces<BomTree>();
        pf.MapGet("/where-used/{productId:int}", async (int productId, DateTime? asOf, int? depth, ProductionRepository p) =>
            Results.Ok(await p.WhereUsedAsync(productId, asOf ?? DateTime.UtcNow, depth ?? ProductionRepository.MaxBomDepth)))
            .RequireAuthorization(StaffPolicy).WithName("whereUsed").Produces<BomTree>();
        pf.MapGet("/kpis", (string? from, string? to, ProductionRepository p) => Guard(async () =>
            Results.Ok(await p.KpisAsync(from ?? "2013-07", to ?? "2014-06"))))
            .RequireAuthorization(StaffPolicy).WithName("productionKpis").Produces<ProductionKpis>().ProducesProblem(400);
        pf.MapGet("/scrap-reasons", async (ProductionRepository p) =>
            Results.Ok((await p.ScrapReasonsAsync()).Select(kv => new ScrapReasonInfo(kv.Key, kv.Value)).OrderBy(r => r.Name).ToList()))
            .RequireAuthorization(StaffPolicy).WithName("listScrapReasons").Produces<List<ScrapReasonInfo>>();

        // C2-5 AI layer (enable_ai, default off): status is public; semantic search is public; ask-the-data needs a staff role.
        var ai = g.MapGroup("/ai");
        ai.MapGet("/status", (AiOptions o, IServiceProvider sp, HttpContext h) =>
        {
            var (ql, tl) = o.Enabled ? sp.GetRequiredService<AiBudget>().Left(AiSession(h)) : (0, 0);
            return Results.Ok(new AiStatus(o.Enabled, o.Enabled ? o.Mode : "off", o.ChatModel, o.EmbeddingModel, o.RowLimit, o.TimeoutSeconds, ql, tl,
                o.Enabled && sp.GetRequiredService<ISqlRunner>().Connected));
        }).WithName("getAiStatus").Produces<AiStatus>();
        ai.MapGet("/search", async (string q, int? top, AiOptions o, IServiceProvider sp, CancellationToken ct) =>
        {
            if (!o.Enabled) return AiOff();
            if (string.IsNullOrWhiteSpace(q) || q.Length > 200) return Results.Problem(title: "q must be 1 to 200 characters.", statusCode: 400);
            return Results.Ok(await sp.GetRequiredService<SemanticSearch>().SearchAsync(q.Trim(), Math.Clamp(top ?? 10, 1, 30), o.Mode, ct));
        }).WithName("semanticSearch").Produces<SearchResult>().ProducesProblem(400).ProducesProblem(404);
        ai.MapGet("/examples", (AiOptions o) => o.Enabled ? Results.Ok(AiText.LoadEval().Select(e => e.Question).ToList()) : AiOff())
            .RequireAuthorization(StaffPolicy).WithName("askExamples").Produces<List<string>>().ProducesProblem(404);
        ai.MapPost("/ask", async (AskRequest body, AiOptions o, IServiceProvider sp, HttpContext h, ClaimsPrincipal u, CancellationToken ct) =>
            o.Enabled ? Results.Ok(await sp.GetRequiredService<AskService>().AskAsync(AiSession(h), Actor(u), body.Question, ct)) : AiOff())
            .RequireAuthorization(StaffPolicy).WithName("askTheData").Produces<AskResult>().ProducesProblem(404);
        ai.MapPost("/reindex", async (AiOptions o, IServiceProvider sp, CancellationToken ct) =>
            o.Enabled ? Results.Ok(new { indexed = await sp.GetRequiredService<SemanticSearch>().ReindexAsync(ct) }) : AiOff())
            .RequireAuthorization(CatalogAdminPolicy).WithName("reindexSearch").ProducesProblem(404);

        return g;
    }

    public static ClaimsPrincipal Principal(LoginResult login) => new(new ClaimsIdentity([
        new Claim(ClaimTypes.Name, login.DisplayName), new Claim(ClaimTypes.Email, login.Email),
        new Claim("customer_id", login.CustomerId.ToString()), new Claim("person_id", login.PersonId.ToString()),
        new Claim(ClaimTypes.Role, CustomerRole),
    ], CookieAuthenticationDefaults.AuthenticationScheme));

    /// <summary>C2-2 demo staff (no customer record): back-office roles only.</summary>
    public static ClaimsPrincipal StaffPrincipal(StaffAccount s) => new(new ClaimsIdentity(
        new[] { new Claim(ClaimTypes.Name, s.Name), new Claim(ClaimTypes.Email, s.Email.ToLowerInvariant()) }
            .Concat(s.EmployeeId is { } e ? [new Claim("employee_id", e.ToString(System.Globalization.CultureInfo.InvariantCulture))] : Array.Empty<Claim>())
            .Concat(s.Roles.Select(r => new Claim(ClaimTypes.Role, r))),
        CookieAuthenticationDefaults.AuthenticationScheme));

    public static MeDto Me(ClaimsPrincipal u) => u.Identity?.IsAuthenticated == true
        ? new(true, u.Identity.Name, u.FindFirstValue(ClaimTypes.Email), int.TryParse(u.FindFirstValue("customer_id"), out var c) ? c : null,
            u.FindAll(ClaimTypes.Role).Select(r => r.Value).DefaultIfEmpty(CustomerRole).Distinct().ToArray())
        : new(false, null, null, null, []);

    /// <summary>Cookie auth: API callers get 401/403 instead of a redirect to a login page (the SPA's /app/login).</summary>
    public static void ApiAwareRedirects(CookieAuthenticationOptions o)
    {
        o.Events.OnRedirectToLogin = ctx => Status(ctx, StatusCodes.Status401Unauthorized, "Sign in required");
        o.Events.OnRedirectToAccessDenied = ctx => Status(ctx, StatusCodes.Status403Forbidden, "Forbidden");
    }

    private static Task Status(RedirectContext<CookieAuthenticationOptions> ctx, int code, string title)
    {
        if (!IsApi(ctx.Request.Path)) { ctx.Response.Redirect(ctx.RedirectUri); return Task.CompletedTask; }
        ctx.Response.StatusCode = code;
        return ctx.Response.WriteAsJsonAsync(new { title, status = code }, (System.Text.Json.JsonSerializerOptions?)null, "application/problem+json");
    }
}
