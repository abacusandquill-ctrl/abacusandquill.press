#!/usr/bin/env python3
"""Abacus & Quill public book catalog and price-cap matching CLI.

Discovery and retailer handoff ONLY. This tool does not place orders,
process payments, authenticate with retailers, or guarantee current prices.

Usage:
  python3 agent-catalog.py catalog
  python3 agent-catalog.py offers --book the-flying-sandolo
  python3 agent-catalog.py offers --max-price 10 --currency USD
  python3 agent-catalog.py offers --format kindle --max-price 8.00

Python 3.9+; standard library only.
"""
import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CATALOG_URL = "https://abacusandquill.press/catalog.json"


def load_catalog():
    req = Request(CATALOG_URL, headers={"Accept": "application/json", "User-Agent": "AbacusQuillCatalogReader/1.0"})
    with urlopen(req, timeout=12) as response:
        return json.load(response)


def affordable(amount, cap):
    try:
        return Decimal(str(amount)) <= Decimal(str(cap))
    except (InvalidOperation, TypeError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("catalog", help="Return the complete public catalog")
    offers = sub.add_parser("offers", help="Return retailer destinations; optionally filter by a spending cap")
    offers.add_argument("--book", default="the-flying-sandolo", help="Book identifier")
    offers.add_argument("--format", choices=["kindle", "paperback"], help="Preferred edition")
    offers.add_argument("--max-price", help="Maximum total item price (excluding taxes and fees)")
    offers.add_argument("--currency", default="USD", help="ISO currency for --max-price (currently USD)")
    args = parser.parse_args()

    if args.command == "offers" and args.max_price is not None:
        try:
            if Decimal(args.max_price) < 0:
                parser.error("--max-price must be nonnegative")
        except InvalidOperation:
            parser.error("--max-price must be a valid decimal amount")

    catalog = load_catalog()
    if args.command == "catalog":
        print(json.dumps(catalog, ensure_ascii=False, indent=2))
        return 0

    if args.currency != "USD":
        parser.error("Only USD offers are currently published. Never infer currency conversion.")

    books = [b for b in catalog.get("books", []) if b.get("id") == args.book]
    if not books:
        print(json.dumps({"status": "book_not_found", "book_id": args.book, "automatic_order_placement": False}, indent=2))
        return 0

    matches = []
    for item in books[0].get("formats", []):
        if args.format and item.get("id") != args.format:
            continue
        if item.get("price", {}).get("currency") != args.currency:
            continue
        eligible = args.max_price is None or affordable(item["price"]["amount"], args.max_price)
        available = item.get("availability") in ("preorder", "on_sale") and bool(item.get("purchase_url"))
        matches.append({
            "format": item.get("id"),
            "isbn": item.get("isbn"),
            "price": item.get("price"),
            "within_item_price_cap": eligible,
            "availability": item.get("availability"),
            "release_date": item.get("release_date"),
            "retailer": item.get("retailer"),
            "retailer_handoff_url": item.get("purchase_url") if eligible and available else None,
            "can_place_order": False,
        })

    print(json.dumps({
        "book": args.book,
        "buyer_max_item_price": args.max_price,
        "currency": args.currency,
        "offers": matches,
        "automatic_order_placement": False,
        "checkout_note": "No purchase is completed. A retailer handoff URL is not an order. Verify live retailer price, taxes, and availability. Use an authorized retailer checkout to pay.",
        "price_cap_note": "The cap applies to the item price only; taxes and any fees are not included.",
        "discount_available": False,
        "catalog_url": CATALOG_URL,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError) as err:
        print(json.dumps({"status": "catalog_unavailable", "error": str(err), "automatic_order_placement": False}), file=sys.stderr)
        sys.exit(1)
