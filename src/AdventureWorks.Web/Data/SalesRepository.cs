using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using AdventureWorks.Web.Models;

namespace AdventureWorks.Web.Data;

/// <summary>aw-sales (docs/design/tables/sales.md): cart (SAL-01), checkout (SAL-02), my orders (SAL-03), order (SAL-04).</summary>
public sealed class SalesRepository(DynamoTables t, TimeProvider clock)
{
    public const int MaxTransactActions = 100;
    /// <summary>P3-5: header + lines must fit one TransactWriteItems (100 actions) with a little headroom.</summary>
    public const int MaxOrderLines = 95;
    public static readonly TimeSpan CartTtl = TimeSpan.FromDays(7);   // D3
    public const decimal TaxRate = 0.08m, FreightRate = 0.025m;

    private IAmazonDynamoDB Db => t.For(DynamoTables.Sales);
    private string Table => t.Name(DynamoTables.Sales);
    private static Dictionary<string, AttributeValue> K(string pk, string sk) => new() { ["PK"] = Av.S(pk), ["SK"] = Av.S(sk) };

    // ---------------------------------------------------------------- SAL-01 cart (strong reads, D8; TTL 7 days, D3)

    public async Task<List<CartLine>> GetCartAsync(int customerId)
    {
        var items = await Db.QueryAll(new QueryRequest { TableName = Table, ConsistentRead = true, KeyConditionExpression = "PK = :pk",
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Cart(customerId)) } });
        var now = clock.GetUtcNow().ToUnixTimeSeconds();
        return items.Where(i => (i.Long("ttl") ?? long.MaxValue) > now)   // TTL deletes lazily; hide expired rows
            .Select(i => new CartLine(i.Int("product_id")!.Value, i.Str("product_name") ?? "", i.Str("product_number") ?? "", i.Dec("unit_price") ?? 0,
                i.Int("quantity") ?? 1, i.Date("date_created") ?? DateTime.MinValue)).ToList();
    }

    public async Task AddToCartAsync(int customerId, Product p, int qty)
    {
        var now = clock.GetUtcNow();
        await Db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = Table, Key = K(Keys.Cart(customerId), Keys.CartItem(p.Id)),
            UpdateExpression = "SET #t = :t, src = :src, shopping_cart_id = :cart, product_id = :p, product_name = :n, product_number = :pn, " +
                               "unit_price = :price, date_created = if_not_exists(date_created, :now), updated_at = :now, #ttl = :ttl ADD quantity :q, ver :one",
            ExpressionAttributeNames = new() { ["#t"] = "type", ["#ttl"] = "ttl" },
            ExpressionAttributeValues = new()
            {
                [":t"] = Av.S("CartItem"), [":src"] = Av.S("ddb"), [":cart"] = Av.S(customerId.ToString()), [":p"] = Av.N(p.Id), [":n"] = Av.S(p.Name),
                [":pn"] = Av.S(p.ProductNumber), [":price"] = Av.N(p.ListPrice), [":now"] = Av.S(Keys.Iso(now.UtcDateTime)),
                [":ttl"] = Av.N((now + CartTtl).ToUnixTimeSeconds()), [":q"] = Av.N(qty), [":one"] = Av.N(1),
            },
        });
    }

    public async Task SetQuantityAsync(int customerId, int productId, int qty)
    {
        if (qty <= 0) { await RemoveAsync(customerId, productId); return; }
        var now = clock.GetUtcNow();
        await Db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = Table, Key = K(Keys.Cart(customerId), Keys.CartItem(productId)), ConditionExpression = "attribute_exists(PK)",
            UpdateExpression = "SET quantity = :q, updated_at = :now, #ttl = :ttl ADD ver :one", ExpressionAttributeNames = new() { ["#ttl"] = "ttl" },
            ExpressionAttributeValues = new() { [":q"] = Av.N(qty), [":now"] = Av.S(Keys.Iso(now.UtcDateTime)), [":ttl"] = Av.N((now + CartTtl).ToUnixTimeSeconds()), [":one"] = Av.N(1) },
        });
    }

    public Task RemoveAsync(int customerId, int productId) =>
        Db.DeleteItemAsync(new DeleteItemRequest { TableName = Table, Key = K(Keys.Cart(customerId), Keys.CartItem(productId)) });

    // ---------------------------------------------------------------- SAL-02 checkout

    /// <summary>P3-1: one atomic counter increment per order; ids start at 1,000,000,000 (D5).</summary>
    public async Task<long> NextOrderIdAsync()
    {
        var r = await Db.UpdateItemAsync(new UpdateItemRequest
        {
            TableName = Table, Key = K("COUNTER", "ORDER"), UpdateExpression = "ADD next_id :one SET #t = if_not_exists(#t, :t), src = :src",
            ExpressionAttributeNames = new() { ["#t"] = "type" },
            ExpressionAttributeValues = new() { [":one"] = Av.N(1), [":t"] = Av.S("OrderIdCounter"), [":src"] = Av.S("ddb") },
            ReturnValues = ReturnValue.UPDATED_NEW,
        });
        var id = long.Parse(r.Attributes["next_id"].N);
        return id < Keys.NativeOrderIdStart ? Keys.NativeOrderIdStart + id : id;
    }

    public sealed record CheckoutPlan(List<TransactWriteItem> Transaction, List<Dictionary<string, AttributeValue>> CartKeysAfter);

    /// <summary>Builds the checkout writes: Put ORDER + Put LINE#n (+ Delete CART items while they fit in 100 actions;
    /// the rest of the cart is cleaned up right after the transaction - the SAL-02 compromise). Pure, unit-tested.</summary>
    public static CheckoutPlan Plan(string table, Order o, CustomerView c, string email, int customerId, DateTime now)
    {
        if (o.Lines.Count == 0) throw new InvalidOperationException("Cart is empty.");
        if (o.Lines.Count > MaxOrderLines) throw new InvalidOperationException($"An order can have at most {MaxOrderLines} lines (P3-5).");
        var pk = Keys.Order(o.Id);
        var h = Av.Item(pk, "ORDER", "Order");
        h["src_origin"] = Av.S("app-net10");
        h["sales_order_id"] = Av.N(o.Id); h["sales_order_number"] = Av.S(o.Number); h["revision_number"] = Av.N(1);
        h["order_date"] = Av.S(Keys.Iso(now)); h["due_date"] = Av.S(Keys.Iso(now.AddDays(12)));
        h["status"] = Av.N(o.Status); h["online_order_flag"] = Av.B(true);
        h["purchase_order_number"] = Av.S("DDB-" + now.ToString("yyyyMMddHHmmss"));
        h["customer_id"] = Av.N(customerId); h["customer_account_number"] = Av.S(c.AccountNumber); h["customer_name"] = Av.S(c.DisplayName);
        h.Set("store_name", c.StoreName); h["customer_email"] = Av.S(email);
        h["ship_method_id"] = Av.N(5); h["ship_method_name"] = Av.S("CARGO TRANSPORT 5");
        if (c.Addresses.FirstOrDefault() is { } a)
        {
            foreach (var pre in new[] { "ship_to", "bill_to" })
            {
                h[$"{pre}_address_id"] = Av.N(a.AddressId); h[$"{pre}_line1"] = Av.S(a.Line1); h.Set($"{pre}_line2", a.Line2);
                h[$"{pre}_city"] = Av.S(a.City); h[$"{pre}_state"] = Av.S(a.State); h[$"{pre}_postal_code"] = Av.S(a.PostalCode); h[$"{pre}_country"] = Av.S(a.Country);
            }
        }
        if (c.Cards.FirstOrDefault() is { } card) { h["credit_card_id"] = Av.N(card.CreditCardId); h["card_type"] = Av.S(card.CardType); h["card_last4"] = Av.S(card.Last4); }
        h["sub_total"] = Av.N(o.SubTotal); h["tax_amt"] = Av.N(o.TaxAmt); h["freight"] = Av.N(o.Freight); h["total_due"] = Av.N(o.TotalDue);
        h["GSI1PK"] = Av.S(Keys.Customer(customerId)); h["GSI1SK"] = Av.S(Keys.CustomerOrder(now, o.Id));
        h["GSI2PK"] = Av.S($"ORDERSTATUS#{o.Status}"); h["GSI2SK"] = Av.S(Keys.Iso(now));

        var tx = new List<TransactWriteItem> { new() { Put = new Put { TableName = table, Item = h, ConditionExpression = "attribute_not_exists(PK)" } } };
        foreach (var l in o.Lines)
        {
            var li = Av.Item(pk, Keys.OrderLine(l.LineNo), "OrderLine");
            li["sales_order_id"] = Av.N(o.Id); li["sales_order_detail_id"] = Av.N(l.LineNo); li["product_id"] = Av.N(l.ProductId);
            li["product_name"] = Av.S(l.Name); li.Set("product_number", l.ProductNumber); li["order_qty"] = Av.N(l.Quantity);
            li["unit_price"] = Av.N(l.UnitPrice); li["unit_price_discount"] = Av.N(0); li["line_total"] = Av.N(l.LineTotal); li["special_offer_id"] = Av.N(1);
            tx.Add(new TransactWriteItem { Put = new Put { TableName = table, Item = li } });
        }
        var after = new List<Dictionary<string, AttributeValue>>();
        foreach (var l in o.Lines)
        {
            var key = K(Keys.Cart(customerId), Keys.CartItem(l.ProductId));
            if (tx.Count < MaxTransactActions) tx.Add(new TransactWriteItem { Delete = new Delete { TableName = table, Key = key } });
            else after.Add(key);
        }
        return new CheckoutPlan(tx, after);
    }

    public static Order PriceOrder(long id, int customerId, IReadOnlyList<CartLine> cart, DateTime now)
    {
        var o = new Order { Id = id, Number = Keys.OrderNumber(id), CustomerId = customerId, OrderDate = now, Status = 1, Source = "ddb" };
        var n = 1;
        foreach (var c in cart) o.Lines.Add(new OrderLine(n++, c.ProductId, c.Name, c.ProductNumber, c.Quantity, c.UnitPrice, c.LineTotal));
        o.SubTotal = o.Lines.Sum(l => l.LineTotal);
        o.TaxAmt = Math.Round(o.SubTotal * TaxRate, 4);
        o.Freight = Math.Round(o.SubTotal * FreightRate, 4);
        o.TotalDue = o.SubTotal + o.TaxAmt + o.Freight;
        return o;
    }

    public async Task<Order> CheckoutAsync(int customerId, CustomerView customer, string email)
    {
        var cart = await GetCartAsync(customerId);
        if (cart.Count == 0) throw new InvalidOperationException("Cart is empty.");
        if (cart.Count > MaxOrderLines) throw new InvalidOperationException($"An order can have at most {MaxOrderLines} lines (P3-5).");
        var now = clock.GetUtcNow().UtcDateTime; now = now.AddTicks(-(now.Ticks % TimeSpan.TicksPerSecond));
        var order = PriceOrder(await NextOrderIdAsync(), customerId, cart, now);
        var plan = Plan(Table, order, customer, email, customerId, now);
        await Db.TransactWriteItemsAsync(new TransactWriteItemsRequest { TransactItems = plan.Transaction });
        foreach (var chunk in plan.CartKeysAfter.Chunk(25))
            await Db.BatchWriteItemAsync(new BatchWriteItemRequest { RequestItems = new() { [Table] = chunk.Select(k => new WriteRequest { DeleteRequest = new DeleteRequest { Key = k } }).ToList() } });
        return order;
    }

    // ---------------------------------------------------------------- SAL-03 / SAL-04

    public async Task<OrderPage> GetOrdersForCustomerAsync(int customerId, string? token, int pageSize = 20)
    {
        var r = await Db.QueryAsync(new QueryRequest
        {
            TableName = Table, IndexName = "GSI1", KeyConditionExpression = "GSI1PK = :pk AND begins_with(GSI1SK, :o)", ScanIndexForward = false,
            Limit = pageSize, ExclusiveStartKey = Paging.Decode(token),
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Customer(customerId)), [":o"] = Av.S("ORDER#") },
        });
        return new OrderPage((r.Items ?? new()).Where(i => i.IsLive()).Select(ToOrder).ToList(), Paging.Encode(r.LastEvaluatedKey));
    }

    public async Task<Order?> GetOrderAsync(long id, bool consistent)
    {
        var items = await Db.QueryAll(new QueryRequest { TableName = Table, ConsistentRead = consistent, KeyConditionExpression = "PK = :pk",
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Order(id)) } });
        var head = items.FirstOrDefault(i => i.Str("SK") == "ORDER" && i.IsLive());
        if (head is null) return null;
        var o = ToOrder(head);
        foreach (var l in items.Where(i => i.Str("type") == "OrderLine" && i.IsLive()).OrderBy(i => i.Int("sales_order_detail_id")))
            o.Lines.Add(new OrderLine(l.Int("sales_order_detail_id")!.Value, l.Int("product_id")!.Value, l.Str("product_name") ?? "", l.Str("product_number"),
                l.Int("order_qty") ?? 0, l.Dec("unit_price") ?? 0, l.Dec("line_total") ?? 0));
        return o;
    }

    private static Order ToOrder(Dictionary<string, AttributeValue> h) => new()
    {
        Id = h.Long("sales_order_id")!.Value, Number = h.Str("sales_order_number") ?? Keys.OrderNumber(h.Long("sales_order_id")!.Value),
        CustomerId = h.Int("customer_id") ?? 0, OrderDate = h.Date("order_date") ?? DateTime.MinValue, Status = h.Int("status") ?? 0,
        SubTotal = h.Dec("sub_total") ?? 0, TaxAmt = h.Dec("tax_amt") ?? 0, Freight = h.Dec("freight") ?? 0, TotalDue = h.Dec("total_due") ?? 0,
        ShipTo = h.Str("ship_to_line1") is { } l1 ? $"{l1}, {h.Str("ship_to_city")} {h.Str("ship_to_state")} {h.Str("ship_to_postal_code")}" : null,
        Source = h.Str("src") ?? "sql",
    };
}
