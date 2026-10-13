using System.Globalization;
using AdventureWorks.Web.Ai;
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
builder.Services.AddSingleton(builder.Configuration.GetSection("Pricing").Get<PricingOptions>() ?? new PricingOptions());
builder.Services.AddSingleton<PricingRepository>();
builder.Services.AddSingleton(sp => new SalesRepository(sp.GetRequiredService<DynamoTables>(), sp.GetRequiredService<TimeProvider>(),
    sp.GetRequiredService<PricingRepository>(), sp.GetRequiredService<CatalogRepository>()));
builder.Services.AddSingleton<FulfilmentRepository>();
builder.Services.AddSingleton<ProcurementRepository>();
builder.Services.AddSingleton<ProductionRepository>();
// C2-5 AI layer: registered only when Ai:Enabled (Terraform enable_ai). Mode mock = hash embeddings, in-memory vectors, eval-replay model.
var aiOptions = builder.Configuration.GetSection("Ai").Get<AiOptions>() ?? new AiOptions();
builder.Services.AddSingleton(aiOptions);
if (aiOptions.Enabled)
{
    builder.Services.AddSingleton<AiBudget>();
    builder.Services.AddSingleton<SemanticSearch>();
    builder.Services.AddSingleton<AskService>();
    builder.Services.AddSingleton<AiAssist>();
    builder.Services.AddSingleton<TriageFacts>();
    builder.Services.AddSingleton<DemandRepository>();
    builder.Services.AddSingleton<ReorderFacts>();
    if (string.IsNullOrWhiteSpace(aiOptions.MonitorApiUrl)) builder.Services.AddSingleton<IWatchSource, ReplayWatchSource>();
    else builder.Services.AddHttpClient<IWatchSource, MonitorWatchSource>(c => c.Timeout = TimeSpan.FromSeconds(5));                  // C2-6 shared explain / draft service
    if (aiOptions.IsBedrock)
    {
        builder.Services.AddSingleton<Amazon.BedrockRuntime.IAmazonBedrockRuntime, Amazon.BedrockRuntime.AmazonBedrockRuntimeClient>(_ => new());
        builder.Services.AddSingleton<IEmbedder, TitanEmbedder>();
        builder.Services.AddSingleton<ISqlModel, BedrockSqlModel>();
        builder.Services.AddSingleton<IAssistModel, BedrockAssistModel>();
        builder.Services.AddSingleton<IVectorStore>(_ => new S3VectorStore(new Amazon.S3Vectors.AmazonS3VectorsClient(), aiOptions));
    }
    else
    {
        builder.Services.AddSingleton<IEmbedder>(new HashEmbedder(aiOptions.Dimensions));
        builder.Services.AddSingleton<ISqlModel>(new MockSqlModel(AiText.LoadEval()));
        builder.Services.AddSingleton<IAssistModel>(new MockAssistModel(aiOptions));
        builder.Services.AddSingleton<IVectorStore, InMemoryVectorStore>();
    }
    if (!string.IsNullOrEmpty(aiOptions.RedshiftWorkgroup))
        builder.Services.AddSingleton<ISqlRunner>(_ => new RedshiftDataRunner(new Amazon.RedshiftDataAPIService.AmazonRedshiftDataAPIServiceClient(), aiOptions));
    else if (!string.IsNullOrEmpty(aiOptions.WarehouseConnection)) builder.Services.AddSingleton<ISqlRunner>(new PostgresRunner(aiOptions.WarehouseConnection));
    else builder.Services.AddSingleton<ISqlRunner, NoWarehouseRunner>();
}
builder.Services.AddSingleton(builder.Configuration.GetSection("Demo").Get<DemoOptions>() ?? new DemoOptions());

// C2-3 (John's C2-2 decision 3): the Razor UI (shop, account, admin) is gone; Chapter 1 keeps it in tag v1.0-migration
// and at /c1/. The app serves /api/v2, the SPA at /app/ and /healthz only.
// Phase 8 (ADR 0009): Showcase:FrameAncestors = space-separated origins allowed to embed the app (the showcase's
// "App" tab). Unset = default antiforgery X-Frame-Options: SAMEORIGIN.
var frameAncestors = builder.Configuration["Showcase:FrameAncestors"]?.Trim();
builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme)
    .AddCookie(o => { o.LoginPath = "/app/login"; o.Cookie.Name = "aw.after"; o.SlidingExpiration = true; V2.ApiAwareRedirects(o); });
builder.Services.AddAuthorizationBuilder()
    .AddPolicy(V2.CustomerPolicy, p => p.RequireClaim("customer_id"))
    .AddPolicy(V2.FulfilmentPolicy, p => p.RequireRole(V2.FulfilmentRole))
    .AddPolicy(V2.CatalogAdminPolicy, p => p.RequireRole(V2.CatalogAdminRole))
    .AddPolicy(V2.ProcurementPolicy, p => p.RequireRole(V2.BuyerRole, V2.PurchasingManagerRole))
    .AddPolicy(V2.PurchasingManagerPolicy, p => p.RequireRole(V2.PurchasingManagerRole))
    .AddPolicy(V2.ProductionPolicy, p => p.RequireRole(V2.ProductionRole))
    .AddPolicy(V2.StaffPolicy, p => p.RequireRole(V2.StaffRoles));
builder.Services.AddProblemDetails();
// C2-2: numbers are plain JSON numbers (no "number | string" in the OpenAPI schema), so the generated SPA client gets number types.
builder.Services.ConfigureHttpJsonOptions(o => o.SerializerOptions.NumberHandling = System.Text.Json.Serialization.JsonNumberHandling.Strict);
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
app.UseExceptionHandler();
app.UseWhen(c => V2.IsApi(c.Request.Path), b => b.UseStatusCodePages());
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
// / opens the SPA (C2-2). C2-3 removed the Razor shop and /classic (John's C2-2 decision 3).
app.MapGet("/", () => Results.Redirect("/app/")).ExcludeFromDescription();
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
    /// <summary>C2-2 back-office demo staff (same demo password; no customer record, roles only).</summary>
    public List<StaffAccount> Staff { get; set; } =
    [
        new() { Email = "fulfilment@adventure-works.com", Name = "Fulfilment clerk (demo)", Roles = [V2.FulfilmentRole] },
        new() { Email = "ops@adventure-works.com", Name = "Ops manager (demo)", Roles = [V2.FulfilmentRole, V2.CatalogAdminRole] },
        // C2-3: real AdventureWorks purchasing employees (HumanResources.Employee 251 Buyer, 250 Purchasing Manager), so
        // "my POs" (PUR-06, GSI2 EMPLOYEE#) also shows their SQL-era purchase orders. Same demo password; no new auth system.
        new() { Email = "mikael0@adventure-works.com", Name = "Mikael Sandberg", EmployeeId = 251, Roles = [V2.BuyerRole] },
        new() { Email = "sheela0@adventure-works.com", Name = "Sheela Word", EmployeeId = 250, Roles = [V2.BuyerRole, V2.PurchasingManagerRole] },
        // C2-4: a production supervisor (synthetic, like fulfilment@): work orders are not tied to an employee in AdventureWorks.
        new() { Email = "production@adventure-works.com", Name = "Production supervisor (demo)", Roles = [V2.ProductionRole] },
    ];
}

public sealed class StaffAccount
{
    public string Email { get; set; } = "";
    public string Name { get; set; } = "";
    public List<string> Roles { get; set; } = [];
    public int? EmployeeId { get; set; }
}

public partial class Program { }
