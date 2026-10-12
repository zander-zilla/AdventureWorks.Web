namespace AdventureWorks.Web.Models;

public sealed record Category(int Id, string Name, List<Subcategory> Subcategories);
public sealed record Subcategory(int Id, int CategoryId, string Name, string? CategoryName);

public sealed class Product
{
    public int Id { get; set; }
    public string Name { get; set; } = "";
    public string ProductNumber { get; set; } = "";
    public string? Color { get; set; }
    public string? Size { get; set; }
    public decimal ListPrice { get; set; }
    public decimal StandardCost { get; set; }
    public int? SubcategoryId { get; set; }
    public string? SubcategoryName { get; set; }
    public int? CategoryId { get; set; }
    public string? CategoryName { get; set; }
    public int? ModelId { get; set; }
    public string? ModelName { get; set; }
    public decimal? Weight { get; set; }
    public DateTime? SellStartDate { get; set; }
    public DateTime? SellEndDate { get; set; }
    public decimal StockQty { get; set; }
    public bool Active { get; set; } = true;
    public string? ThumbnailFileName { get; set; }
    public long Version { get; set; }
    public string Source { get; set; } = "ddb";
}

public sealed record ProductSummary(int Id, string Name, string ProductNumber, decimal ListPrice, bool Active);
public sealed record ModelDescription(string Culture, string Text);
public sealed record ProductPage(List<ProductSummary> Items, string? Next);

public sealed record Address(string Line1, string? Line2, string City, string State, string PostalCode, string Country, int AddressId);
public sealed record Card(int CreditCardId, string CardType, string Last4);

public sealed class CustomerView
{
    public int CustomerId { get; set; }
    public int OwnerId { get; set; }
    public string AccountNumber { get; set; } = "";
    public string DisplayName { get; set; } = "";
    public string? StoreName { get; set; }
    public int? StoreId { get; set; }
    public string? TerritoryName { get; set; }
    public string? Title { get; set; }
    public string? FirstName { get; set; }
    public string? MiddleName { get; set; }
    public string? LastName { get; set; }
    public List<string> Emails { get; } = new();
    public List<string> Phones { get; } = new();
    public List<Address> Addresses { get; } = new();
    public List<Card> Cards { get; } = new();
}

public sealed record CustomerSummary(int CustomerId, string DisplayName, string AccountNumber, string? StoreName, string? TerritoryName);
public sealed record CustomerPage(List<CustomerSummary> Items, string? Next);

public sealed record LoginResult(int CustomerId, int PersonId, string DisplayName, string Email);

public sealed record CartLine(int ProductId, string Name, string ProductNumber, decimal UnitPrice, int Quantity, DateTime Added)
{
    public decimal LineTotal => UnitPrice * Quantity;
}

public sealed record OrderLine(int LineNo, int ProductId, string Name, string? ProductNumber, int Quantity, decimal UnitPrice, decimal LineTotal);

public sealed class Order
{
    public long Id { get; set; }
    public string Number { get; set; } = "";
    public int CustomerId { get; set; }
    public DateTime OrderDate { get; set; }
    public int Status { get; set; }
    public decimal SubTotal { get; set; }
    public decimal TaxAmt { get; set; }
    public decimal Freight { get; set; }
    public decimal TotalDue { get; set; }
    public string? ShipTo { get; set; }
    public string Source { get; set; } = "sql";
    public List<OrderLine> Lines { get; } = new();
    public static string StatusName(int s) => s switch { 1 => "In process", 2 => "Approved", 3 => "Backordered", 4 => "Rejected", 5 => "Shipped", 6 => "Cancelled", _ => s.ToString() };
}

public sealed record OrderPage(List<Order> Items, string? Next);
