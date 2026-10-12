using System.Globalization;
using AdventureWorks.Web.Data;
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
builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme)
    .AddCookie(o => { o.LoginPath = "/Account/Login"; o.Cookie.Name = "aw.after"; o.SlidingExpiration = true; });
builder.Services.AddAuthorization();
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
if (!app.Environment.IsDevelopment()) app.UseExceptionHandler("/Home/Error");
app.UseStaticFiles();
app.UseRouting();
app.UseAuthentication();
app.UseAuthorization();
app.MapHealthChecks("/healthz");
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
