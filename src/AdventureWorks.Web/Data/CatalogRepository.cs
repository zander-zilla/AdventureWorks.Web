using Amazon.DynamoDBv2;
using Amazon.DynamoDBv2.Model;
using AdventureWorks.Web.Models;

namespace AdventureWorks.Web.Data;

/// <summary>aw-catalog (docs/design/tables/catalog.md). Reads are eventually consistent (D8).</summary>
public sealed class CatalogRepository(DynamoTables t)
{
    public static readonly string[] Cultures = ["en", "fr", "ar", "he", "th", "zh-cht"];
    private IAmazonDynamoDB Db => t.For(DynamoTables.Catalog);
    private string Table => t.Name(DynamoTables.Catalog);

    private QueryRequest Q(string expr, Dictionary<string, AttributeValue> values, string? index = null) => new()
    {
        TableName = Table, IndexName = index, KeyConditionExpression = expr, ExpressionAttributeValues = values,
    };

    // CAT-01: whole category tree, one Query.
    public async Task<List<Category>> GetCategoryTreeAsync()
    {
        var items = await Db.QueryAll(Q("PK = :pk", new() { [":pk"] = Av.S("CATALOG") }));
        var cats = new List<Category>();
        foreach (var i in items.Where(x => x.IsLive()))
        {
            if (i.Str("type") == "Category") cats.Add(new Category(i.Int("product_category_id")!.Value, i.Str("name")!, new()));
            else if (i.Str("type") == "Subcategory" && cats.LastOrDefault() is { } c && c.Id == i.Int("product_category_id"))
                c.Subcategories.Add(ToSub(i));
        }
        return cats;
    }

    private static Subcategory ToSub(Dictionary<string, AttributeValue> i) =>
        new(i.Int("product_subcategory_id")!.Value, i.Int("product_category_id")!.Value, i.Str("name")!, i.Str("category_name"));

    // CAT-02: subcategory by id (GSI1 #META).
    public async Task<Subcategory?> GetSubcategoryAsync(int id)
    {
        var r = await Db.QueryAsync(Q("GSI1PK = :pk AND GSI1SK = :sk", new() { [":pk"] = Av.S(Keys.SubcatGsi(id)), [":sk"] = Av.S("#META") }, "GSI1"));
        return r.Items?.Where(x => x.IsLive()).Select(ToSub).FirstOrDefault();
    }

    // CAT-03: active products of a subcategory, name order (key order).
    public async Task<List<Product>> GetProductsBySubcategoryAsync(int subId)
    {
        var items = await Db.QueryAll(Q("GSI1PK = :pk AND begins_with(GSI1SK, :p)",
            new() { [":pk"] = Av.S(Keys.SubcatGsi(subId)), [":p"] = Av.S("PRODUCT#A#") }, "GSI1"));
        return items.Where(x => x.IsLive()).Select(ToProduct).ToList();
    }

    // CAT-04: product + its collection (photos, offers, ...) in one Query.
    public async Task<Product?> GetProductAsync(int id)
    {
        var items = await Db.QueryAll(Q("PK = :pk", new() { [":pk"] = Av.S(Keys.Product(id)) }));
        var head = items.FirstOrDefault(x => x.Str("SK") == "PRODUCT" && x.IsLive());
        if (head is null) return null;
        var p = ToProduct(head);
        p.ThumbnailFileName = items.Where(x => x.Str("type") == "ProductPhotoLink").OrderByDescending(x => x.Bool("primary") ?? false)
            .Select(x => x.Str("thumbnail_file_name")).FirstOrDefault();
        return p;
    }

