using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using AdventureWorks.Web.Models;

namespace AdventureWorks.Web.Data;

/// <summary>aw-customer (docs/design/tables/customer.md). Strong reads only for login (D8).</summary>
public sealed class CustomerRepository(DynamoTables t)
{
    private IAmazonDynamoDB Db => t.For(DynamoTables.Customer);
    private string Table => t.Name(DynamoTables.Customer);

    // CUS-01: login. GetItem EMAIL#<email> then Query BE#<id>, both ConsistentRead (D8).
    public async Task<LoginResult?> FindLoginAsync(string email)
    {
        var e = await Db.GetItemAsync(new GetItemRequest { TableName = Table, ConsistentRead = true,
            Key = new() { ["PK"] = Av.S(Keys.Email(email)), ["SK"] = Av.S("EMAIL") } });
        if (e.Item is not { Count: > 0 } ei || !ei.IsLive()) return null;
        var be = ei.Int("business_entity_id")!.Value;
        var items = await Db.QueryAll(new QueryRequest { TableName = Table, ConsistentRead = true, KeyConditionExpression = "PK = :pk",
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Be(be)) } });
        var cust = items.FirstOrDefault(i => i.Str("type") == "Customer" && i.IsLive());
        var person = items.FirstOrDefault(i => i.Str("SK") == "PERSON");
        if (cust is null) return null;
        var name = person is null ? cust.Str("display_name")! : $"{person.Str("first_name")} {person.Str("last_name")}";
        return new LoginResult(cust.Int("customer_id")!.Value, be, name, email.Trim().ToLowerInvariant());
    }

    // CUS-02: customer by id (GSI1) then the owner's collection (+ store addresses for store contacts).
    public async Task<CustomerView?> GetCustomerAsync(int customerId)
    {
        var r = await Db.QueryAsync(new QueryRequest { TableName = Table, IndexName = "GSI1", KeyConditionExpression = "GSI1PK = :pk",
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Customer(customerId)) } });
        var c = r.Items?.FirstOrDefault(i => i.IsLive());
        if (c is null) return null;
        var v = new CustomerView
        {
            CustomerId = customerId, OwnerId = int.Parse(c.Str("PK")![3..]), AccountNumber = c.Str("account_number") ?? "",
            DisplayName = c.Str("display_name") ?? "", StoreName = c.Str("store_name"), StoreId = c.Int("store_id"), TerritoryName = c.Str("territory_name"),
        };
        Fill(v, await Collection(v.OwnerId));
        if (v.Addresses.Count == 0 && v.StoreId is { } s) Fill(v, (await Collection(s)).Where(i => i.Str("type") == "PartyAddress").ToList());
        return v;
    }

    private Task<List<Dictionary<string, AttributeValue>>> Collection(int be) => Db.QueryAll(new QueryRequest { TableName = Table,
        KeyConditionExpression = "PK = :pk", ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Be(be)) } });

    private static void Fill(CustomerView v, List<Dictionary<string, AttributeValue>> items)
    {
        foreach (var i in items.Where(i => i.IsLive()))
        {
            switch (i.Str("type"))
            {
                case "Person": v.Title = i.Str("title"); v.FirstName = i.Str("first_name"); v.MiddleName = i.Str("middle_name"); v.LastName = i.Str("last_name"); break;
                case "EmailAddress": v.Emails.Add(i.Str("email_address")!); break;
                case "Phone": v.Phones.Add($"{i.Str("phone_number")} ({i.Str("phone_type")})"); break;
                case "PartyAddress":
                    v.Addresses.Add(new Address(i.Str("address_line1") ?? "", i.Str("address_line2"), i.Str("city") ?? "", i.Str("state_province_code")?.Trim() ?? "",
                        i.Str("postal_code") ?? "", i.Str("country_region_code") ?? "", i.Int("address_id") ?? 0));
                    break;
                case "PartyCard": v.Cards.Add(new Card(i.Int("credit_card_id")!.Value, i.Str("card_type") ?? "", i.Str("card_last4") ?? "")); break;
            }
        }
    }

    // CUS-05: admin grid sorted by last name (GSI2 CUSTOMERS), paged.
    public async Task<CustomerPage> ListAsync(string? token, int pageSize = 25)
    {
        var r = await Db.QueryAsync(new QueryRequest { TableName = Table, IndexName = "GSI2", KeyConditionExpression = "GSI2PK = :pk", Limit = pageSize,
            ExpressionAttributeValues = new() { [":pk"] = Av.S("CUSTOMERS") }, ExclusiveStartKey = Paging.Decode(token) });
        var items = (r.Items ?? new()).Where(i => i.IsLive()).Select(i => new CustomerSummary(i.Int("customer_id")!.Value, i.Str("display_name") ?? "",
            i.Str("account_number") ?? "", i.Str("store_name"), i.Str("territory_name"))).ToList();
        return new CustomerPage(items, Paging.Encode(r.LastEvaluatedKey));
    }

    /// <summary>Admin edit of a person customer's name: PERSON item + the customer item's display copies, one transaction
    /// (the app owns both items; ver-checked on the person).</summary>
    public async Task UpdateNameAsync(int customerId, string? title, string first, string? middle, string last)
    {
        var v = await GetCustomerAsync(customerId) ?? throw new KeyNotFoundException();
        if (v.FirstName is null) throw new InvalidOperationException("Store customers are renamed via the store.");
        var pk = Av.S(Keys.Be(v.OwnerId));
        var display = $"{first} {last}";
        var tx = new List<TransactWriteItem>
        {
            new() { Update = new Update { TableName = Table, Key = new() { ["PK"] = pk, ["SK"] = Av.S("PERSON") },
                UpdateExpression = PersonUpdate(middle, title),
                ConditionExpression = "attribute_exists(PK)",
                ExpressionAttributeValues = Vals(("f", first), ("l", last), ("m", middle), ("t", title)) } },
            new() { Update = new Update { TableName = Table, Key = new() { ["PK"] = pk, ["SK"] = Av.S(Keys.Customer(customerId)) },
                UpdateExpression = "SET display_name = :d, GSI2SK = :s, updated_at = :u, src = :src ADD ver :one", ConditionExpression = "attribute_exists(PK)",
                ExpressionAttributeValues = Vals(("d", display), ("s", $"{last.ToUpperInvariant()}, {first.ToUpperInvariant()}#{customerId:000000}")) } },
        };
        await Db.TransactWriteItemsAsync(new TransactWriteItemsRequest { TransactItems = tx });
    }

    public static string PersonUpdate(string? middle, string? title)
    {
        var sets = new List<string> { "first_name = :f", "last_name = :l", "updated_at = :u", "src = :src" };
        var removes = new List<string>();
        if (middle is null) removes.Add("middle_name"); else sets.Add("middle_name = :m");
        if (title is null) removes.Add("title"); else sets.Add("title = :t");
        return "SET " + string.Join(", ", sets) + (removes.Count > 0 ? " REMOVE " + string.Join(", ", removes) : "") + " ADD ver :one";
    }

    private static Dictionary<string, AttributeValue> Vals(params (string k, string? v)[] kv)
    {
        var d = new Dictionary<string, AttributeValue> { [":u"] = Av.S(DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")), [":src"] = Av.S("ddb"), [":one"] = Av.N(1) };
        foreach (var (k, v) in kv) if (v is not null) d[":" + k] = Av.S(v);
        return d;
    }

    /// <summary>CUS-04: new individual customer: BE + PERSON + CUSTOMER + EMAIL items, unique email, ids from a counter.</summary>
    public async Task<int> CreateAsync(string? title, string first, string? middle, string last, string email)
    {
        var r = await Db.UpdateItemAsync(new UpdateItemRequest { TableName = Table, Key = new() { ["PK"] = Av.S("COUNTER"), ["SK"] = Av.S("CUSTOMER") },
            UpdateExpression = "SET #t = :t ADD next_id :one", ExpressionAttributeNames = new() { ["#t"] = "type" },
            ExpressionAttributeValues = new() { [":one"] = Av.N(1), [":t"] = Av.S("CustomerIdCounter") }, ReturnValues = ReturnValue.UPDATED_NEW });
        var n = (int)decimal.Parse(r.Attributes["next_id"].N);
        int be = 900_000 + n, cid = 900_000 + n;   // above SQL's ranges (BusinessEntityID < 21k, CustomerID < 31k)
        string pk = Keys.Be(be);
        var beItem = Av.Item(pk, "BE", "BusinessEntity"); beItem["business_entity_id"] = Av.N(be);
        var person = Av.Item(pk, "PERSON", "Person"); person["business_entity_id"] = Av.N(be); person["person_type"] = Av.S("IN");
        person["first_name"] = Av.S(first); person["last_name"] = Av.S(last); person.Set("middle_name", middle); person.Set("title", title);
        person["name_style"] = Av.B(false); person["email_promotion"] = Av.N(0);
        var cust = Av.Item(pk, Keys.Customer(cid), "Customer"); cust["customer_id"] = Av.N(cid); cust["person_id"] = Av.N(be);
        cust["account_number"] = Av.S($"AW{cid:00000000}"); cust["display_name"] = Av.S($"{first} {last}");
        cust["GSI1PK"] = Av.S(Keys.Customer(cid)); cust["GSI1SK"] = Av.S("CUSTOMER");
        cust["GSI2PK"] = Av.S("CUSTOMERS"); cust["GSI2SK"] = Av.S($"{last.ToUpperInvariant()}, {first.ToUpperInvariant()}#{cid:000000}");
        var mail = Av.Item(pk, $"EMAIL#{n:000000}", "EmailAddress"); mail["business_entity_id"] = Av.N(be); mail["email_address"] = Av.S(email.Trim());
        var login = Av.Item(Keys.Email(email), "EMAIL", "EmailLogin"); login["business_entity_id"] = Av.N(be); login["derived"] = Av.B(true);
        await Db.TransactWriteItemsAsync(new TransactWriteItemsRequest { TransactItems = new[] { beItem, person, cust, mail, login }
            .Select(i => new TransactWriteItem { Put = new Put { TableName = Table, Item = i, ConditionExpression = "attribute_not_exists(PK)" } }).ToList() });
        return cid;
    }
}
