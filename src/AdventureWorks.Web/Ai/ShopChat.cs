using System.Text.RegularExpressions;
using Amazon.DynamoDBv2.Model;
using AdventureWorks.Web.Data;
using AdventureWorks.Web.Models;

namespace AdventureWorks.Web.Ai;

public sealed record AlsoBought(int ProductId, string Name, string? ProductNumber, decimal ListPrice, int Orders);
public sealed record ChatRequest(string Message, int? ProductId = null);
public sealed record ChatCard(int ProductId, string Name, decimal ListPrice, string? Category, string Source);
public sealed record ChatResponse(AssistResult Answer, List<ChatCard> Cards, List<string> Tools, int TurnsLeft);

/// <summary>ALSO#&lt;pid&gt; / RANK#nn items in aw-catalog written by scripts/loader/derive_ai.py (CAT-12).</summary>
public sealed class AlsoBoughtRepository(DynamoTables t)
{
    public async Task<List<AlsoBought>> ListAsync(int productId, int top = 6)
    {
        var items = await t.For(DynamoTables.Catalog).QueryAll(new QueryRequest
        {
            TableName = t.Name(DynamoTables.Catalog), KeyConditionExpression = "PK = :p AND begins_with(SK, :r)",
            ExpressionAttributeValues = new() { [":p"] = Av.S($"ALSO#{productId}"), [":r"] = Av.S("RANK#") },
        }, top);
        return items.Take(top).Select(i => new AlsoBought(i.Int("other_id") ?? 0, i.Str("other_name") ?? "", i.Str("other_number"), i.Dec("other_price") ?? 0, i.Int("orders") ?? 0)).ToList();
    }
}

/// <summary>C2-6 shopper chat. The server picks the tools in code (search, product details, customers also bought) and hands
/// the results to the model as facts; product cards come from the tool results, never from the model's text. The shop
/// feature runs on its own guardrail (John's six settings) with contextual grounding on those facts. Turn-limited.</summary>
public sealed partial class ShopChat(SemanticSearch search, AlsoBoughtRepository also, CatalogRepository catalog, AiAssist assist, AiBudget budget, AiOptions o)
{
    public const int MaxMessage = 300;

    public static (bool Search, bool Also) Route(string message, int? productId)
    {
        var wantsAlso = AlsoIntent().IsMatch(message);
        var onlyAlso = wantsAlso && productId is not null && message.Split(' ', StringSplitOptions.RemoveEmptyEntries).Length <= 8;
        return (!onlyAlso, wantsAlso);
    }

    public async Task<ChatResponse> ChatAsync(string session, string user, ChatRequest req, CancellationToken ct = default)
    {
        var left = budget.TurnsLeft(session, "shop", o.ShopTurns);
        var facts = new Dictionary<string, object?> { ["shop"] = "Adventure Works Cycles online shop" };
        if (left == 0)
        {
            var (ql, tl) = budget.Left(session);
            return new(new AssistResult("shop", "shop-reply", null, [], facts, $"This chat is limited to {o.ShopTurns} questions a day. Browse the catalog or search instead.", null, 0, 0, ql, tl, o.Mode), [], [], 0);
        }
        budget.Turn(session, "shop");
        var msg = ShopGuardrail.Anonymize(req.Message.Trim());
        if (msg.Length > MaxMessage) msg = msg[..MaxMessage];
        var cards = new List<ChatCard>(); var tools = new List<string>();
        var (doSearch, doAlso) = Route(msg, req.ProductId);
        Product? current = req.ProductId is int pid ? await catalog.GetProductAsync(pid) : null;
        if (current is not null)
        {
            tools.Add("details"); facts["product.name"] = current.Name; facts["product.price"] = Math.Round(current.ListPrice, 2); facts["product.category"] = current.CategoryName;
        }
        if (doSearch)
        {
            tools.Add("search");
            var r = await search.SearchAsync(msg, 4, o.Mode, ct);
            facts["search.query"] = msg; facts["search.count"] = r.Hits.Count;
            var i = 0;
            foreach (var h in r.Hits)
            {
                i++; facts[$"p{i}.name"] = h.Name; facts[$"p{i}.price"] = Math.Round(h.ListPrice, 2); facts[$"p{i}.category"] = h.Category;
                cards.Add(new(h.ProductId, h.Name, h.ListPrice, h.Category, "search"));
            }
        }
        if (doAlso)
        {
            var forId = current?.Id ?? cards.FirstOrDefault()?.ProductId;
            var forName = current?.Name ?? cards.FirstOrDefault()?.Name;
            if (forId is int fid)
            {
                tools.Add("also-bought");
                facts["also.for"] = forName;
                var i = 0;
                foreach (var a in (await also.ListAsync(fid, 3)))
                {
                    i++; facts[$"also{i}.name"] = a.Name; facts[$"also{i}.price"] = Math.Round(a.ListPrice, 2);
                    cards.Add(new(a.ProductId, a.Name, a.ListPrice, null, "also-bought"));
                }
            }
        }
        var answer = await assist.RunAsync("shop", "shop-reply", facts, session, user, msg, ct);
        return new(answer, answer.Text is null ? [] : cards, tools, budget.TurnsLeft(session, "shop", o.ShopTurns));
    }

    [GeneratedRegex(@"\b(also|goes? with|go with|pairs?|accessor(y|ies)|match(es|ing)?|together)\b", RegexOptions.IgnoreCase)]
    private static partial Regex AlsoIntent();
}
