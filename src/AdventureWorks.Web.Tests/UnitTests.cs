using AdventureWorks.Web.Data;
using AdventureWorks.Web.Models;

namespace AdventureWorks.Web.Tests;

public class KeyTests
{
    [Fact] public void Templates_match_the_mapping()
    {
        Assert.Equal("PRODUCT#000680", Keys.Product(680));
        Assert.Equal("CATALOG", "CATALOG");
        Assert.Equal("CAT#0001#SUB#0002", Keys.Subcategory(1, 2));
        Assert.Equal("SUBCAT#0014", Keys.SubcatGsi(14));
        Assert.Equal("MODEL#0006", Keys.Model(6));
        Assert.Equal("EMAIL#catherine0@adventure-works.com", Keys.Email(" Catherine0@Adventure-Works.com "));
        Assert.Equal("CUSTOMER#029485", Keys.Customer(29485));
        Assert.Equal("ORDER#0000043659", Keys.Order(43659));
        Assert.Equal("ORDER#1000000001", Keys.Order(1_000_000_001));
        Assert.Equal("LINE#0000001", Keys.OrderLine(1));
        Assert.Equal("ORDER#2026-10-11T20:00:00#1000000001", Keys.CustomerOrder(new DateTime(2026, 10, 11, 20, 0, 0), 1_000_000_001));
    }

    [Theory]
    [InlineData(43659L, "SO43659")]
    [InlineData(1_000_000_007L, "SO-DDB-1000000007")]
    public void Order_numbers_carry_the_source_prefix(long id, string number)
    {
        Assert.Equal(number, Keys.OrderNumber(id));
        Assert.Equal(id, Keys.ParseOrderNumber(number));
    }
}

public class CheckoutTests
{
    private static readonly DateTime Now = new(2026, 10, 11, 20, 0, 0, DateTimeKind.Utc);

    private static List<CartLine> Cart(int n) => Enumerable.Range(1, n).Select(i => new CartLine(i, $"P{i}", $"PN-{i}", 10m, 2, Now)).ToList();

    private static CustomerView Customer()
    {
        var c = new CustomerView { CustomerId = 29485, AccountNumber = "AW00029485", DisplayName = "Catherine Abel", StoreName = "Professional Sales and Service" };
        c.Addresses.Add(new Address("57251 Serene Blvd", null, "Van Nuys", "CA", "91411", "US", 1086));
        c.Cards.Add(new Card(17038, "Distinguish", "9047"));
        return c;
    }

    private static readonly ShipMethodInfo Truck = new(1, "XRQ - TRUCK GROUND", 3.95m, 0.99m);
    private static readonly TaxInfo Wa = new(79, "WA", "Washington", 1, 0.088m, "Washington State Sales Tax");

    private static Order PriceOrder(long id, int customerId, List<CartLine> cart, DateTime now) =>
        SalesRepository.BuildOrder(id, customerId, Pricing.Price(cart.Select(c => new PricingItem(c.ProductId, c.Name, c.ProductNumber, c.Quantity, c.UnitPrice, null, null, [])).ToList(),
            Wa, Truck, new DateTime(2014, 5, 1)), now);

    [Fact] public void Prices_with_real_tax_and_freight()
    {
        var o = PriceOrder(1_000_000_001, 29485, Cart(3), Now);
        Assert.Equal(60m, o.SubTotal); Assert.Equal(5.28m, o.TaxAmt);          // 8.8 % Washington
        Assert.Equal(3.95m + 0.99m * 6, o.Freight);                              // base + rate x 6 units x 1 lb default
        Assert.Equal(o.SubTotal + o.TaxAmt + o.Freight, o.TotalDue);
        Assert.Equal("SO-DDB-1000000001", o.Number);
        Assert.Equal(1, o.ShipMethodId); Assert.Equal(1, o.TerritoryId);
    }

    [Fact] public void Small_order_is_one_transaction_with_cart_cleanup()
    {
        var o = PriceOrder(1_000_000_001, 29485, Cart(3), Now);
        var plan = SalesRepository.Plan("aw-sales", o, Customer(), "c@x", 29485, Now);
        Assert.Equal(1 + 3 + 2 + 3, plan.Transaction.Count);   // header + lines + event + change feed + cart deletes
        Assert.Empty(plan.CartKeysAfter);
        var h = plan.Transaction[0].Put;
        Assert.Equal("attribute_not_exists(PK)", h.ConditionExpression);
        Assert.Equal("ORDER#1000000001", h.Item["PK"].S);
        Assert.Equal("CUSTOMER#029485", h.Item["GSI1PK"].S);
        Assert.Equal("ORDERSTATUS#1", h.Item["GSI2PK"].S);
        Assert.Equal("2026-10-11T20:00:00#1000000001", h.Item["GSI2SK"].S);
        Assert.Equal(Keys.AppLsn, h.Item["src_lsn"].S);
        Assert.Equal("ChangeFeed", plan.Transaction[5].Put.Item["type"].S);
        Assert.Equal("ddb", h.Item["src"].S);
        Assert.Equal("Van Nuys", h.Item["ship_to_city"].S);
        Assert.Equal("CART#29485", plan.Transaction[^1].Delete.Key["PK"].S);
    }

    [Fact] public void Large_order_moves_cart_cleanup_out_of_the_transaction()
    {
        var o = PriceOrder(1_000_000_002, 29485, Cart(95), Now);
        var plan = SalesRepository.Plan("aw-sales", o, Customer(), "c@x", 29485, Now);
        Assert.Equal(SalesRepository.MaxTransactActions, plan.Transaction.Count);
        Assert.Equal(95 - 2, plan.CartKeysAfter.Count);
    }

    [Fact] public void More_than_95_lines_is_rejected()
    {
        var o = PriceOrder(1_000_000_003, 29485, Cart(96), Now);
        Assert.Throws<InvalidOperationException>(() => SalesRepository.Plan("aw-sales", o, Customer(), "c@x", 29485, Now));
    }
}

public class MiscTests
{
    [Fact] public void Person_update_removes_cleared_attributes()
    {
        Assert.Equal("SET first_name = :f, last_name = :l, updated_at = :u, src = :src REMOVE middle_name, title ADD ver :one", CustomerRepository.PersonUpdate(null, null));
        Assert.Contains("middle_name = :m", CustomerRepository.PersonUpdate("R.", null));
    }

    [Fact] public void Page_tokens_round_trip()
    {
        var k = new Dictionary<string, Amazon.DynamoDBv2.Model.AttributeValue> { ["PK"] = Av.S("PRODUCTNAMES"), ["SK"] = Av.S("chain") };
        var back = Paging.Decode(Paging.Encode(k))!;
        Assert.Equal("chain", back["SK"].S);
        Assert.Null(Paging.Decode("not base64!"));
    }
}
