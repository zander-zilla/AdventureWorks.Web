using AdventureWorks.Web.Ai;
using Microsoft.Extensions.Logging.Abstractions;

namespace AdventureWorks.Web.Tests;

/// <summary>C2-6 AI everywhere: shared assist service, output checks, per-feature options and the mocked model's golden cases.</summary>
public sealed class AssistTests
{
    static AiAssist Assist(AiOptions? o = null)
    {
        o ??= new AiOptions { Enabled = true };
        return new AiAssist(new MockAssistModel(), new AiBudget(o, TimeProvider.System), o, NullLogger<AiAssist>.Instance);
    }

    internal static Dictionary<string, object?> Order(int lines = 2, int[]? stock = null, int age = 1, int median = 2, int prior = 3)
    {
        var f = new Dictionary<string, object?>
        {
            ["order.number"] = "SO43697", ["order.status"] = "In process", ["order.status_age_days"] = age, ["order.total_due"] = 3953.99m,
            ["order.lines"] = lines, ["order.ship_method"] = "CARGO TRANSPORT 5", ["queue.count"] = 12, ["queue.median_age_days"] = median,
            ["customer.prior_orders"] = prior, ["customer.last_order_date"] = prior == 0 ? null : "2013-07-22",
        };
        var can = true;
        for (var i = 1; i <= lines; i++)
        {
            var st = stock?[i - 1] ?? 100; var qty = 4; var sh = Math.Max(0, qty - st); if (sh > 0) can = false;
            f[$"line{i}.product"] = i == 1 ? "HL Road Frame - Red, 62" : $"Sport-100 Helmet, Blue"; f[$"line{i}.qty"] = qty; f[$"line{i}.stock"] = (decimal)st;
            f[$"line{i}.short"] = (decimal)sh; f[$"line{i}.reorder_point"] = 375;
        }
        f["order.can_ship"] = can;
        return f;
    }

    // Golden cases for the triage copilot: (facts, kind, expected fragment).
    public static IEnumerable<object[]> TriageGolden() =>
    [
        [Order(), "triage-explain", "Looks fine"],
        [Order(stock: [0, 100]), "triage-explain", "has 0 in stock but needs 4 [line1.short]"],
        [Order(stock: [2, 1]), "triage-explain", "line 2 Sport-100 Helmet, Blue has 1 in stock"],
        [Order(age: 31, median: 2), "triage-explain", "for 31 days vs a queue median of 2 days"],
        [Order(prior: 0), "triage-explain", "first order [customer.prior_orders]"],
        [Order(stock: [0, 0], age: 40, median: 3, prior: 0), "triage-explain", "Needs attention"],
        [Order(), "triage-approve-note", "Approved SO43697 [order.number]: all 2 lines in stock"],
        [Order(lines: 1), "triage-approve-note", "3953.99 due"],
        [Order(stock: [1, 100]), "triage-backorder-note", "HL Road Frame - Red, 62 short by 3 (in stock 1, ordered 4) [line1.short]"],
        [Order(), "triage-backorder-note", "at the clerk's request"],
    ];

    [Theory, MemberData(nameof(TriageGolden))]
    public async Task Triage_golden_cases_pass_the_output_checks(Dictionary<string, object?> facts, string kind, string expected)
    {
        var r = await Assist().RunAsync("triage", kind, facts, "s", "u");
        Assert.Null(r.Error); Assert.Null(r.Blocked);
        Assert.Contains(expected, r.Text);
        Assert.NotEmpty(r.Cites);
        Assert.All(r.Cites, c => Assert.True(facts.ContainsKey(c)));
    }

    [Theory]
    [InlineData("Order SO43697 has 17 missing units [order.number].", "number 17")]
    [InlineData("Call 555-123-4567 about SO43697 [order.number].", "phone")]
    [InlineData("Mail jon@example.com about SO43697 [order.number].", "e-mail")]
    [InlineData("Everything is fine.", "no fact cited")]
    [InlineData("", "empty")]
    public void Output_check_rejects_invented_numbers_contacts_and_uncited_text(string text, string reason) =>
        Assert.Contains(reason, AiAssist.Check(text, Order()));

    [Fact] public void Output_check_rejects_long_text() =>
        Assert.Contains("longer", AiAssist.Check(new string('a', 1300) + " [order.number]", Order()));

    [Fact] public void Output_check_accepts_rounded_and_percent_forms()
    {
        var f = new Dictionary<string, object?> { ["x.rate"] = 0.2734, ["x.total"] = 1234.5678m };
        Assert.Null(AiAssist.Check("Rate 27 percent, total 1,234.57 [x.rate] [x.total].", f));
    }

    [Fact] public void Features_fall_back_to_the_ask_settings_and_shop_uses_its_own()
    {
        var o = new AiOptions { ChatModel = "m-pro", GuardrailId = "g-ask", GuardrailVersion = "3" };
        Assert.Equal(new AiFeature("triage", "m-pro", "g-ask", "3"), o.Feature("triage"));
        Assert.Equal("amazon.nova-lite-v1:0", o.Feature("shop").Model);
        Assert.Equal("g-ask", o.Feature("shop").GuardrailId);
        o.Features["shop"] = new AiFeatureOptions { Model = "lite", GuardrailId = "g-shop" };
        Assert.Equal(new AiFeature("shop", "lite", "g-shop", "DRAFT"), o.Feature("shop"));
        Assert.Equal("g-ask", o.Feature("ask").GuardrailId);
    }

    [Fact] public async Task Assist_spends_the_shared_session_budget()
    {
        var o = new AiOptions { Enabled = true, SessionQuestions = 1 };
        var a = Assist(o);
        Assert.Null((await a.RunAsync("triage", "triage-explain", Order(), "s", "u")).Blocked);
        Assert.Equal("Session budget used up for today.", (await a.RunAsync("triage", "triage-explain", Order(), "s", "u")).Blocked);
    }

    [Fact] public void Turn_budget_per_feature()
    {
        var b = new AiBudget(new AiOptions(), TimeProvider.System);
        b.Turn("s", "shop"); b.Turn("s", "shop");
        Assert.Equal(8, b.TurnsLeft("s", "shop", 10));
        Assert.Equal(10, b.TurnsLeft("other", "shop", 10));
    }

    [Fact] public void Every_kind_has_a_prompt_with_the_rules()
    {
        foreach (var k in new[] { "triage-explain", "triage-approve-note", "triage-backorder-note", "reorder-explain", "po-email", "watchdog-explain", "shop-reply" })
        {
            var p = AssistPrompts.For(k);
            Assert.Contains("Cite every fact", p);
            Assert.True(p.Length > AssistPrompts.Rules.Length + 40, k);
        }
    }
}
