using System.Globalization;
using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using Amazon.Runtime;

namespace AdventureWorks.Web.Data;

/// <summary>DynamoDB options. In AWS only Region is set; locally ServiceUrl (one DynamoDB Local) or
/// Endpoints:{table} (one DynamoDB Local per table, as the Phase 3 loader runs them).</summary>
public sealed class DynamoOptions
{
    public string Region { get; set; } = "us-east-1";
    public string? ServiceUrl { get; set; }
    public Dictionary<string, string> Endpoints { get; set; } = new();
    public string TablePrefix { get; set; } = "";
}

/// <summary>Routes each domain table to its client (one per endpoint).</summary>
public sealed class DynamoTables
{
    public const string Catalog = "aw-catalog", Customer = "aw-customer", Sales = "aw-sales", Inventory = "aw-inventory", Reference = "aw-reference",
        Purchasing = "aw-purchasing";
    private readonly DynamoOptions _o;
    private readonly Dictionary<string, IAmazonDynamoDB> _clients = new();
    private readonly Func<string?, IAmazonDynamoDB> _factory;

    public DynamoTables(DynamoOptions o, Func<string?, IAmazonDynamoDB>? factory = null)
    {
        _o = o;
        _factory = factory ?? (url =>
        {
            var cfg = new AmazonDynamoDBConfig();
            if (url is null) { cfg.RegionEndpoint = Amazon.RegionEndpoint.GetBySystemName(o.Region); return new AmazonDynamoDBClient(cfg); }
            cfg.ServiceURL = url; cfg.AuthenticationRegion = o.Region;
            return new AmazonDynamoDBClient(new BasicAWSCredentials("local", "local"), cfg);
        });
    }

    public string Name(string table) => _o.TablePrefix + table;

    private string EndpointKey(string table) => (_o.Endpoints.TryGetValue(table, out var e) ? e : _o.ServiceUrl) ?? "aws";

    /// <summary>C2-2: one logical write across domain tables. In AWS (and with one local endpoint) this is ONE
    /// TransactWriteItems (tables in the same account and region). DynamoDB Local in the Chapter 1 layout runs one
    /// instance per table, and a transaction cannot span instances: the actions are then grouped per endpoint and
    /// applied in first-seen order (callers put the group whose conditions are most likely to fail first). Local only;
    /// see docs/chapter-2/PLAN.md, C2-2 as built.</summary>
    public async Task TransactAsync(IReadOnlyList<(string Table, TransactWriteItem Action)> actions, string? idempotencyToken = null)
    {
        var groups = actions.GroupBy(a => EndpointKey(a.Table)).ToList();
        foreach (var g in groups)
            await For(g.First().Table).TransactWriteItemsAsync(new TransactWriteItemsRequest
            {
                TransactItems = g.Select(a => a.Action).ToList(),
                ClientRequestToken = groups.Count == 1 ? idempotencyToken : null,
            });
    }

    /// <summary>True when all the given tables share one endpoint (a single atomic transaction).</summary>
    public bool SingleEndpoint(params string[] tables) => tables.Select(EndpointKey).Distinct().Count() == 1;

    public IAmazonDynamoDB For(string table)
    {
        var url = _o.Endpoints.TryGetValue(table, out var e) ? e : _o.ServiceUrl;
        var key = url ?? "aws";
        lock (_clients)
        {
            if (!_clients.TryGetValue(key, out var c)) _clients[key] = c = _factory(url);
            return c;
        }
    }
}

/// <summary>Key templates from design/mapping (docs/design/tables/*.md).</summary>
public static class Keys
{
    public static string Product(int id) => $"PRODUCT#{id:000000}";
    public static string Model(int id) => $"MODEL#{id:0000}";
    public static string Category(int id) => $"CAT#{id:0000}";
    public static string Subcategory(int cat, int sub) => $"CAT#{cat:0000}#SUB#{sub:0000}";
    public static string SubcatGsi(int sub) => $"SUBCAT#{sub:0000}";
    public static string ProductNumber(string n) => $"PRODUCTNUMBER#{n}";
    public static string Be(int id) => $"BE#{id:000000}";
    public static string Email(string e) => $"EMAIL#{e.Trim().ToLowerInvariant()}";
    public static string Customer(int id) => $"CUSTOMER#{id:000000}";
    public static string Cart(int customerId) => $"CART#{customerId}";
    public static string CartItem(int productId) => $"ITEM#{productId:000000}";
    public static string Order(long id) => $"ORDER#{id:0000000000}";
    public static string OrderLine(int n) => $"LINE#{n:0000000}";
    public static string CustomerOrder(DateTime orderDate, long id) => $"ORDER#{Iso(orderDate)}#{id:0000000000}";
    public static string InvProduct(int id) => Product(id);
    public static string Txn(DateTime d, long id) => $"TXN#{Iso(d)}#{id:000000}";
    public static string Review(DateTime d, int id) => $"REVIEW#{Iso(d)}#{id:00000}";
    public static string Price(DateTime start) => $"PRICE#{Iso(start)}";
    public static string OrderEvent(DateTime d, int seq) => $"EVENT#{Iso(d)}#{seq:000}";
    public static string Vendor(int id) => $"VENDOR#{id:000000}";
    public static string Po(int id) => $"PO#{id:000000}";
    public static string PoLine(int detailId) => $"LINE#{detailId:000000}";
    public static string PoStatus(int status) => $"POSTATUS#{status}";
    public static string PoIndexSk(DateTime orderDate, int id) => $"{Iso(orderDate)}#{id:000000}";
    public static string Employee(int id) => $"EMPLOYEE#{id:000000}";
    /// <summary>C2-3: DynamoDB-native purchase orders (and their lines) are numbered from 100,000 (SQL: 1..4,012 / 1..8,845)
    /// and shown as PO-DDB-n, like the D5 rule for sales orders.</summary>
    public const int NativePoIdStart = 100_000;
    public static string PoNumber(int id) => id >= NativePoIdStart ? $"PO-DDB-{id}" : $"PO{id:000000}";
    public static string Feed(DateTime d) => "FEED#" + d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    /// <summary>C2-2 origin marker: app-owned items get src_lsn = AppLsn, which sorts after every SQL LSN ("0x..."), so the
    /// one-way SQL -> DynamoDB CDC (conditional on src_lsn &lt; position, ADR 0003) never overwrites an app write.</summary>
    public const string AppLsn = "~app";
    public static string Iso(DateTime d) => d.ToString("yyyy-MM-dd'T'HH:mm:ss", CultureInfo.InvariantCulture);

