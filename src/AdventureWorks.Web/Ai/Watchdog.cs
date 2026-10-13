using System.Net.Http.Json;
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace AdventureWorks.Web.Ai;

public sealed record LagMs(double Last, double P50, double Max);
public sealed record WatchStatus(bool Paused, int Queued, long AppliedEvents, int? Dlq,
    LagMs LagMs, string? Source);
public sealed record WatchChange(string Table, string Op, double? LagMs);
public sealed record DlqSample(string Table, string Op, string Error, int Attempts, string? Position);
public sealed record WatchSnapshot(string Scenario, WatchStatus Status, List<WatchChange> Changes, List<DlqSample> DlqSamples);
public sealed record WatchCause(string Key, string Title, string Severity, string NextStep, string Runbook);
public sealed record WatchdogReport(WatchSnapshot Snapshot, WatchCause Cause, List<string> Scenarios, bool Replay);

/// <summary>C2-6 replication watchdog. Rules decide the cause; the model only explains it (facts + runbook link).</summary>
public static partial class WatchRules
{
    public const double LagSlo = 60_000;
    const string Rb = "docs/runbooks/replication-watchdog.md";

    public static WatchCause Classify(WatchSnapshot s)
    {
        var st = s.Status;
        if (st.Source == "unavailable") return new("unavailable", "The monitor API did not answer", "warn", "Check the monitor API Lambda and the app's lambda:InvokeFunctionUrl permission", Rb + "#unavailable");
        if (st.Paused) return new("paused", "The consumer is paused", "warn", "Resume the consumer (POST /api/resume) once the maintenance is over", Rb + "#paused");
        if ((st.Dlq ?? 0) > 0)
        {
            var orphan = s.DlqSamples.Any(d => d.Error.Contains("not found", StringComparison.OrdinalIgnoreCase));
            return orphan
                ? new("dlq-orphans", "Child rows reached the dead-letter queue before their parent order", "danger", "Wait for the parent to replicate, then redrive the DLQ", Rb + "#dead-letter-orphans")
                : new("dlq", "Changes failed to apply and wait in the dead-letter queue", "danger", "Read the error on each message, fix the cause, then redrive", Rb + "#dead-letter-queue");
        }
        if (st.LagMs.Last > LagSlo)
            return st.Queued > 1000
                ? new("backlog", "A burst of changes built a backlog: lag is above the 60 s target", "warn", "Watch the queue drain; scale the consumer if it keeps growing", Rb + "#backlog")
                : new("slow-apply", "Changes apply slowly: lag is above the 60 s target with a short queue", "warn", "Check DynamoDB throttling and the consumer logs", Rb + "#slow-apply");
        return new("healthy", "Replication is healthy", "ok", "Nothing to do", Rb + "#healthy");
    }

    public static Dictionary<string, object?> Facts(WatchSnapshot s, WatchCause c)
    {
        var f = new Dictionary<string, object?>
        {
            ["cause.key"] = c.Key, ["cause.title"] = c.Title, ["cause.next_step"] = c.NextStep, ["cause.runbook"] = c.Runbook,
            ["status.paused"] = s.Status.Paused, ["status.queued"] = s.Status.Queued, ["status.dlq"] = s.Status.Dlq ?? 0,
            ["status.lag_last_ms"] = Math.Round(s.Status.LagMs.Last), ["status.lag_p50_ms"] = Math.Round(s.Status.LagMs.P50), ["status.lag_max_ms"] = Math.Round(s.Status.LagMs.Max),
            ["status.source"] = s.Status.Source,
        };
        var i = 0;
        foreach (var d in s.DlqSamples.Take(10)) { i++; f[$"dlq{i}.table"] = d.Table; f[$"dlq{i}.error"] = Redact(d.Error); }
        return f;
    }

    /// <summary>DLQ payloads may carry customer data: only table, operation and a redacted error reach the model or the UI.</summary>
    public static string Redact(string s) => Phone().Replace(Email().Replace(s, "{EMAIL}"), "{PHONE}");
    [GeneratedRegex(@"[\w.+-]+@[\w-]+\.[\w.]+")] private static partial Regex Email();
    [GeneratedRegex(@"\+?\d[\d\s().-]{7,}\d")] private static partial Regex Phone();
}

public interface IWatchSource { bool Replay { get; } Task<WatchSnapshot> GetAsync(string? scenario, CancellationToken ct); }

