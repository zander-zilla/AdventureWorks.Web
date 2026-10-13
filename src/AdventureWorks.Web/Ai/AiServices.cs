using System.Collections.Concurrent;
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Amazon.BedrockRuntime;
using Amazon.BedrockRuntime.Model;
using Amazon.RedshiftDataAPIService;
using Amazon.RedshiftDataAPIService.Model;
using Amazon.S3Vectors;
using Amazon.S3Vectors.Model;
using AdventureWorks.Web.Data;
using AdventureWorks.Web.Models;
using Npgsql;

namespace AdventureWorks.Web.Ai;

/// <summary>C2-5 settings ("Ai" section). Off unless Enabled; Terraform sets Ai__* when enable_ai = true.</summary>
public sealed class AiOptions
{
    public bool Enabled { get; set; }
    public string Mode { get; set; } = "mock";                 // mock | bedrock
    public string EmbeddingModel { get; set; } = "amazon.titan-embed-text-v2:0";
    public int Dimensions { get; set; } = 512;
    public string ChatModel { get; set; } = "amazon.nova-pro-v1:0";
    public string? GuardrailId { get; set; }
    public string GuardrailVersion { get; set; } = "DRAFT";
    public string? VectorBucket { get; set; }
    public string VectorIndex { get; set; } = "products";
    public string? RedshiftWorkgroup { get; set; }
    public string RedshiftDatabase { get; set; } = "dev";
    public string? RedshiftSecretArn { get; set; }              // read-only ai_reader user
    public string? WarehouseConnection { get; set; }            // local Postgres stand-in (optional)
    public int RowLimit { get; set; } = 200;
    public int TimeoutSeconds { get; set; } = 15;
    public int SessionQuestions { get; set; } = 20;             // per session per day
    public int SessionTokens { get; set; } = 40_000;
    public bool IsBedrock => Mode.Equals("bedrock", StringComparison.OrdinalIgnoreCase);
}

public sealed record AiStatus(bool Enabled, string Mode, string ChatModel, string EmbeddingModel, int RowLimit, int TimeoutSeconds, int QuestionsLeft, int TokensLeft, bool WarehouseConnected);
public sealed record SearchHit(int ProductId, string Name, string? Category, string? Subcategory, string? Model, decimal ListPrice, double Score, double VectorScore, double KeywordScore);
public sealed record SearchResult(string Query, string Mode, List<SearchHit> Hits);
public sealed record AskRequest(string Question);
public sealed record AskResult(string Question, string? Sql, string? GuardedSql, List<string> Columns, List<List<object?>> Rows, bool Truncated,
    string? Chart, string? Blocked, string? Error, int InputTokens, int OutputTokens, long ElapsedMs, int QuestionsLeft, int TokensLeft, string Mode);
public sealed record EvalQuestion(int Id, string Question, string Sql, string Expected);

// ---------- embeddings ----------
public interface IEmbedder { Task<float[]> EmbedAsync(string text, CancellationToken ct = default); }

/// <summary>Mock embedder (CI / local): deterministic feature hashing of words and character trigrams, L2-normalised. Lexical, not semantic.</summary>
public sealed class HashEmbedder(int dims = 512) : IEmbedder
{
    public Task<float[]> EmbedAsync(string text, CancellationToken ct = default)
    {
        var v = new float[dims];
        foreach (var w in AiText.Words(text))
        {
            v[Bucket(w)] += 2f;
            var p = $"^{w}$";
            for (var i = 0; i + 3 <= p.Length; i++) v[Bucket(p.Substring(i, 3))] += 1f;
        }
        return Task.FromResult(AiText.Normalise(v));
    }
    int Bucket(string s) { var h = 2166136261u; foreach (var c in s) { h ^= c; h *= 16777619u; } return (int)(h % (uint)dims); }
}

public sealed class TitanEmbedder(IAmazonBedrockRuntime bedrock, AiOptions o) : IEmbedder
{
    public async Task<float[]> EmbedAsync(string text, CancellationToken ct = default)
    {
        var body = JsonSerializer.SerializeToUtf8Bytes(new { inputText = text, dimensions = o.Dimensions, normalize = true });
        var r = await bedrock.InvokeModelAsync(new InvokeModelRequest { ModelId = o.EmbeddingModel, ContentType = "application/json", Accept = "application/json", Body = new MemoryStream(body) }, ct);
        using var doc = await JsonDocument.ParseAsync(r.Body, cancellationToken: ct);
        return doc.RootElement.GetProperty("embedding").EnumerateArray().Select(e => e.GetSingle()).ToArray();
    }
}

