using System.Globalization;

namespace AdventureWorks.Web.Data;

public sealed record OfferInfo(int Id, string Description, decimal DiscountPct, string Type, string Category, DateTime Start, DateTime End, int MinQty, int? MaxQty);
public sealed record ShipMethodInfo(int Id, string Name, decimal ShipBase, decimal ShipRate);
public sealed record TaxInfo(int StateProvinceId, string StateCode, string? StateName, int? TerritoryId, decimal Rate, string? Name);
public sealed record PricingItem(int ProductId, string Name, string ProductNumber, int Quantity, decimal UnitPrice, decimal? Weight, string? WeightUnit, IReadOnlyList<OfferInfo> Offers);
public sealed record PricedLine(int LineNo, int ProductId, string Name, string ProductNumber, int Quantity, decimal UnitPrice, decimal UnitPriceDiscount,
    int SpecialOfferId, string? OfferDescription, decimal LineTotal, decimal TaxAllocated, decimal FreightAllocated);
public sealed record Quote(List<PricedLine> Lines, decimal SubTotal, decimal Discount, TaxInfo? Tax, decimal TaxAmt, ShipMethodInfo ShipMethod,
    decimal WeightLb, decimal Freight, decimal TotalDue, string OfferDate);

/// <summary>C2-2 checkout pricing (replaces the Chapter 1 demo 8% tax / 2.5% freight). Pure and unit-tested; the inputs
/// come from CAT-10 (offers on the product partition), REF-02 (tax by ship-to state/province) and REF-04 (ship methods).
/// Money follows SQL Server: LineTotal = UnitPrice * (1 - UnitPriceDiscount) * OrderQty (numeric(38,6)); header
/// amounts are money (4 dp, midpoint away from zero). Allocation to lines is exactly what the Redshift fact build does
/// (warehouse/sql/star/03_facts.sql: header amount * line_total / sub_total, cast to decimal(19,4)).</summary>
public static class Pricing
{
    public const int NoDiscountOfferId = 1;
    public const decimal DefaultWeightLb = 1m;   // products without a weight ship as 1 lb
    private const decimal GramsPerLb = 453.59237m;

    public static decimal Money(decimal v) => Math.Round(v, 4, MidpointRounding.AwayFromZero);

    /// <summary>Best applicable offer for a line: active on the pricing date (inclusive), quantity within min/max, highest
    /// discount wins (ties: lowest id). Offer 1 (No Discount) applies when nothing else does, as in SQL Server.</summary>
    public static OfferInfo? BestOffer(IEnumerable<OfferInfo> offers, int qty, DateTime asOf) => offers
        .Where(o => o.Id != NoDiscountOfferId && o.DiscountPct > 0 && o.Start.Date <= asOf.Date && asOf.Date <= o.End.Date
                    && qty >= o.MinQty && (o.MaxQty is null || o.MaxQty == 0 || qty <= o.MaxQty))
        .OrderByDescending(o => o.DiscountPct).ThenBy(o => o.Id).FirstOrDefault();

    public static decimal WeightLb(decimal? weight, string? unit) => weight is not { } w || w <= 0 ? DefaultWeightLb
        : (unit ?? "").Trim().ToUpperInvariant() == "G" ? w / GramsPerLb : w;

    /// <summary>Freight = ShipBase + ShipRate * total weight in pounds (Purchasing.ShipMethod: "ShipRate = shipping charge per pound").</summary>
    public static decimal Freight(ShipMethodInfo m, decimal weightLb) => Money(m.ShipBase + m.ShipRate * weightLb);

    public static Quote Price(IReadOnlyList<PricingItem> items, TaxInfo? tax, ShipMethodInfo ship, DateTime offerDate)
    {
        var lines = new List<PricedLine>();
        var n = 1;
        decimal weight = 0, gross = 0;
        foreach (var i in items)
        {
            var offer = BestOffer(i.Offers, i.Quantity, offerDate);
            var disc = offer?.DiscountPct ?? 0m;
            var lineTotal = Math.Round(i.UnitPrice * (1m - disc) * i.Quantity, 6, MidpointRounding.AwayFromZero);
            gross += i.UnitPrice * i.Quantity;
            weight += WeightLb(i.Weight, i.WeightUnit) * i.Quantity;
            lines.Add(new PricedLine(n++, i.ProductId, i.Name, i.ProductNumber, i.Quantity, i.UnitPrice, disc, offer?.Id ?? NoDiscountOfferId,
                offer?.Description, lineTotal, 0, 0));
        }
        var sub = Money(lines.Sum(l => l.LineTotal));
        var taxAmt = Money(sub * (tax?.Rate ?? 0m));
        var freight = lines.Count == 0 ? 0 : Freight(ship, weight);
        lines = lines.Select(l => l with { TaxAllocated = Allocate(taxAmt, l.LineTotal, sub), FreightAllocated = Allocate(freight, l.LineTotal, sub) }).ToList();
        return new Quote(lines, sub, Money(gross) - sub, tax, taxAmt, ship, Math.Round(weight, 2), freight, sub + taxAmt + freight,
            offerDate.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture));
    }

    /// <summary>Same formula as the Redshift fact build (CASE WHEN sub_total = 0 THEN 0 ELSE amount * line_total / sub_total END).</summary>
    public static decimal Allocate(decimal amount, decimal lineTotal, decimal subTotal) => subTotal == 0 ? 0 : Money(amount * lineTotal / subTotal);

    /// <summary>Retail tax for a state/province from its SalesTaxRate rows: TaxType 1 (retail) wins over 3 (all sales);
    /// type 2 (wholesale) never applies to the web shop. Rates are stored as percentages (e.g. 14.00).</summary>
    public static decimal? RetailRate(IEnumerable<(int TaxType, decimal RatePct)> rates)
    {
        var list = rates.ToList();
        var pick = list.Where(r => r.TaxType == 1).Select(r => (decimal?)r.RatePct).Max() ?? list.Where(r => r.TaxType == 3).Select(r => (decimal?)r.RatePct).Max();
        return pick is { } p ? p / 100m : null;
    }
}

/// <summary>SalesOrderHeader.Status (ufnGetSalesOrderStatusText) and the C2-2 back-office transitions, enforced server-side.</summary>
public static class OrderStatus
{
    public const int InProcess = 1, Approved = 2, Backordered = 3, Rejected = 4, Shipped = 5, Cancelled = 6;

    public static string Text(int s) => s switch
    {
        1 => "In process", 2 => "Approved", 3 => "Backordered", 4 => "Rejected", 5 => "Shipped", 6 => "Cancelled", _ => "** Invalid **",
    };

    /// <summary>Statuses kept in the sparse ORDERSTATUS GSI (SAL-05): the open ones.</summary>
    public static bool IsOpen(int s) => s is >= 1 and <= 3;

    public static readonly IReadOnlyDictionary<string, (int[] From, int To)> Actions = new Dictionary<string, (int[], int)>
    {
        ["approve"] = (new[] { InProcess }, Approved),
        ["reject"] = (new[] { InProcess }, Rejected),
        ["backorder"] = (new[] { InProcess, Approved }, Backordered),
        ["ship"] = (new[] { Approved, Backordered }, Shipped),
        ["cancel"] = (new[] { InProcess, Approved, Backordered }, Cancelled),
    };

    public static bool CanApply(string action, int status) => Actions.TryGetValue(action, out var a) && a.From.Contains(status);

    public static string[] AllowedActions(int status) => Actions.Where(a => a.Value.From.Contains(status)).Select(a => a.Key).ToArray();
}
