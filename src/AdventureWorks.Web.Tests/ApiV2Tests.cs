using System.Net;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;

namespace AdventureWorks.Web.Tests;

/// <summary>C2-0 /api/v2 scaffolding and /app/ hosting, in-process (no DynamoDB needed for these paths).</summary>
public sealed class ApiV2Tests : IClassFixture<ApiV2Tests.Factory>
{
    public sealed class Factory : WebApplicationFactory<Program>
    {
        public readonly string WebRoot = Directory.CreateTempSubdirectory("aw-webroot").FullName;
        public string? FrameAncestors { get; init; }
        public Factory()
        {
            Directory.CreateDirectory(Path.Combine(WebRoot, "app"));
            File.WriteAllText(Path.Combine(WebRoot, "app", "index.html"), "<!doctype html><div id=root></div><!-- spa -->");
        }
        protected override void ConfigureWebHost(IWebHostBuilder b)
        {
            b.UseWebRoot(WebRoot).UseEnvironment("Production");
            if (FrameAncestors is not null) b.UseSetting("Showcase:FrameAncestors", FrameAncestors);
        }
    }

    private readonly Factory f;
    public ApiV2Tests(Factory f) => this.f = f;
    private HttpClient Client() => f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false });

    [Fact] public async Task Me_is_anonymous_by_default()
    {
        var me = await Client().GetFromJsonAsync<JsonElement>("/api/v2/me");
        Assert.False(me.GetProperty("authenticated").GetBoolean());
    }

    [Fact] public async Task Unsafe_methods_need_the_client_header()
    {
        var r = await Client().PostAsJsonAsync("/api/v2/auth/login", new { email = "x@y", password = "z" });
        Assert.Equal(HttpStatusCode.BadRequest, r.StatusCode);
    }

    [Fact] public async Task Wrong_password_is_401_problem_json_without_touching_dynamodb()
    {
        var c = Client(); c.DefaultRequestHeaders.Add("X-AW-Client", "test");
        var r = await c.PostAsJsonAsync("/api/v2/auth/login", new { email = "donald0@adventure-works.com", password = "nope" });
        Assert.Equal(HttpStatusCode.Unauthorized, r.StatusCode);
        Assert.Equal("application/problem+json", r.Content.Headers.ContentType?.MediaType);
    }

    [Fact] public async Task Protected_api_returns_401()
    {
        var api = await Client().GetAsync("/api/v2/cart");
        Assert.Equal(HttpStatusCode.Unauthorized, api.StatusCode);
    }

    [Fact] public async Task OpenApi_document_lists_v2_endpoints()
    {
        var doc = await Client().GetStringAsync("/api/v2/openapi.json");
        foreach (var p in new[] { "/api/v2/me", "/api/v2/auth/login", "/api/v2/products", "/api/v2/categories", "/api/v2/cart", "/api/v2/cart/items",
                     "/api/v2/checkout/quote", "/api/v2/checkout", "/api/v2/orders", "/api/v2/products/{id}/reviews", "/api/v2/ship-methods",
                     "/api/v2/back-office/orders", "/api/v2/back-office/orders/{id}/{op}", "/api/v2/back-office/changes", "/api/v2/back-office/products/{id}/price",
                     "/api/v2/back-office/procurement/suggestions", "/api/v2/back-office/procurement/vendors/{id}", "/api/v2/back-office/procurement/purchase-orders",
                     "/api/v2/back-office/procurement/purchase-orders/{id}/{op}", "/api/v2/back-office/procurement/purchase-orders/{id}/receive",
                     "/api/v2/back-office/procurement/purchase-orders/mine" })
            Assert.Contains($"\"{p}\"", doc);
        Assert.DoesNotContain("\"/Shop", doc);
        Assert.Contains("\"Quote\"", doc);   // response schemas are declared (the SPA client is generated from them)
        // C2-2: the generated SPA client (src/web) is built from this document; CI writes it and fails if the committed copy differs.
        if (Environment.GetEnvironmentVariable("AW_OPENAPI_OUT") is { Length: > 0 } outPath)
            File.WriteAllText(outPath, System.Text.Json.Nodes.JsonNode.Parse(doc)!.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + "\n");
    }

    private async Task<HttpClient> SignedIn(string email)
    {
        var c = Client(); c.DefaultRequestHeaders.Add("X-AW-Client", "test");
        var r = await c.PostAsJsonAsync("/api/v2/auth/login", new { email, password = "Demo!2026" });
        r.EnsureSuccessStatusCode();   // the test client keeps the auth cookie (HandleCookies)
        return c;
    }

    [Fact] public async Task Staff_login_carries_back_office_roles_without_dynamodb()
    {
        var c = await SignedIn("ops@adventure-works.com");
        var me = await c.GetFromJsonAsync<JsonElement>("/api/v2/me");
        Assert.Equal(new[] { "Fulfilment", "CatalogAdmin" }, me.GetProperty("roles").EnumerateArray().Select(x => x.GetString()).ToArray());
        Assert.Equal(JsonValueKind.Null, me.GetProperty("customerId").ValueKind);
    }

    [Theory]
    [InlineData("/api/v2/back-office/orders")]
    [InlineData("/api/v2/back-office/changes")]
    [InlineData("/api/v2/checkout/quote")]
    [InlineData("/api/v2/orders")]
    [InlineData("/api/v2/back-office/procurement/suggestions")]
    [InlineData("/api/v2/back-office/procurement/purchase-orders")]
    public async Task Anonymous_gets_401_on_protected_endpoints(string path) =>
        Assert.Equal(HttpStatusCode.Unauthorized, (await Client().GetAsync(path)).StatusCode);

    [Fact] public async Task Roles_are_enforced()
    {
        var clerk = await SignedIn("fulfilment@adventure-works.com");
        var price = await clerk.PutAsJsonAsync("/api/v2/back-office/products/680/price", new { listPrice = 1, version = 1 });
        Assert.Equal(HttpStatusCode.Forbidden, price.StatusCode);                       // Fulfilment is not CatalogAdmin
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.GetAsync("/api/v2/cart")).StatusCode);   // staff are not customers
        var bad = await clerk.PostAsJsonAsync("/api/v2/back-office/orders/1/explode", new { version = 1 });
        Assert.Equal(HttpStatusCode.NotFound, bad.StatusCode);                          // only the 5 transitions are routed
    }

    [Fact] public async Task Procurement_roles_are_enforced()
    {
        var buyer = await SignedIn("mikael0@adventure-works.com");
        var me = await buyer.GetFromJsonAsync<JsonElement>("/api/v2/me");
        Assert.Equal(new[] { "Buyer" }, me.GetProperty("roles").EnumerateArray().Select(x => x.GetString()).ToArray());
        var approve = await buyer.PostAsJsonAsync("/api/v2/back-office/procurement/purchase-orders/100001/approve", new { version = 1 });
        Assert.Equal(HttpStatusCode.Forbidden, approve.StatusCode);                     // buyers cannot approve their own POs
        Assert.Equal(HttpStatusCode.Forbidden, (await buyer.GetAsync("/api/v2/back-office/orders")).StatusCode);   // not Fulfilment
        var clerk = await SignedIn("fulfilment@adventure-works.com");
        Assert.Equal(HttpStatusCode.Forbidden, (await clerk.GetAsync("/api/v2/back-office/procurement/suggestions")).StatusCode);
        var bad = await (await SignedIn("sheela0@adventure-works.com")).PostAsJsonAsync("/api/v2/back-office/procurement/purchase-orders/1/explode", new { version = 1 });
        Assert.Equal(HttpStatusCode.NotFound, bad.StatusCode);
    }

    [Theory]
    [InlineData("/classic")]
    [InlineData("/Shop")]
    [InlineData("/Shop/Product/707")]
    [InlineData("/Cart")]
    [InlineData("/Account/Login")]
    [InlineData("/Products")]
    public async Task Razor_ui_is_gone(string path) =>   // C2-3: Chapter 1's Razor UI lives in tag v1.0-migration and /c1/ only
        Assert.Equal(HttpStatusCode.NotFound, (await Client().GetAsync(path)).StatusCode);

    [Fact] public async Task Root_opens_the_spa() =>
        Assert.Equal("/app/", (await Client().GetAsync("/")).Headers.Location!.ToString());

    [Theory]
    [InlineData("/app/")]
    [InlineData("/app/design")]
    [InlineData("/app/shop/products")]
    public async Task Spa_routes_fall_back_to_index(string path)
    {
        var r = await Client().GetAsync(path);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Contains("<!-- spa -->", await r.Content.ReadAsStringAsync());
    }

    [Fact] public async Task App_without_slash_redirects() =>
        Assert.Equal("/app/", (await Client().GetAsync("/app")).Headers.Location!.ToString());

    internal static HttpRequestMessage StaffLogin(bool https = false)
    {
        var m = new HttpRequestMessage(HttpMethod.Post, "/api/v2/auth/login") { Content = JsonContent.Create(new { email = "ops@adventure-works.com", password = "Demo!2026" }) };
        m.Headers.Add("X-AW-Client", "test");
        if (https) m.Headers.Add("X-Forwarded-Proto", "https");
        return m;
    }

    [Fact] public async Task Cookies_stay_lax_when_not_framed()
    {
        var r = await Client().SendAsync(StaffLogin());
        Assert.All(r.Headers.GetValues("Set-Cookie"), c => Assert.DoesNotContain("samesite=none", c, StringComparison.OrdinalIgnoreCase));
    }
}

/// <summary>Framed by the showcase over HTTPS (ALB sets X-Forwarded-Proto): cookies become SameSite=None; Secure.</summary>
public sealed class FramedCookieTests
{
    [Fact] public async Task Cookies_are_cross_site_when_framed_over_https()
    {
        using var f = new ApiV2Tests.Factory { FrameAncestors = "https://showcase.example" };
        var c = f.CreateClient(new WebApplicationFactoryClientOptions { AllowAutoRedirect = false });
        var r = await c.SendAsync(ApiV2Tests.StaffLogin(https: true));
        Assert.Equal("frame-ancestors 'self' https://showcase.example", r.Headers.GetValues("Content-Security-Policy").Single());
        Assert.All(r.Headers.GetValues("Set-Cookie"), cookie =>
        {
            Assert.Contains("samesite=none", cookie, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("secure", cookie, StringComparison.OrdinalIgnoreCase);
        });

        var http = await c.SendAsync(ApiV2Tests.StaffLogin());   // plain HTTP: Secure cookies would be dropped, so keep Lax
        Assert.All(http.Headers.GetValues("Set-Cookie"), cookie => Assert.DoesNotContain("samesite=none", cookie, StringComparison.OrdinalIgnoreCase));
    }
}