// ---------- vector store ----------
public interface IVectorStore
{
    Task UpsertAsync(IReadOnlyList<(string Key, float[] Vector)> items, CancellationToken ct = default);
    Task<List<(string Key, double Score)>> QueryAsync(float[] v, int topK, CancellationToken ct = default);
    Task<int> CountAsync();
}

public sealed class InMemoryVectorStore : IVectorStore
{
    readonly ConcurrentDictionary<string, float[]> _v = new();
    public Task UpsertAsync(IReadOnlyList<(string Key, float[] Vector)> items, CancellationToken ct = default) { foreach (var (k, v) in items) _v[k] = v; return Task.CompletedTask; }
    public Task<List<(string Key, double Score)>> QueryAsync(float[] q, int topK, CancellationToken ct = default) =>
        Task.FromResult(_v.Select(kv => (kv.Key, Score: (double)AiText.Dot(q, kv.Value))).OrderByDescending(x => x.Score).ThenBy(x => x.Key).Take(topK).ToList());
    public Task<int> CountAsync() => Task.FromResult(_v.Count);
}

/// <summary>Amazon S3 Vectors (cosine index created by Terraform module ai).</summary>
public sealed class S3VectorStore(IAmazonS3Vectors s3v, AiOptions o) : IVectorStore
{
    int _count = -1;
    public async Task UpsertAsync(IReadOnlyList<(string Key, float[] Vector)> items, CancellationToken ct = default)
    {
        foreach (var chunk in items.Chunk(500))
            await s3v.PutVectorsAsync(new PutVectorsRequest { VectorBucketName = o.VectorBucket, IndexName = o.VectorIndex,
                Vectors = chunk.Select(x => new PutInputVector { Key = x.Key, Data = new VectorData { Float32 = x.Vector.ToList() } }).ToList() }, ct);
        _count = Math.Max(_count, 0) + items.Count;
    }
    public async Task<List<(string Key, double Score)>> QueryAsync(float[] v, int topK, CancellationToken ct = default)
    {
        var r = await s3v.QueryVectorsAsync(new QueryVectorsRequest { VectorBucketName = o.VectorBucket, IndexName = o.VectorIndex, TopK = topK,
            QueryVector = new VectorData { Float32 = v.ToList() }, ReturnDistance = true }, ct);
        if (_count < 0) _count = r.Vectors.Count;
        return r.Vectors.Select(x => (x.Key, 1.0 - (x.Distance ?? 1f))).ToList();   // cosine distance -> similarity
    }
    public Task<int> CountAsync() => Task.FromResult(Math.Max(_count, 0));
}

// ---------- semantic search ----------
/// <summary>Product corpus (name, model, category, subcategory, English model description) embedded into the vector store;
/// results blend vector similarity (0.7) with keyword overlap (0.3).</summary>
public sealed class SemanticSearch(CatalogRepository catalog, IEmbedder embedder, IVectorStore store, ILogger<SemanticSearch> log)
{
    public const double VectorWeight = 0.7, KeywordWeight = 0.3;
    readonly SemaphoreSlim _lock = new(1, 1);
    Dictionary<int, (Product P, string Text)>? _corpus;

    public async Task<Dictionary<int, (Product P, string Text)>> CorpusAsync()
    {
        if (_corpus is { } c) return c;
        await _lock.WaitAsync();
        try
        {
            if (_corpus is { } c2) return c2;
            var d = new Dictionary<int, (Product, string)>();
            var descs = new ConcurrentDictionary<int, string>();
            foreach (var cat in await catalog.GetCategoryTreeAsync())
                foreach (var sub in cat.Subcategories)
                    foreach (var p in await catalog.GetProductsBySubcategoryAsync(sub.Id))
                    {
                        if (p.ModelId is int m && !descs.ContainsKey(m))
                            descs[m] = (await catalog.GetDescriptionsAsync(m)).FirstOrDefault(x => x.Culture.Trim() == "en")?.Text ?? "";
                        d[p.Id] = (p, $"{p.Name}. {p.ModelName}. {p.CategoryName ?? cat.Name} / {p.SubcategoryName ?? sub.Name}. {p.Color} {(p.ModelId is int mm ? descs[mm] : "")}".Trim());
                    }
            return _corpus = d;
        }
        finally { _lock.Release(); }
    }