    public async Task<bool> HasChildrenAsync(int id)
    {
        var r = await Db.QueryAsync(new QueryRequest { TableName = Table, KeyConditionExpression = "PK = :pk AND SK < :sk", Limit = 1,
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Product(id)), [":sk"] = Av.S("PRODUCT") } });
        var r2 = await Db.QueryAsync(new QueryRequest { TableName = Table, KeyConditionExpression = "PK = :pk AND SK > :sk", Limit = 1,
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.Product(id)), [":sk"] = Av.S("PRODUCT") } });
        return (r.Items?.Count ?? 0) + (r2.Items?.Count ?? 0) > 0;
    }

    // CAT-04 second request: model descriptions (6 cultures, D9).
    public async Task<List<ModelDescription>> GetDescriptionsAsync(int modelId)
    {
        var items = await Db.QueryAll(Q("PK = :pk AND begins_with(SK, :d)", new() { [":pk"] = Av.S(Keys.Model(modelId)), [":d"] = Av.S("DESC#") }));
        return items.Where(x => x.IsLive()).Select(x => new ModelDescription(x.Str("culture_id")!.Trim(), x.Str("description") ?? "")).ToList();
    }

    // CAT-12 (D2): name-prefix search over the PRODUCTNAMES partition.
    public async Task<List<ProductSummary>> SearchByPrefixAsync(string prefix, int limit = 50)
    {
        prefix = prefix.Trim().ToLowerInvariant();
        if (prefix.Length == 0) return new();
        var items = await Db.QueryAll(Q("PK = :pk AND begins_with(SK, :p)", new() { [":pk"] = Av.S("PRODUCTNAMES"), [":p"] = Av.S(prefix) }), limit);
        return items.Where(x => x.IsLive()).Select(ToSummary).Where(x => x.Active).Take(limit).ToList();
    }

    // CAT-06: admin product grid, paged.
    public async Task<ProductPage> ListProductsAsync(string? token, int pageSize = 25)
    {
        var r = await Db.QueryAsync(new QueryRequest { TableName = Table, KeyConditionExpression = "PK = :pk", Limit = pageSize,
            ExpressionAttributeValues = new() { [":pk"] = Av.S("PRODUCTNAMES") }, ExclusiveStartKey = Paging.Decode(token) });
        return new ProductPage((r.Items ?? new()).Where(x => x.IsLive()).Select(ToSummary).ToList(), Paging.Encode(r.LastEvaluatedKey));
    }

    // CAT-05: product by number.
    public async Task<Product?> GetByNumberAsync(string number)
    {
        var r = await Db.GetItemAsync(new GetItemRequest { TableName = Table, Key = K(Keys.ProductNumber(number), "PRODUCTNUMBER") });
        return r.Item is { Count: > 0 } i && i.IsLive() ? await GetProductAsync(i.Int("product_id")!.Value) : null;
    }

    private static ProductSummary ToSummary(Dictionary<string, AttributeValue> x) =>
        new(x.Int("product_id")!.Value, x.Str("name")!, x.Str("product_number") ?? "", x.Dec("list_price") ?? 0, (x.Str("active") ?? "A") == "A");

    public static Product ToProduct(Dictionary<string, AttributeValue> i) => new()
    {
        Id = i.Int("product_id")!.Value, Name = i.Str("name")!, ProductNumber = i.Str("product_number") ?? "",
        Color = i.Str("color"), Size = i.Str("size"), ListPrice = i.Dec("list_price") ?? 0, StandardCost = i.Dec("standard_cost") ?? 0,
        SubcategoryId = i.Int("product_subcategory_id"), SubcategoryName = i.Str("subcategory_name"), CategoryId = i.Int("category_id"),
        CategoryName = i.Str("category_name"), ModelId = i.Int("product_model_id"), ModelName = i.Str("model_name"), Weight = i.Dec("weight"),
        SellStartDate = i.Date("sell_start_date"), SellEndDate = i.Date("sell_end_date"), StockQty = i.Dec("stock_qty") ?? 0,
        Active = (i.Str("active") ?? "A") == "A", Version = i.Long("ver") ?? 1, Source = i.Str("src") ?? "sql",
    };

    private static Dictionary<string, AttributeValue> K(string pk, string sk) => new() { ["PK"] = Av.S(pk), ["SK"] = Av.S(sk) };

    // ------------------------------------------------------------------ admin writes (CAT-07, CAT-02)

    private Dictionary<string, AttributeValue> ProductItem(Product p, Dictionary<string, AttributeValue>? existing)
    {
        var i = existing is null ? new() : new Dictionary<string, AttributeValue>(existing);
        foreach (var (k, v) in Av.Item(Keys.Product(p.Id), "PRODUCT", "Product", p.Version)) i[k] = v;
        i["product_id"] = Av.N(p.Id); i.Set("name", p.Name); i.Set("product_number", p.ProductNumber);
        i.Set("color", p.Color); i.Set("size", p.Size); i["list_price"] = Av.N(p.ListPrice); i["standard_cost"] = Av.N(p.StandardCost);
        i.Set("product_subcategory_id", p.SubcategoryId); i.Set("subcategory_name", p.SubcategoryName);
        i.Set("category_id", p.CategoryId); i.Set("category_name", p.CategoryName);
        i.Set("sell_start_date", p.SellStartDate is { } d ? Keys.Iso(d) : null);
        i["active"] = Av.S(p.Active ? "A" : "I");
        if (!i.ContainsKey("stock_qty")) i["stock_qty"] = Av.N(0);
        if (!i.ContainsKey("safety_stock_level")) { i["safety_stock_level"] = Av.N(1); i["reorder_point"] = Av.N(1); i["make_flag"] = Av.B(false); i["finished_goods_flag"] = Av.B(true); i["days_to_manufacture"] = Av.N(0); }
        if (p.SubcategoryId is { } s) { i["GSI1PK"] = Av.S(Keys.SubcatGsi(s)); i["GSI1SK"] = Av.S($"PRODUCT#{(p.Active ? "A" : "I")}#{p.Name.ToLowerInvariant()}#{p.Id:000000}"); }
        else { i.Remove("GSI1PK"); i.Remove("GSI1SK"); }
        return i;
    }

    private Dictionary<string, AttributeValue> NameItem(Product p)
    {
        var i = Av.Item("PRODUCTNAMES", p.Name.ToLowerInvariant(), "ProductNameIndex", p.Version);
        i["derived"] = Av.B(true); i["product_id"] = Av.N(p.Id); i["name"] = Av.S(p.Name); i["product_number"] = Av.S(p.ProductNumber);
        i["list_price"] = Av.N(p.ListPrice); i.Set("product_subcategory_id", p.SubcategoryId); i["active"] = Av.S(p.Active ? "A" : "I");
        return i;
    }

    private Dictionary<string, AttributeValue> NumberItem(Product p)
    {
        var i = Av.Item(Keys.ProductNumber(p.ProductNumber), "PRODUCTNUMBER", "ProductNumberIndex", p.Version);
        i["derived"] = Av.B(true); i["product_id"] = Av.N(p.Id);
        return i;
    }

    private async Task FillCopiesAsync(Product p)
    {
        if (p.SubcategoryId is { } s && await GetSubcategoryAsync(s) is { } sub)
        { p.SubcategoryName = sub.Name; p.CategoryId = sub.CategoryId; p.CategoryName = sub.CategoryName; }
        else { p.SubcategoryId = null; p.SubcategoryName = null; p.CategoryId = null; p.CategoryName = null; }
    }

    /// <summary>CAT-07 create: product + unique name + unique number items in one transaction.</summary>
    public async Task<int> CreateProductAsync(Product p)
    {
        var all = await Db.QueryAll(Q("PK = :pk", new() { [":pk"] = Av.S("PRODUCTNAMES") }));
        p.Id = all.Select(x => x.Int("product_id") ?? 0).DefaultIfEmpty(0).Max() + 1;
        p.Version = 1; p.SellStartDate ??= DateTime.UtcNow.Date;
        await FillCopiesAsync(p);
        await Db.TransactWriteItemsAsync(new TransactWriteItemsRequest { TransactItems =
        [
            Put(ProductItem(p, null), "attribute_not_exists(PK)"),
            Put(NameItem(p), "attribute_not_exists(PK)"),
            Put(NumberItem(p), "attribute_not_exists(PK)"),
        ] });
        return p.Id;
    }

    /// <summary>CAT-07 update: optimistic (ver = :v); re-keys the name/number items on rename.</summary>
    public async Task UpdateProductAsync(Product p)
    {
        var cur = await Db.GetItemAsync(new GetItemRequest { TableName = Table, Key = K(Keys.Product(p.Id), "PRODUCT"), ConsistentRead = true });
        if (cur.Item is not { Count: > 0 } existing) throw new KeyNotFoundException();
        var old = ToProduct(existing);
        var expected = p.Version; p.Version = expected + 1;
        await FillCopiesAsync(p);
        var tx = new List<TransactWriteItem>
        {
            Put(ProductItem(p, existing), "ver = :v", new() { [":v"] = Av.N(expected) }),
            Put(NameItem(p), old.Name.Equals(p.Name, StringComparison.OrdinalIgnoreCase) ? null : "attribute_not_exists(PK)"),
            Put(NumberItem(p), old.ProductNumber == p.ProductNumber ? null : "attribute_not_exists(PK)"),
        };
        if (!old.Name.Equals(p.Name, StringComparison.OrdinalIgnoreCase)) tx.Add(Del("PRODUCTNAMES", old.Name.ToLowerInvariant()));
        if (old.ProductNumber != p.ProductNumber) tx.Add(Del(Keys.ProductNumber(old.ProductNumber), "PRODUCTNUMBER"));
        await Db.TransactWriteItemsAsync(new TransactWriteItemsRequest { TransactItems = tx });
    }

    /// <summary>Delete is only allowed for products without history (no photos/offers/reviews in the collection);
    /// order lines keep their own snapshot. SQL-sourced products with history are deactivated instead.</summary>
    public async Task DeleteProductAsync(int id)
    {
        var p = await GetProductAsync(id) ?? throw new KeyNotFoundException();
        if (await HasChildrenAsync(id)) throw new InvalidOperationException("Product has history (photos, offers, reviews); deactivate it instead.");
        await Db.TransactWriteItemsAsync(new TransactWriteItemsRequest { TransactItems =
        [
            Del(Keys.Product(id), "PRODUCT"), Del("PRODUCTNAMES", p.Name.ToLowerInvariant()), Del(Keys.ProductNumber(p.ProductNumber), "PRODUCTNUMBER"),
        ] });
    }

    // CAT-02 writes: categories and subcategories live in the CATALOG collection.
    public async Task<int> SaveCategoryAsync(int? id, string name)
    {
        var tree = await GetCategoryTreeAsync();
        var newId = id ?? tree.Select(c => c.Id).DefaultIfEmpty(0).Max() + 1;
        var item = Av.Item("CATALOG", Keys.Category(newId), "Category");
        item["product_category_id"] = Av.N(newId); item["name"] = Av.S(name);
        await Db.PutItemAsync(new PutItemRequest { TableName = Table, Item = item,
            ConditionExpression = id is null ? "attribute_not_exists(PK)" : "attribute_exists(PK)" });
        return newId;
    }

    public async Task<int> SaveSubcategoryAsync(int? id, int categoryId, string name)
    {
        var tree = await GetCategoryTreeAsync();
        var cat = tree.FirstOrDefault(c => c.Id == categoryId) ?? throw new KeyNotFoundException("category");
        var current = id is null ? null : tree.SelectMany(c => c.Subcategories).FirstOrDefault(s => s.Id == id);
        var newId = id ?? tree.SelectMany(c => c.Subcategories).Select(s => s.Id).DefaultIfEmpty(0).Max() + 1;
        var item = Av.Item("CATALOG", Keys.Subcategory(categoryId, newId), "Subcategory");
        item["product_subcategory_id"] = Av.N(newId); item["product_category_id"] = Av.N(categoryId);
        item["name"] = Av.S(name); item["category_name"] = Av.S(cat.Name);
        item["GSI1PK"] = Av.S(Keys.SubcatGsi(newId)); item["GSI1SK"] = Av.S("#META");
        var tx = new List<TransactWriteItem> { Put(item, current is null || current.CategoryId != categoryId ? "attribute_not_exists(PK)" : null) };
        if (current is not null && current.CategoryId != categoryId) tx.Add(Del("CATALOG", Keys.Subcategory(current.CategoryId, current.Id)));
        await Db.TransactWriteItemsAsync(new TransactWriteItemsRequest { TransactItems = tx });
        return newId;
    }

    public async Task DeleteCategoryAsync(int id, int? subId)
    {
        var tree = await GetCategoryTreeAsync();
        var cat = tree.FirstOrDefault(c => c.Id == id) ?? throw new KeyNotFoundException();
        if (subId is { } s)
        {
            if ((await GetProductsBySubcategoryAsync(s)).Count > 0 || await AnyInactiveAsync(s)) throw new InvalidOperationException("Subcategory still has products.");
            await Db.DeleteItemAsync(new DeleteItemRequest { TableName = Table, Key = K("CATALOG", Keys.Subcategory(id, s)) });
            return;
        }
        if (cat.Subcategories.Count > 0) throw new InvalidOperationException("Category still has subcategories.");
        await Db.DeleteItemAsync(new DeleteItemRequest { TableName = Table, Key = K("CATALOG", Keys.Category(id)) });
    }

    private async Task<bool> AnyInactiveAsync(int sub)
    {
        var r = await Db.QueryAsync(new QueryRequest { TableName = Table, IndexName = "GSI1", Limit = 2, KeyConditionExpression = "GSI1PK = :pk AND begins_with(GSI1SK, :p)",
            ExpressionAttributeValues = new() { [":pk"] = Av.S(Keys.SubcatGsi(sub)), [":p"] = Av.S("PRODUCT#") } });
        return (r.Items?.Count ?? 0) > 0;
    }

    private TransactWriteItem Put(Dictionary<string, AttributeValue> item, string? cond, Dictionary<string, AttributeValue>? values = null) =>
        new() { Put = new Put { TableName = Table, Item = item, ConditionExpression = cond, ExpressionAttributeValues = values } };

    private TransactWriteItem Del(string pk, string sk) => new() { Delete = new Delete { TableName = Table, Key = K(pk, sk) } };
}
