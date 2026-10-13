"""C2-7 marking helpers on top of awmap.SYNTHETIC (the single source of the key ranges)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "loader"))
from awmap import SYNTHETIC, is_synthetic  # noqa: F401


def synthetic_where(table, alias=None):
    """SQL predicate that is true for generated rows of `table` (false for tables that never get generated rows)."""
    rules = SYNTHETIC.get(table)
    if not rules:
        return "1 = 0"
    a = (alias + ".") if alias else ""
    return "(" + " OR ".join("%s[%s] >= %s" % (a, c, ("'%s'" % f) if isinstance(f, str) else f) for c, f in rules) + ")"


def original_where(table, alias=None):
    """SQL predicate for the original AdventureWorks rows (what the Chapter 1 evidence and reconcile check)."""
    return "NOT " + synthetic_where(table, alias) if table in SYNTHETIC else "1 = 1"
