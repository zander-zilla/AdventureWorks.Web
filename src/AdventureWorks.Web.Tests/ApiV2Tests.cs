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

    [Fact] public async Task Protected_api_returns_401_but_razor_still_redirects()
    {
        var c = Client();
        var api = await c.GetAsync("/api/v2/cart");
        Assert.Equal(HttpStatusCode.Unauthorized, api.StatusCode);
        var razor = await c.GetAsync("/Cart");
        Assert.Equal(HttpStatusCode.Redirect, razor.StatusCode);
        Assert.Contains("/Account/Login", razor.Headers.Location!.ToString());
    }

    [Fact] public async Task OpenApi_document_lists_v2_endpoints()
    {
        var doc = await Client().GetStringAsync("/api/v2/openapi.json");
        foreach (var p in new[] { "/api/v2/me", "/api/v2/auth/login", "/api/v2/products", "/api/v2/categories", "/api/v2/cart" }) Assert.Contains($"\"{p}\"", doc);
        Assert.DoesNotContain("\"/Shop", doc);
    }

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

    [Fact] public async Task Cookies_stay_lax_when_not_framed()
    {
        var r = await Client().GetAsync("/Account/Login");
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
        var https = new HttpRequestMessage(HttpMethod.Get, "/Account/Login"); https.Headers.Add("X-Forwarded-Proto", "https");
        var r = await c.SendAsync(https);
        Assert.Equal("frame-ancestors 'self' https://showcase.example", r.Headers.GetValues("Content-Security-Policy").Single());
        Assert.All(r.Headers.GetValues("Set-Cookie"), cookie =>
        {
            Assert.Contains("samesite=none", cookie, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("secure", cookie, StringComparison.OrdinalIgnoreCase);
        });

        var http = await c.GetAsync("/Account/Login");   // plain HTTP: Secure cookies would be dropped, so keep Lax
        Assert.All(http.Headers.GetValues("Set-Cookie"), cookie => Assert.DoesNotContain("samesite=none", cookie, StringComparison.OrdinalIgnoreCase));
    }
}