    /// <summary>D5: DynamoDB-native orders are numbered from 1,000,000,000 and carry the SO-DDB- prefix.</summary>
    public const long NativeOrderIdStart = 1_000_000_000;
    public static string OrderNumber(long id) => id >= NativeOrderIdStart ? $"SO-DDB-{id}" : $"SO{id}";

    public static long? ParseOrderNumber(string s)
    {
        s = s.Trim().ToUpperInvariant();
        var digits = s.StartsWith("SO-DDB-") ? s[7..] : s.StartsWith("SO") ? s[2..] : s;
        return long.TryParse(digits, out var n) ? n : null;
    }
}

/// <summary>AttributeValue helpers.</summary>
public static class Av
{
    public static AttributeValue S(string v) => new() { S = v };
    public static AttributeValue N(decimal v) => new() { N = v.ToString(CultureInfo.InvariantCulture) };
    public static AttributeValue N(long v) => new() { N = v.ToString(CultureInfo.InvariantCulture) };
    public static AttributeValue B(bool v) => new() { BOOL = v };

    public static string? Str(this Dictionary<string, AttributeValue> i, string k) => i.TryGetValue(k, out var v) && v.S != null ? v.S : null;
    public static decimal? Dec(this Dictionary<string, AttributeValue> i, string k) =>
        i.TryGetValue(k, out var v) && v.N != null ? decimal.Parse(v.N, CultureInfo.InvariantCulture) : null;
    public static int? Int(this Dictionary<string, AttributeValue> i, string k) => i.Dec(k) is { } d ? (int)d : null;
    public static long? Long(this Dictionary<string, AttributeValue> i, string k) => i.Dec(k) is { } d ? (long)d : null;
    public static bool? Bool(this Dictionary<string, AttributeValue> i, string k) => i.TryGetValue(k, out var v) && v.IsBOOLSet ? v.BOOL : null;
    public static DateTime? Date(this Dictionary<string, AttributeValue> i, string k) =>
        i.Str(k) is { } s && DateTime.TryParse(s.TrimEnd('Z'), CultureInfo.InvariantCulture, DateTimeStyles.None, out var d) ? d : null;
    public static bool IsLive(this Dictionary<string, AttributeValue> i) => !(i.Bool("deleted") ?? false);

    /// <summary>Meta attributes every app-written item carries (ADR 0002): type, ver, src=ddb, updated_at.</summary>
    public static Dictionary<string, AttributeValue> Item(string pk, string sk, string type, long ver = 1) => new()
    {
        ["PK"] = S(pk), ["SK"] = S(sk), ["type"] = S(type), ["ver"] = N(ver), ["src"] = S("ddb"),
        ["updated_at"] = S(DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture)),
    };

    public static void Set(this Dictionary<string, AttributeValue> i, string k, string? v) { if (v is null) i.Remove(k); else i[k] = S(v); }
    public static void Set(this Dictionary<string, AttributeValue> i, string k, decimal? v) { if (v is null) i.Remove(k); else i[k] = N(v.Value); }

    public static async Task<List<Dictionary<string, AttributeValue>>> QueryAll(this IAmazonDynamoDB db, QueryRequest q, int max = int.MaxValue)
    {
        var all = new List<Dictionary<string, AttributeValue>>();
        do
        {
            var r = await db.QueryAsync(q);
            all.AddRange(r.Items ?? new());
            q.ExclusiveStartKey = r.LastEvaluatedKey is { Count: > 0 } ? r.LastEvaluatedKey : null;
        } while (q.ExclusiveStartKey != null && all.Count < max);
        return all;
    }
}