    public async Task<int> ReindexAsync(CancellationToken ct = default)
    {
        var corpus = await CorpusAsync();
        var items = new List<(string, float[])>();
        foreach (var (id, (_, text)) in corpus) items.Add((id.ToString(), await embedder.EmbedAsync(text, ct)));
        await store.UpsertAsync(items, ct);
        log.LogInformation("ai.reindex {Count} products", items.Count);
        return items.Count;
    }

    public async Task<SearchResult> SearchAsync(string q, int top, string mode, CancellationToken ct = default)
    {
        var corpus = await CorpusAsync();
        if (await store.CountAsync() == 0) await ReindexAsync(ct);
        var qv = await embedder.EmbedAsync(q, ct);
        var vec = (await store.QueryAsync(qv, Math.Max(top * 4, 40), ct)).ToDictionary(x => x.Key, x => x.Score);
        var words = AiText.Words(q).Where(w => w.Length > 2 && !AiText.Stop.Contains(w)).ToList();
        var hits = corpus.Select(kv =>
        {
            var vs = vec.GetValueOrDefault(kv.Key.ToString());
            var ks = Keyword(words, kv.Value.Text);
            return (kv.Value.P, vs, ks, score: VectorWeight * vs + KeywordWeight * ks);
        }).Where(x => x.score > 0).OrderByDescending(x => x.score).ThenBy(x => x.P.Name).Take(top)
          .Select(x => new SearchHit(x.P.Id, x.P.Name, x.P.CategoryName, x.P.SubcategoryName, x.P.ModelName, x.P.ListPrice, Math.Round(x.score, 4), Math.Round(x.vs, 4), Math.Round(x.ks, 4))).ToList();
        return new SearchResult(q, mode, hits);
    }

    public static double Keyword(IReadOnlyList<string> words, string text)
    {
        if (words.Count == 0) return 0;
        var t = AiText.Words(text).ToHashSet();
        return (double)words.Count(w => t.Contains(w) || t.Any(x => x.StartsWith(w))) / words.Count;
    }
}

// ---------- NL -> SQL ----------
public sealed record SqlAnswer(string? Sql, string? Blocked, int InputTokens, int OutputTokens);
public interface ISqlModel { Task<SqlAnswer> ToSqlAsync(string question, CancellationToken ct = default); }

/// <summary>Mocked model for CI and local runs: replays the eval-set answers (exact question match, case / punctuation insensitive)
/// and refuses anything else. A local stand-in for the guardrail blocks the denied topics and PII the Bedrock guardrail blocks.</summary>
public sealed class MockSqlModel(IReadOnlyList<EvalQuestion> eval) : ISqlModel
{
    readonly Dictionary<string, string> _answers = eval.ToDictionary(e => AiText.Key(e.Question), e => e.Sql);
    public Task<SqlAnswer> ToSqlAsync(string question, CancellationToken ct = default)
    {
        var tokensIn = 900 + question.Length / 4;
        if (LocalGuardrail.Check(question) is { } why) return Task.FromResult(new SqlAnswer(null, why, tokensIn, 0));
        return Task.FromResult(_answers.TryGetValue(AiText.Key(question), out var sql)
            ? new SqlAnswer(sql, null, tokensIn, sql.Length / 4)
            : new SqlAnswer(null, null, tokensIn, 12));
    }
}

public static partial class LocalGuardrail
{
    // Mirrors the Bedrock guardrail in infra/modules/ai: denied topics + PII in the question.
    public static string? Check(string q)
    {
        var l = q.ToLowerInvariant();
        if (Topics().IsMatch(l)) return "Blocked by the guardrail: this topic is not allowed (personal data, credentials or HR records).";
        if (Pii().IsMatch(q)) return "Blocked by the guardrail: the question contains personal data (email, phone or card number).";
        return null;
    }
    [GeneratedRegex(@"\b(password|passwords|credit card|card number|social security|ssn|salary|salaries|pay rate|home address|phone number|email address|ignore (all|previous|the) instructions|system prompt)\b")]
    private static partial Regex Topics();
    [GeneratedRegex(@"[\w.+-]+@[\w-]+\.[\w.]+|\b(?:\d[ -]?){13,16}\b|\b\d{3}[-. ]\d{3}[-. ]\d{4}\b")]
    private static partial Regex Pii();
}

