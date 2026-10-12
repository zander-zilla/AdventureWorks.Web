using System.Globalization;
using AdventureWorks.Web.Api;
using AdventureWorks.Web.Data;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Authentication.Cookies;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);

var dynamo = builder.Configuration.GetSection("DynamoDb").Get<DynamoOptions>() ?? new DynamoOptions();
builder.Services.AddSingleton(dynamo);
builder.Services.AddSingleton(sp => new DynamoTables(dynamo));
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddSingleton<CatalogRepository>();
builder.Services.AddSingleton<CustomerRepository>();
builder.Services.AddSingleton<SalesRepository>();
builder.Services.AddSingleton(builder.Configuration.GetSection("Demo").Get<DemoOptions>() ?? new DemoOptions());

builder.Services.AddControllersWithViews();
// Phase 8 (ADR 0009): Showcase:FrameAncestors = space-separated origins allowed to embed the app (the showcase's
// "App" tab). Unset = default antiforgery X-Frame-Options: SAMEORIGIN.
var frameAncestors = builder.Configuration["Showcase:FrameAncestors"]?.Trim();
if (!string.IsNullOrEmpty(frameAncestors))
    builder.Services.AddAntiforgery(o => o.SuppressXFrameOptionsHeader = true);
builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme)
    .AddCookie(o => { o.LoginPath = "/Account/Login"; o.Cookie.Name = "aw.after"; o.SlidingExpiration = true; V2.ApiAwareRedirects(o); });
builder.Services.AddAuthorizationBuilder().AddPolicy(V2.CustomerPolicy, p => p.RequireClaim("customer_id"));
builder.Services.AddProblemDetails();
builder.Services.AddOpenApi("v2", o => o.ShouldInclude = d => d.RelativePath?.StartsWith("api/v2") == true);
// ALB terminates TLS: trust X-Forwarded-Proto so Request.IsHttps reflects the browser's scheme (cookie policy below).
builder.Services.Configure<ForwardedHeadersOptions>(o =>
{
    o.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
    o.KnownIPNetworks.Clear(); o.KnownProxies.Clear();
});
// C2-0 (ADR 0010): when the app may be framed by the showcase (FrameAncestors set) and the page is HTTPS, cookies are
// SameSite=None; Secure so sign-in works inside the cross-site iframe (Chapter 1 limitation: "log in in a new tab").
// Plain HTTP or no FrameAncestors: unchanged (Lax).
builder.Services.Configure<CookiePolicyOptions>(o =>
{
    void Relax(HttpContext ctx, CookieOptions c)
    {
        if (string.IsNullOrEmpty(frameAncestors) || !ctx.Request.IsHttps) return;
        c.SameSite = SameSiteMode.None; c.Secure = true;
    }
    o.OnAppendCookie = e => Relax(e.Context, e.CookieOptions);
    o.OnDeleteCookie = e => Relax(e.Context, e.CookieOptions);
});
builder.Services.AddHealthChecks();

// OpenTelemetry tracing (nice-to-have): ASP.NET Core + outgoing HTTP (the DynamoDB SDK calls). OTLP when an endpoint is set.
builder.Services.AddOpenTelemetry()
    .ConfigureResource(r => r.AddService("adventureworks-web-after"))
    .WithTracing(t =>
    {
        t.AddAspNetCoreInstrumentation().AddHttpClientInstrumentation().AddSource("Amazon.AWSSDK.DynamoDBv2");
        if (builder.Configuration["OTEL_CONSOLE"] == "true") t.AddConsoleExporter();
    });

var app = builder.Build();
app.UseForwardedHeaders();
if (!app.Environment.IsDevelopment())
    app.UseWhen(c => !V2.IsApi(c.Request.Path), b => b.UseExceptionHandler("/Home/Error"));
app.UseWhen(c => V2.IsApi(c.Request.Path), b => b.UseExceptionHandler().UseStatusCodePages());
app.UseCookiePolicy();
app.Use((ctx, next) => { if (ctx.Request.Path.Value == "/app") { ctx.Response.Redirect("/app/"); return Task.CompletedTask; } return next(); });
if (!string.IsNullOrEmpty(frameAncestors))
    app.Use((ctx, next) => { ctx.Response.Headers.ContentSecurityPolicy = "frame-ancestors 'self' " + frameAncestors; return next(); });
app.UseStaticFiles();
app.UseRouting();
app.UseAuthentication();
app.UseAuthorization();
app.MapHealthChecks("/healthz");
app.MapOpenApi("/api/{documentName}/openapi.json");
app.MapApiV2();
// Chapter 2 SPA (src/web, built into wwwroot/app by the Dockerfile / `npm run build`): client-side routes fall back to index.html.
app.MapFallbackToFile("/app/{*path:nonfile}", "app/index.html");
app.MapControllerRoute("default", "{controller=Shop}/{action=Index}/{id?}");
app.Run();

public sealed class DemoOptions
{
    /// <summary>Demo-only shared password (same as the before app).</summary>
    public string Password { get; set; } = "Demo!2026";
    public List<string> Emails { get; set; } =
    [
        "catherine0@adventure-works.com", "cory0@adventure-works.com", "christopher1@adventure-works.com",
        "donald0@adventure-works.com", "walter0@adventure-works.com",
    ];
}

public partial class Program { }