/// <summary>Recorded scenarios embedded in the image (local, CI, and AWS when no monitor API is configured).</summary>
public sealed class ReplayWatchSource : IWatchSource
{
    public static readonly string[] Scenarios = ["healthy", "lag-spike", "dlq", "paused"];
    static readonly JsonSerializerOptions J = new(JsonSerializerDefaults.Web) { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    public bool Replay => true;
    public Task<WatchSnapshot> GetAsync(string? scenario, CancellationToken ct)
    {
        var name = Scenarios.Contains(scenario) ? scenario! : "healthy";
        using var s = Assembly.GetExecutingAssembly().GetManifestResourceStream($"AdventureWorks.Web.Ai.watchdog.{name}.json")!;
        var snap = JsonSerializer.Deserialize<WatchSnapshot>(s, J)!;
        return Task.FromResult(snap with { DlqSamples = snap.DlqSamples.Select(d => d with { Error = WatchRules.Redact(d.Error) }).ToList() });
    }
}

/// <summary>AWS: the replication monitor API (cdc/monitor_api, GET /api/status + /api/changes) on its Lambda Function URL
/// (AWS_IAM), signed with SigV4 by the app's task role when Ai:MonitorSigV4 is on. DLQ depth only, no message bodies.
/// When the call fails the snapshot says so (cause "unavailable") instead of showing a recorded scenario as if it were live.</summary>
public sealed class MonitorWatchSource(HttpClient http, AiOptions o, ILogger<MonitorWatchSource> log, Func<CancellationToken, Task<SigV4.Creds>>? creds = null) : IWatchSource
{
    static readonly JsonSerializerOptions J = new(JsonSerializerDefaults.Web) { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    public bool Replay => false;

    static async Task<SigV4.Creds> TaskRole(CancellationToken ct)
    {
        var c = await Amazon.Runtime.Credentials.DefaultAWSCredentialsIdentityResolver.GetCredentials().GetCredentialsAsync();
        return new SigV4.Creds(c.AccessKey, c.SecretKey, c.UseToken ? c.Token : null);
    }

    async Task<T?> Get<T>(string url, CancellationToken ct)
    {
        using var req = new HttpRequestMessage(HttpMethod.Get, url);
        if (o.MonitorSigV4)
        {
            var region = o.MonitorRegion ?? Environment.GetEnvironmentVariable("AWS_REGION") ?? "us-east-1";
            SigV4.Sign(req, await (creds ?? TaskRole)(ct), region, "lambda", DateTime.UtcNow);
        }
        using var res = await http.SendAsync(req, ct);
        res.EnsureSuccessStatusCode();
        return await res.Content.ReadFromJsonAsync<T>(J, ct);
    }

    public async Task<WatchSnapshot> GetAsync(string? scenario, CancellationToken ct)
    {
        var b = o.MonitorApiUrl!.TrimEnd('/');
        try
        {
            var st = await Get<WatchStatus>($"{b}/api/status", ct) ?? throw new InvalidOperationException("empty status");
            var ch = await Get<List<WatchChange>>($"{b}/api/changes?limit=20", ct) ?? [];
            return new WatchSnapshot("live", st, ch, []);
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException or InvalidOperationException or JsonException or Amazon.Runtime.AmazonClientException)
        {
            log.LogWarning("watchdog monitor API unavailable: {Error}", e.Message);
            return new WatchSnapshot("live", new WatchStatus(false, 0, 0, null, new LagMs(0, 0, 0), "unavailable"), [], []);
        }
    }
}

/// <summary>Minimal AWS Signature Version 4 for a GET without body (Lambda Function URL with AWS_IAM auth).</summary>
public static class SigV4
{
    public sealed record Creds(string AccessKey, string SecretKey, string? Token);

    public static void Sign(HttpRequestMessage req, Creds c, string region, string service, DateTime utcNow)
    {
        var u = req.RequestUri!;
        var amzDate = utcNow.ToString("yyyyMMdd'T'HHmmss'Z'", System.Globalization.CultureInfo.InvariantCulture);
        var day = amzDate[..8];
        var payloadHash = Hex(System.Security.Cryptography.SHA256.HashData([]));
        var headers = new SortedDictionary<string, string>(StringComparer.Ordinal) { ["host"] = u.IsDefaultPort ? u.Host : $"{u.Host}:{u.Port}", ["x-amz-date"] = amzDate };
        if (c.Token is not null) headers["x-amz-security-token"] = c.Token;
        var query = string.Join('&', (u.Query.TrimStart('?')).Split('&', StringSplitOptions.RemoveEmptyEntries)
            .Select(p => { var kv = p.Split('=', 2); return (K: Enc(Uri.UnescapeDataString(kv[0])), V: Enc(kv.Length > 1 ? Uri.UnescapeDataString(kv[1]) : "")); })
            .OrderBy(p => p.K, StringComparer.Ordinal).ThenBy(p => p.V, StringComparer.Ordinal).Select(p => $"{p.K}={p.V}"));
        var path = string.Join('/', u.AbsolutePath.Split('/').Select(seg => Enc(Uri.UnescapeDataString(seg))));
        var signed = string.Join(';', headers.Keys);
        var canonical = $"GET\n{(path.Length == 0 ? "/" : path)}\n{query}\n{string.Concat(headers.Select(h => $"{h.Key}:{h.Value.Trim()}\n"))}\n{signed}\n{payloadHash}";
        var scope = $"{day}/{region}/{service}/aws4_request";
        var toSign = $"AWS4-HMAC-SHA256\n{amzDate}\n{scope}\n{Hex(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(canonical)))}";
        var k = Hmac(Hmac(Hmac(Hmac(System.Text.Encoding.UTF8.GetBytes("AWS4" + c.SecretKey), day), region), service), "aws4_request");
        var sig = Hex(Hmac(k, toSign));
        req.Headers.TryAddWithoutValidation("x-amz-date", amzDate);
        if (c.Token is not null) req.Headers.TryAddWithoutValidation("x-amz-security-token", c.Token);
        req.Headers.TryAddWithoutValidation("Authorization", $"AWS4-HMAC-SHA256 Credential={c.AccessKey}/{scope}, SignedHeaders={signed}, Signature={sig}");
    }

    static string Enc(string s) => Uri.EscapeDataString(s);   // RFC 3986 unreserved kept, everything else %XX (upper case)
    static byte[] Hmac(byte[] key, string data) => System.Security.Cryptography.HMACSHA256.HashData(key, System.Text.Encoding.UTF8.GetBytes(data));
    static string Hex(byte[] b) => Convert.ToHexStringLower(b);
}
