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

/// <summary>AWS: the replication monitor API (cdc/monitor_api, GET /api/status + /api/changes). DLQ depth only, no message bodies.</summary>
public sealed class MonitorWatchSource(HttpClient http, AiOptions o) : IWatchSource
{
    static readonly JsonSerializerOptions J = new(JsonSerializerDefaults.Web) { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    public bool Replay => false;
    public async Task<WatchSnapshot> GetAsync(string? scenario, CancellationToken ct)
    {
        var b = o.MonitorApiUrl!.TrimEnd('/');
        var st = await http.GetFromJsonAsync<WatchStatus>($"{b}/api/status", J, ct) ?? throw new InvalidOperationException("empty status");
        var ch = await http.GetFromJsonAsync<List<WatchChange>>($"{b}/api/changes?limit=20", J, ct) ?? [];
        return new WatchSnapshot("live", st, ch, []);
    }
}
