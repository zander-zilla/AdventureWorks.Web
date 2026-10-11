// BEFORE BASELINE (demo-only): minimal customer login for the live CDC demo.
// Not production auth: a handful of seeded demo users mapped to existing SalesLT.Customer rows.
using System.Collections.Generic;
using System.Linq;

namespace AdventureWorks.Web.Demo
{
    public class DemoCustomer
    {
        public string Email { get; set; }
        public int CustomerId { get; set; }
        public int AddressId { get; set; }
        public string DisplayName { get; set; }
    }

    public static class DemoCustomers
    {
        // Shared demo password for all seeded users (demo only).
        public const string Password = "Demo!2026";

        public static readonly IReadOnlyList<DemoCustomer> All = new List<DemoCustomer>
        {
            new DemoCustomer { Email = "catherine0@adventure-works.com", CustomerId = 29485, AddressId = 1086, DisplayName = "Catherine Abel" },
            new DemoCustomer { Email = "cory0@adventure-works.com",      CustomerId = 29531, AddressId = 1061, DisplayName = "Cory Booth" },
            new DemoCustomer { Email = "christopher1@adventure-works.com", CustomerId = 29546, AddressId = 635, DisplayName = "Christopher Beck" },
            new DemoCustomer { Email = "donald0@adventure-works.com",    CustomerId = 29568, AddressId = 993,  DisplayName = "Donald Blanton" },
            new DemoCustomer { Email = "walter0@adventure-works.com",    CustomerId = 29584, AddressId = 1014, DisplayName = "Walter Brian" },
        };

        public static DemoCustomer Find(string email) =>
            All.FirstOrDefault(c => string.Equals(c.Email, email?.Trim(), System.StringComparison.OrdinalIgnoreCase));
    }
}