public sealed class BedrockSqlModel(IAmazonBedrockRuntime bedrock, AiOptions o) : ISqlModel
{
    public async Task<SqlAnswer> ToSqlAsync(string question, CancellationToken ct = default)
    {
        var req = new ConverseRequest
        {
            ModelId = o.ChatModel,
            System = [new SystemContentBlock { Text = SemanticLayer.Prompt }],
            Messages = [new Message { Role = ConversationRole.User, Content = [new ContentBlock { Text = question }] }],
            InferenceConfig = new InferenceConfiguration { MaxTokens = 800, Temperature = 0 },
        };
        if (!string.IsNullOrEmpty(o.GuardrailId)) req.GuardrailConfig = new GuardrailConfiguration { GuardrailIdentifier = o.GuardrailId, GuardrailVersion = o.GuardrailVersion };
        var r = await bedrock.ConverseAsync(req, ct);
        int tin = r.Usage?.InputTokens ?? 0, tout = r.Usage?.OutputTokens ?? 0;
        if (r.StopReason == StopReason.Guardrail_intervened) return new SqlAnswer(null, "Blocked by the Bedrock guardrail.", tin, tout);
        var text = string.Concat(r.Output?.Message?.Content?.Select(c => c.Text) ?? []);
        return new SqlAnswer(SemanticLayer.ExtractSql(text), null, tin, tout);
    }
}

public static partial class SemanticLayer
{
    public const string Prompt = """
        You translate questions about AdventureWorks into one Amazon Redshift SQL SELECT statement.
        Use ONLY these views (schema dw); never base tables, never DDL/DML, no comments, no semicolons:
        dw.v_sales(channel ['Internet'|'Reseller'], sales_order_number, sales_order_line_number, order_date, calendar_year, calendar_quarter,
          month_number_of_year, english_month_name, fiscal_year, sales_territory_group, sales_territory_country, sales_territory_region,
          product_category, product_subcategory, product_name, model_name, promotion, customer_or_reseller, order_quantity, sales_amount,
          total_product_cost, gross_margin, tax_amt, freight) - one row per sales order line, both channels.
        dw.v_vendor_performance(vendor_key, vendor_name, preferred_vendor_flag, credit_rating, purchase_orders, lines, ordered_quantity,
          received_quantity, rejected_quantity, spend, reject_rate, fill_rate, on_time_rate, avg_lead_time_days, app_lines) - one row per vendor.
        dw.v_production_scrap_on_time(calendar_year, month_number_of_year, due_year_month [yyyymm], work_orders, closed, on_time,
          order_quantity, scrapped_quantity, scrap_rate, on_time_rate, app_work_orders) - one row per work-order due month.
        Recompute ratios from sums when aggregating. Add ORDER BY for ranked or time-series answers. If the question cannot be answered
        from these views, reply exactly: CANNOT_ANSWER. Otherwise reply with the SQL only, in a ```sql block.
        """;

    public static string? ExtractSql(string text)
    {
        if (text.Contains("CANNOT_ANSWER")) return null;
        var m = Block().Match(text);
        return (m.Success ? m.Groups[1].Value : text).Trim();
    }
    [GeneratedRegex(@"```(?:sql)?\s*([\s\S]*?)```", RegexOptions.IgnoreCase)] private static partial Regex Block();
}

// ---------- SQL runner ----------
public sealed record SqlRows(List<string> Columns, List<List<object?>> Rows);
public interface ISqlRunner { bool Connected { get; } Task<SqlRows> RunAsync(string guardedSql, int timeoutSeconds, CancellationToken ct = default); }

public sealed class NoWarehouseRunner : ISqlRunner
{
    public bool Connected => false;
    public Task<SqlRows> RunAsync(string sql, int t, CancellationToken ct = default) => throw new InvalidOperationException("No warehouse is connected in this environment; the SQL was generated and checked but not run.");
}

