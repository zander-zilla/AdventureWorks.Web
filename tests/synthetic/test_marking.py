"""C2-7 marking: generated rows map to DynamoDB items with syn = 1 (bulk loader and CDC transform share awmap);
original rows are untouched (no syn attribute), and the SQL predicates match the Python rule."""
import datetime as dt, os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "scripts", "loader")); sys.path.insert(0, os.path.join(ROOT, "scripts", "synthetic"))
import awmap  # noqa: E402
from marking import original_where, synthetic_where  # noqa: E402

M = awmap.load_mapping()


def items(table, row):
    return awmap.items_for_row(table, M["sources"][table], row, ["ProductReviewID"])


def review(i):
    return {"ProductReviewID": i, "ProductID": 709, "ReviewerName": "A", "ReviewDate": dt.datetime(2015, 1, 2), "EmailAddress": "a@adventure-works.com",
            "Rating": 5, "Comments": "x", "ModifiedDate": dt.datetime(2015, 1, 2)}


def test_generated_items_get_syn_and_originals_do_not():
    (_, gen), = items("Production.ProductReview", review(50001))
    (_, orig), = items("Production.ProductReview", review(4))
    assert gen["syn"] == 1 and "syn" not in orig
    assert {k for k in gen if k != "syn"} == set(orig)


def test_date_floors_and_any_rule():
    assert awmap.is_synthetic("Production.ProductListPriceHistory", {"ProductID": 707, "StartDate": dt.datetime(2015, 7, 1)})
    assert not awmap.is_synthetic("Production.ProductListPriceHistory", {"ProductID": 707, "StartDate": dt.datetime(2013, 5, 30)})
    assert awmap.is_synthetic("Sales.SpecialOfferProduct", {"SpecialOfferID": 1, "ProductID": 5003})
    assert not awmap.is_synthetic("Sales.SpecialOfferProduct", {"SpecialOfferID": 1, "ProductID": 707})
    assert not awmap.is_synthetic("Sales.SalesTerritory", {"TerritoryID": 1})


def test_sql_predicates():
    assert synthetic_where("Sales.SalesOrderHeader", "h") == "(h.[SalesOrderID] >= 1000000)"
    assert original_where("Sales.SpecialOfferProduct") == "NOT ([SpecialOfferID] >= 100 OR [ProductID] >= 5000)"
    assert original_where("Sales.SalesTerritory") == "1 = 1"


def test_every_generated_table_is_mapped():
    assert set(awmap.SYNTHETIC) <= set(M["sources"])
