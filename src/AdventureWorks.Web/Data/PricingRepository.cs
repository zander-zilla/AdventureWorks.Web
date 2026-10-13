using System.Globalization;
using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using AdventureWorks.Web.Models;

namespace AdventureWorks.Web.Data;

/// <summary>Pricing options. OfferDate: the date special offers are evaluated on. AdventureWorks' offer calendar ends in
/// 2014, so the demo default is 2014-05-01 (volume discounts and the spring 2014 promotions are live); "today" uses the
/// real date (then only offers without an end in the past apply, i.e. none of the sample offers).</summary>
public sealed class PricingOptions
{
    public string OfferDate { get; set; } = "2014-05-01";
    public int DefaultShipMethodId { get; set; } = 1;
    public DateTime OfferDateFor(DateTime now) => OfferDate.Equals("today", StringComparison.OrdinalIgnoreCase)
        ? now.Date : DateTime.ParseExact(OfferDate, "yyyy-MM-dd", CultureInfo.InvariantCulture);
}

/// <summary>Reads the pricing inputs: CAT-10 offers (aw-catalog), REF-02 tax and REF-04 ship methods (aw-reference;
/// small lists, cached for 10 minutes as the reference design suggests).</summary>
public sealed class PricingRepository(DynamoTables t, PricingOptions options, TimeProvider clock)
{
    private static readonly TimeSpan CacheFor = TimeSpan.FromMinutes(10);
    private (DateTimeOffset At, List<ShipMethodInfo> Methods)? _methods;
    private readonly Dictionary<string, (DateTimeOffset At, TaxInfo? Tax)> _tax = new();

    public PricingOptions Options => options;

    // CAT-10: offers denormalised on the product partition.
    public async Task<List<OfferInfo>> GetOffersAsync(int productId)
    {
        var items = await t.For(DynamoTables.Catalog).QueryAll(new QueryRequest
        {
            TableName = t.Name(DynamoTables.Catalog), KeyConditionExpression = "PK = :pk AND begins_with(SK, :o)",
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Product(productId)), [":o"] = Av.S("OFFER#") },
        });
        return items.Where(i => i.IsLive()).Select(i => new OfferInfo(i.Int("special_offer_id") ?? int.Parse(i.Str("SK")![6..]), i.Str("offer_description") ?? "",
            i.Dec("discount_pct") ?? 0, i.Str("offer_type") ?? "", i.Str("offer_category") ?? "", i.Date("offer_start") ?? DateTime.MinValue,
            i.Date("offer_end") ?? DateTime.MaxValue, i.Int("min_qty") ?? 0, i.Int("max_qty"))).ToList();
    }

    // REF-04
    public async Task<List<ShipMethodInfo>> GetShipMethodsAsync()
    {
        var now = clock.GetUtcNow();
        if (_methods is { } c && now - c.At < CacheFor) return c.Methods;
        var items = await t.For(DynamoTables.Reference).QueryAll(new QueryRequest
        {
            TableName = t.Name(DynamoTables.Reference), KeyConditionExpression = "PK = :pk",
            ExpressionAttributeValues = new() { [":pk"] = Av.S("SHIPMETHODS") },
        });
        var list = items.Where(i => i.IsLive()).Select(i => new ShipMethodInfo(i.Int("ship_method_id")!.Value, i.Str("name") ?? "", i.Dec("ship_base") ?? 0, i.Dec("ship_rate") ?? 0))
            .OrderBy(m => m.Id).ToList();
        _methods = (now, list);
        return list;
    }

    /// <summary>REF-02: ship-to (country code, state code) -> StateProvince item (COUNTRY#cc / STATE#code) -> TAX#id rates.</summary>
    public async Task<TaxInfo?> GetTaxAsync(string? country, string? state)
    {
        if (string.IsNullOrWhiteSpace(country) || string.IsNullOrWhiteSpace(state)) return null;
        var key = $"{country.Trim().ToUpperInvariant()}/{state.Trim().ToUpperInvariant()}";
        var now = clock.GetUtcNow();
        lock (_tax) if (_tax.TryGetValue(key, out var c) && now - c.At < CacheFor) return c.Tax;
        var db = t.For(DynamoTables.Reference); var table = t.Name(DynamoTables.Reference);
        var sp = await db.GetItemAsync(new GetItemRequest { TableName = table, Key = new()
            { ["PK"] = Av.S("COUNTRY#" + country.Trim().ToUpperInvariant()), ["SK"] = Av.S("STATE#" + state.Trim().ToUpperInvariant()) } });
        TaxInfo? tax = null;
        if (sp.Item is { Count: > 0 } s && s.IsLive() && s.Int("state_province_id") is { } id)
        {
            var rates = await db.QueryAll(new QueryRequest { TableName = table, KeyConditionExpression = "PK = :pk",
                ExpressionAttributeValues = new() { [":pk"] = Av.S($"TAX#{id:000}") } });
            var live = rates.Where(r => r.IsLive()).ToList();
            var rate = Pricing.RetailRate(live.Select(r => (r.Int("tax_type") ?? 0, r.Dec("tax_rate") ?? 0)));
            var name = live.OrderBy(r => r.Int("tax_type") == 1 ? 0 : 1).Select(r => r.Str("name")).FirstOrDefault();
            tax = new TaxInfo(id, state.Trim().ToUpperInvariant(), s.Str("name"), s.Int("territory_id"), rate ?? 0, rate is null ? null : name);
        }
        lock (_tax) _tax[key] = (now, tax);
        return tax;
    }

    public async Task<Quote> QuoteAsync(IReadOnlyList<CartLine> cart, Address? shipTo, int? shipMethodId, CatalogRepository catalog)
    {
        var methods = await GetShipMethodsAsync();
        var ship = methods.FirstOrDefault(m => m.Id == (shipMethodId ?? options.DefaultShipMethodId))
                   ?? throw new ArgumentException($"Unknown ship method {shipMethodId}.");
        var items = new List<PricingItem>();
        foreach (var c in cart)
        {
            var p = await catalog.GetProductAsync(c.ProductId);
            items.Add(new PricingItem(c.ProductId, c.Name, c.ProductNumber, c.Quantity, c.UnitPrice, p?.Weight, p?.WeightUnit, await GetOffersAsync(c.ProductId)));
        }
        var tax = await GetTaxAsync(shipTo?.Country, shipTo?.State);
        return Pricing.Price(items, tax, ship, options.OfferDateFor(clock.GetUtcNow().UtcDateTime));
    }
}
