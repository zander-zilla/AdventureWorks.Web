using System.Text;
using System.Text.Json;
using Amazon.DynamoDBv2.Model;

namespace AdventureWorks.Web.Data;

/// <summary>Opaque page tokens: the LastEvaluatedKey (string keys only) as base64 JSON.</summary>
public static class Paging
{
    public static string? Encode(Dictionary<string, AttributeValue>? lek) =>
        lek is null || lek.Count == 0 ? null
        : Convert.ToBase64String(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(lek.ToDictionary(k => k.Key, k => k.Value.S))));

    public static Dictionary<string, AttributeValue>? Decode(string? token)
    {
        if (string.IsNullOrEmpty(token)) return null;
        try
        {
            var d = JsonSerializer.Deserialize<Dictionary<string, string>>(Encoding.UTF8.GetString(Convert.FromBase64String(token)));
            return d?.ToDictionary(k => k.Key, k => new AttributeValue { S = k.Value });
        }
        catch (FormatException) { return null; }
    }
}