/// <summary>Local Postgres stand-in: read-only transaction with statement_timeout.</summary>
public sealed class PostgresRunner(string connection) : ISqlRunner
{
    public bool Connected => true;
    public async Task<SqlRows> RunAsync(string sql, int timeoutSeconds, CancellationToken ct = default)
    {
        await using var c = new NpgsqlConnection(connection);
        await c.OpenAsync(ct);
        await using var tx = await c.BeginTransactionAsync(ct);
        await using (var set = new NpgsqlCommand($"SET TRANSACTION READ ONLY; SET LOCAL statement_timeout = {timeoutSeconds * 1000}", c, tx)) await set.ExecuteNonQueryAsync(ct);
        await using var cmd = new NpgsqlCommand(sql, c, tx) { CommandTimeout = timeoutSeconds + 2 };
        await using var r = await cmd.ExecuteReaderAsync(ct);
        var cols = Enumerable.Range(0, r.FieldCount).Select(r.GetName).ToList();
        var rows = new List<List<object?>>();
        while (await r.ReadAsync(ct)) rows.Add(Enumerable.Range(0, r.FieldCount).Select(i => r.IsDBNull(i) ? null : r.GetValue(i)).ToList());
        return new SqlRows(cols, rows);
    }
}

/// <summary>Redshift Serverless via the Data API as the read-only ai_reader user (secret); cancelled at the timeout.</summary>
public sealed class RedshiftDataRunner(IAmazonRedshiftDataAPIService rs, AiOptions o) : ISqlRunner
{
    public bool Connected => true;
    public async Task<SqlRows> RunAsync(string sql, int timeoutSeconds, CancellationToken ct = default)
    {
        var ex = await rs.ExecuteStatementAsync(new ExecuteStatementRequest { WorkgroupName = o.RedshiftWorkgroup, Database = o.RedshiftDatabase, SecretArn = o.RedshiftSecretArn, Sql = sql }, ct);
        var sw = Stopwatch.StartNew();
        while (true)
        {
            var d = await rs.DescribeStatementAsync(new DescribeStatementRequest { Id = ex.Id }, ct);
            if (d.Status == StatusString.FINISHED) break;
            if (d.Status == StatusString.FAILED || d.Status == StatusString.ABORTED) throw new InvalidOperationException(d.Error ?? "Statement failed.");
            if (sw.Elapsed.TotalSeconds > timeoutSeconds) { await rs.CancelStatementAsync(new CancelStatementRequest { Id = ex.Id }, ct); throw new TimeoutException($"Cancelled after {timeoutSeconds} s."); }
            await Task.Delay(250, ct);
        }
        var res = await rs.GetStatementResultAsync(new GetStatementResultRequest { Id = ex.Id }, ct);
        return new SqlRows(res.ColumnMetadata.Select(c => c.Name).ToList(),
            res.Records.Select(r => r.Select(f => f.IsNull == true ? null : (object?)f.StringValue ?? (object?)f.LongValue ?? (object?)f.DoubleValue ?? f.BooleanValue).ToList()).ToList());
    }
}

// ---------- budget ----------
/// <summary>Per-session daily budget (questions and model tokens), in memory per task.</summary>
public sealed class AiBudget(AiOptions o, TimeProvider clock)
{
    readonly ConcurrentDictionary<string, (DateOnly Day, int Questions, int Tokens)> _s = new();
    (DateOnly, int, int) Current(string key) { var today = DateOnly.FromDateTime(clock.GetUtcNow().UtcDateTime); var v = _s.GetValueOrDefault(key); return v.Day == today ? v : (today, 0, 0); }
    public (int QuestionsLeft, int TokensLeft) Left(string key) { var (_, q, t) = Current(key); return (Math.Max(0, o.SessionQuestions - q), Math.Max(0, o.SessionTokens - t)); }
    public bool TryStart(string key) { var (_, q, t) = Current(key); return q < o.SessionQuestions && t < o.SessionTokens; }
    public void Charge(string key, int tokens) => _s.AddOrUpdate(key, _ => { var (d, q, t) = Current(key); return (d, q + 1, t + tokens); }, (_, _) => { var (d, q, t) = Current(key); return (d, q + 1, t + tokens); });
}

