using System.Text;
using System.Text.RegularExpressions;

namespace AdventureWorks.Web.Ai;

/// <summary>C2-5 ask-the-data guard: one read-only SELECT over the semantic layer (dw.v_* views) only, wrapped with a row limit.
/// Defence in depth: the warehouse user is also read-only on dw views (warehouse/sql/star/06_ai_reader.sql), the statement runs in a
/// read-only transaction with a timeout, and the model is told the same rules.</summary>
public static partial class SqlGuard
{
    public sealed record Result(bool Ok, string? Sql, string? Reason);

    static readonly string[] Denied = ["insert", "update", "delete", "merge", "drop", "alter", "create", "grant", "revoke", "truncate", "copy",
        "unload", "call", "execute", "exec", "vacuum", "analyze", "set", "reset", "begin", "commit", "rollback", "into", "lock", "comment",
        "pg_sleep", "dblink", "refresh", "declare", "prepare", "listen", "notify", "do"];

    public static Result Check(string? sql, int rowLimit)
    {
        if (string.IsNullOrWhiteSpace(sql)) return new(false, null, "No SQL was produced.");
        var s = sql.Trim();
        if (s.Length > 4000) return new(false, null, "The SQL is too long.");
        if (s.Contains("--") || s.Contains("/*")) return new(false, null, "Comments are not allowed.");
        s = s.TrimEnd(';').Trim();
        var code = StripStrings(s);
        if (code is null) return new(false, null, "Unbalanced quotes.");
        if (code.Contains(';')) return new(false, null, "Only one statement is allowed.");
        if (code.Contains('"')) return new(false, null, "Quoted identifiers are not allowed.");
        var lower = code.ToLowerInvariant();
        if (!Start().IsMatch(lower)) return new(false, null, "Only SELECT statements are allowed.");
        foreach (Match w in Word().Matches(lower))
            if (Denied.Contains(w.Value)) return new(false, null, $"'{w.Value.ToUpperInvariant()}' is not allowed.");
        var ctes = Cte().Matches(lower).Select(m => m.Groups[1].Value).ToHashSet();
        foreach (Match m in Source().Matches(lower))
        {
            var name = m.Groups[1].Value;
            if (name.StartsWith('(')) continue;
            if (ctes.Contains(name)) continue;
            if (!ViewName().IsMatch(name)) return new(false, null, $"Only the dw.v_* views can be queried (found {name}).");
        }
        if (Qualified().Matches(lower).Any(m => !m.Value.StartsWith("dw.v_") && !IsAliasRef(m.Value, lower)))
            return new(false, null, "Only the dw.v_* views can be queried.");
        return new(true, $"SELECT * FROM ({s}) AS q LIMIT {rowLimit}", null);
    }

    // x.col refers to a table alias or CTE; schema-qualified objects other than dw.v_* are refused above via FROM/JOIN.
    static bool IsAliasRef(string qualified, string lower)
    {
        var head = qualified[..qualified.IndexOf('.')];
        return head is not ("pg_catalog" or "information_schema" or "stg" or "landing" or "public" or "dw" or "svv" or "stl" or "sys" or "pg_temp");
    }

    static string? StripStrings(string s)
    {
        var sb = new StringBuilder(s.Length);
        var inStr = false;
        for (var i = 0; i < s.Length; i++)
        {
            var c = s[i];
            if (c == '\'') { if (inStr && i + 1 < s.Length && s[i + 1] == '\'') { i++; continue; } inStr = !inStr; sb.Append('\''); continue; }
            if (c == '$' && !inStr) return null;            // dollar quoting
            if (!inStr) sb.Append(c);
        }
        return inStr ? null : sb.ToString();
    }

    [GeneratedRegex(@"^\s*(select|with)\b")] private static partial Regex Start();
    [GeneratedRegex(@"[a-z_][a-z0-9_]*")] private static partial Regex Word();
    [GeneratedRegex(@"(?:with|,)\s*([a-z_][a-z0-9_]*)\s+as\s*\(")] private static partial Regex Cte();
    [GeneratedRegex(@"\b(?:from|join)\s+(\(|[a-z_][a-z0-9_.]*)")] private static partial Regex Source();
    [GeneratedRegex(@"^dw\.v_[a-z0-9_]+$")] private static partial Regex ViewName();
    [GeneratedRegex(@"\b[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*")] private static partial Regex Qualified();
}
