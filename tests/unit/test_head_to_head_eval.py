"""The head-to-head scorer: name matching, prices, titles and the per-task pass rules (no model calls)."""

from __future__ import annotations

from evaluation.head_to_head import BY_LABEL, Answer, load_tasks, match, names_item, outfits_in, price_of, score


def _id(label: str) -> str:
    return BY_LABEL[label].id


def test_tasks_are_fixed() -> None:
    tasks = load_tasks()  # raises if the file's hash moved
    assert len(tasks) == 30
    assert sum(bool(t.get("manual")) for t in tasks) == 10


def test_match_names_to_closet_items() -> None:
    assert match("the Navy Hoodie") is BY_LABEL["navy hoodie"]
    assert match("white graphic t-shirt") is BY_LABEL["white graphic t-shirt"]
    assert match("brown penny loafers") is BY_LABEL["brown penny loafers"]  # longest label wins
    assert match("grey suit trousers") is None


def test_prices_and_titles() -> None:
    assert price_of("₹2,499") == 2499.0
    assert price_of(1999) == 1999.0
    assert price_of("N/A") is None
    assert names_item("Men White Casual Sneakers", "sneakers", "white")
    assert not names_item("Men Black Casual Sneakers", "sneakers", "white")
    assert names_item("Slim Fit Khaki Chinos", "chinos", "beige")


def test_outfit_task_fails_on_excluded_or_invented_piece() -> None:
    task = {"id": "t", "kind": "exclude", "occasion": "everyday_casual", "exclude": [21],
            "weather": {"temperature_c": 22, "rain": False}}  # fmt: skip
    good = [_id("charcoal t-shirt"), _id("blue jeans"), _id("brown sandals")]
    excluded = [_id("charcoal t-shirt"), _id("blue jeans"), _id("white sneakers")]
    assert score(task, Answer(outfits=[good]), {})["pass"]
    row = score(task, Answer(outfits=[good, excluded, ["red raincoat", _id("blue jeans")]]), {})
    assert not row["pass"]
    assert (row["outfits_using_excluded"], row["invented"], row["valid_outfits"]) == (1, 1, 1)


def test_decline_needs_the_missing_thing_named_with_a_negation() -> None:
    task = {"id": "t", "kind": "decline", "occasion": "beach_resort", "missing": "swim",
            "weather": {"temperature_c": 33, "rain": False}}  # fmt: skip
    assert score(task, Answer(text="Your closet has no swimwear."), {})["pass"]
    assert not score(task, Answer(text="Here is a swim look!"), {})["pass"]


def test_products_need_budget_link_and_title() -> None:
    task = {"id": "t", "kind": "products", "budget": 3000, "want": {"garment_type": "sneakers", "color": "white"}}
    ok = {"title": "x", "price": 2500.0, "link": "https://a"}
    links = {"https://a": {"status": 200, "page_title": "White Sneakers for Men"}, "https://b": {"status": 404}}
    assert score(task, Answer(products=[ok]), links)["pass"]
    over = {**ok, "price": 3500.0}
    dead = {**ok, "link": "https://b"}
    row = score(task, Answer(products=[ok, over, dead]), links)
    assert not row["pass"]
    assert (row["in_budget"], row["opens"]) == (2, 2)


def test_outfits_split_at_labels_or_numbered_lines() -> None:
    a, b, c = (_id(x) for x in ("olive dress", "brown penny loafers", "cream blouse"))
    assert outfits_in(f"1. **Olive dress [{a}]**\n   Loafers [{b}]\n\n2. **Cream blouse [{c}]**") == [[a, b], [c]]
    assert outfits_in(f"1. **Outfit 1**:\n - [{a}]\n - [{b}]\n2. **Outfit 2**:\n - [{c}]") == [[a, b], [c]]
    assert outfits_in(f"Wear the olive dress [{a}] with loafers [{b}].") == [[a, b]]


def test_curly_apostrophe_and_soft_404() -> None:
    task = {"id": "t", "kind": "decline", "occasion": "cocktail_semi_formal", "missing": "heel",
            "weather": {"temperature_c": 21, "rain": False}}  # fmt: skip
    assert score(task, Answer(text="You don’t have any heels listed."), {})["pass"]
    products = {"id": "t", "kind": "products", "budget": 3000, "want": {"garment_type": "sneakers", "color": "white"}}
    p = {"title": "White sneakers", "price": 1999.0, "link": "https://a"}
    assert (
        score(products, Answer(products=[p]), {"https://a": {"status": 200, "page_title": "Page Not Found"}})["opens"]
        == 0
    )