// ---------- ask the data ----------
public sealed class AskService(ISqlModel model, ISqlRunner runner, AiBudget budget, AiOptions o, ILogger<AskService> log)
{
    public async Task<AskResult> AskAsync(string session, string user, string question, CancellationToken ct = default)
    {
        var sw = Stopwatch.StartNew();
        question = (question ?? "").Trim();
        AskResult Done(string? sql, string? guarded, SqlRows? rows, string? blocked, string? error, int tin, int tout)
        {
            var (ql, tl) = budget.Left(session);
            var list = rows?.Rows ?? [];
            var res = new AskResult(question, sql, guarded, rows?.Columns ?? [], list.Take(o.RowLimit).Select(r => r.Select(Plain).ToList()).ToList(), list.Count >= o.RowLimit,
                rows is null ? null : ChartFor(rows), blocked, error, tin, tout, sw.ElapsedMilliseconds, ql, tl, o.Mode);
            // Prompt / response log (CloudWatch via the task's log driver). The question is logged; answers are summarised.
            log.LogInformation("ai.ask user={User} session={Session} question={Question} sql={Sql} rows={Rows} blocked={Blocked} error={Error} tokens_in={In} tokens_out={Out} ms={Ms}",
                user, session, question, sql, list.Count, blocked, error, tin, tout, sw.ElapsedMilliseconds);
            return res;
        }
        if (question.Length is < 3 or > 500) return Done(null, null, null, null, "Ask a question of 3 to 500 characters.", 0, 0);
        if (!budget.TryStart(session)) return Done(null, null, null, "Session budget used up for today.", null, 0, 0);
        SqlAnswer a;
        try { a = await model.ToSqlAsync(question, ct); }
        catch (Exception e) { budget.Charge(session, 0); return Done(null, null, null, null, $"The model call failed: {e.Message}", 0, 0); }
        budget.Charge(session, a.InputTokens + a.OutputTokens);
        if (a.Blocked is not null) return Done(null, null, null, a.Blocked, null, a.InputTokens, a.OutputTokens);
        if (a.Sql is null) return Done(null, null, null, null, o.IsBedrock ? "The model could not answer this from the dw views." : "The mocked model only knows the 30 eval-set questions; try one of the examples.", a.InputTokens, a.OutputTokens);
        var g = SqlGuard.Check(a.Sql, o.RowLimit);
        if (!g.Ok) return Done(a.Sql, null, null, $"Refused by the SQL guard: {g.Reason}", null, a.InputTokens, a.OutputTokens);
        try { return Done(a.Sql, g.Sql, await runner.RunAsync(g.Sql!, o.TimeoutSeconds, ct), null, null, a.InputTokens, a.OutputTokens); }
        catch (Exception e) { return Done(a.Sql, g.Sql, null, null, e.Message, a.InputTokens, a.OutputTokens); }
    }

    static object? Plain(object? v) => v switch { DateTime d => d.ToString("yyyy-MM-dd"), DateOnly d => d.ToString("yyyy-MM-dd"), decimal m => (double)m, _ => v };

    /// <summary>"bar" when the result is label + number columns with up to 50 rows, "line" when the label looks like a period.</summary>
    public static string? ChartFor(SqlRows r)
    {
        if (r.Columns.Count != 2 || r.Rows.Count is < 2 or > 50) return null;
        if (!r.Rows.All(x => x[1] is null or byte or short or int or long or float or double or decimal)) return null;
        var c = r.Columns[0].ToLowerInvariant();
        return c.Contains("year") || c.Contains("month") || c.Contains("quarter") ? "line" : "bar";
    }
}

public static partial class AiText
{
    public static readonly HashSet<string> Stop = ["the", "and", "for", "with", "that", "this", "are", "was", "what", "which", "how", "bike", "bikes"];
    public static IEnumerable<string> Words(string s) => W().Matches(s.ToLowerInvariant()).Select(m => m.Value);
    public static string Key(string q) => string.Join(' ', Words(q));
    public static float[] Normalise(float[] v) { var n = MathF.Sqrt(v.Sum(x => x * x)); if (n > 0) for (var i = 0; i < v.Length; i++) v[i] /= n; return v; }
    public static float Dot(float[] a, float[] b) { var s = 0f; for (var i = 0; i < Math.Min(a.Length, b.Length); i++) s += a[i] * b[i]; return s; }
    public static List<EvalQuestion> LoadEval()
    {
        using var s = typeof(AiText).Assembly.GetManifestResourceStream("AdventureWorks.Web.Ai.eval.json") ?? throw new InvalidOperationException("eval.json missing");
        using var d = JsonDocument.Parse(s);
        return d.RootElement.GetProperty("questions").EnumerateArray().Select(q => new EvalQuestion(q.GetProperty("id").GetInt32(), q.GetProperty("question").GetString()!,
            q.GetProperty("sql").GetString()!, q.GetProperty("expected").GetString()!)).ToList();
    }
    [GeneratedRegex(@"[a-z0-9]+")] private static partial Regex W();
}
