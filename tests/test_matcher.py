import pytest
from app.matcher import matches_keyword


def test_matcher_exact_and_case_insensitive():
    assert matches_keyword("PRICE", "PRICE")
    assert matches_keyword("PRICE", "price")
    assert matches_keyword("PRICE", "PrIcE")
    assert matches_keyword("price", "PRICE")


def test_matcher_anywhere_in_text():
    assert matches_keyword("PRICE", "PRICE please 🙏")
    assert matches_keyword("PRICE", "Can I get the price?")
    assert matches_keyword("PRICE", "Hello, what is your price for this item?")
    assert matches_keyword("PRICE", "price\nlist please")
    assert matches_keyword("PRICE", "price.")
    assert matches_keyword("PRICE", "(PRICE)")
    assert matches_keyword("PRICE", "PRICE!")


def test_matcher_sensible_boundaries():
    # Should not match substrings inside unrelated words
    assert not matches_keyword("PRICE", "priceless")
    assert not matches_keyword("PRICE", "enterprise")
    assert not matches_keyword("PRICE", "appreciation")


def test_matcher_multiword_and_special_chars():
    assert matches_keyword("PRICE LIST", "Here is the price list for 2026")
    assert matches_keyword("PRICE LIST", "price list please!")
    assert not matches_keyword("PRICE LIST", "price only")


def test_matcher_empty_or_none():
    assert not matches_keyword("", "some text")
    assert not matches_keyword("PRICE", "")
    assert not matches_keyword("PRICE", None)
