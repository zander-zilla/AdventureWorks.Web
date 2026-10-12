using System.Security.Claims;
using AdventureWorks.Web.Data;
using AdventureWorks.Web.Models;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;

namespace AdventureWorks.Web.Api;

public sealed record MeDto(bool Authenticated, string? Name, string? Email, int? CustomerId, string[] Roles);
public sealed record LoginRequest(string Email, string Password);

/// <summary>
/// Chapter 2 JSON API (ADR 0010): minimal APIs under /api/v2, same cookie auth as the Razor app, problem+json errors,
/// 401/403 instead of login redirects, and a CSRF guard (custom header on unsafe methods).
/// </summary>
public static class V2
{
    public const string ClientHeader = "X-AW-Client";
    public const string CustomerPolicy = "customer";

    public static bool IsApi(PathString p) => p.StartsWithSegments("/api");

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

        g.MapGet("/me", (ClaimsPrincipal u) => Me(u));

        g.MapPost("/auth/login", async (LoginRequest body, HttpContext http, CustomerRepository customers, DemoOptions demo) =>
        {
            var email = body.Email?.Trim() ?? "";
            var allowed = demo.Emails.Contains(email, StringComparer.OrdinalIgnoreCase) && body.Password == demo.Password;
            var login = allowed ? await customers.FindLoginAsync(email) : null;
            if (login is null) return Results.Problem(title: "Unknown demo customer or wrong password", statusCode: StatusCodes.Status401Unauthorized);
            var principal = Principal(login);
            await http.SignInAsync(principal);
            return Results.Ok(Me(principal));
        });

        g.MapPost("/auth/logout", async (HttpContext http) => { await http.SignOutAsync(); return Results.NoContent(); });

        // CAT-06 (paged, DynamoDB cursor) and CAT-01.
        g.MapGet("/products", async (CatalogRepository c, string? next, int? pageSize) =>
            Results.Ok(await c.ListProductsAsync(next, Math.Clamp(pageSize ?? 25, 1, 100))));
        g.MapGet("/products/{id:int}", async (int id, CatalogRepository c) => await c.GetProductAsync(id) is { } p ? Results.Ok(p) : Results.NotFound());
        g.MapGet("/categories", async (CatalogRepository c) => Results.Ok(await c.GetCategoryTreeAsync()));

        // SAL-01 cart: the first endpoint behind the customer policy (401 problem+json when anonymous).
        g.MapGet("/cart", async (ClaimsPrincipal u, SalesRepository s) => Results.Ok(await s.GetCartAsync(int.Parse(u.FindFirstValue("customer_id")!))))
            .RequireAuthorization(CustomerPolicy);

        return g;
    }

    public static ClaimsPrincipal Principal(LoginResult login) => new(new ClaimsIdentity([
        new Claim(ClaimTypes.Name, login.DisplayName), new Claim(ClaimTypes.Email, login.Email),
        new Claim("customer_id", login.CustomerId.ToString()), new Claim("person_id", login.PersonId.ToString()),
        new Claim(ClaimTypes.Role, "Customer"),
    ], CookieAuthenticationDefaults.AuthenticationScheme));

    public static MeDto Me(ClaimsPrincipal u) => u.Identity?.IsAuthenticated == true
        ? new(true, u.Identity.Name, u.FindFirstValue(ClaimTypes.Email), int.TryParse(u.FindFirstValue("customer_id"), out var c) ? c : null,
            u.FindAll(ClaimTypes.Role).Select(r => r.Value).DefaultIfEmpty("Customer").Distinct().ToArray())
        : new(false, null, null, null, []);

    /// <summary>Cookie auth: API callers get 401/403 instead of a redirect to the Razor login page.</summary>
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
