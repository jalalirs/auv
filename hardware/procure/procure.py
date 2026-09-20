"""The parts list as data, and the tool that puts it in your cart.

    procure list                   what the build needs, by status
    procure cart-url [--open]      one Amazon link that adds every wanted ASIN
    procure login                  open a browser on the tool's own profile; sign in; close it
    procure sync [--dry-run]       make the cart match the list: remove, then add
    procure arrived <id> [k=v...]  mark a part arrived; record the measurements it gates
    procure ordered <id>...        mark parts ordered today

It never holds a password. `login` and `sync` drive a Chromium profile that
you sign into yourself; Amazon's cookies live there, the way they live in
your everyday browser. `cart-url` needs no browser of its own: Amazon
accepts a URL that adds ASINs to the cart of whoever opens it, after a
sign-in prompt if the browser is not already signed in.

Nothing here buys anything.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys
import webbrowser

HERE = pathlib.Path(__file__).resolve().parent
PARTS = HERE / "parts.json"


# ── the registry ─────────────────────────────────────────────────────────────

def load() -> dict:
    return json.loads(PARTS.read_text())


def save(data: dict) -> None:
    PARTS.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def wanted_asins(data: dict) -> list[tuple[str, int, dict]]:
    out = []
    for p in data["parts"]:
        asin = (p.get("source") or {}).get("amazon")
        if p["status"] == "wanted" and asin:
            out.append((asin, int(p["qty"]), p))
    return out


def env() -> dict:
    try:
        from dotenv import dotenv_values
        values = {**dotenv_values(HERE / ".env")}
    except ImportError:
        values = {}
    values.setdefault("AMAZON_DOMAIN", "amazon.sa")
    values.setdefault("AMAZON_PROFILE_DIR", "~/.cache/procure/amazon-profile")
    values["AMAZON_PROFILE_DIR"] = os.path.expanduser(values["AMAZON_PROFILE_DIR"])
    values["KEEP"] = [a.strip() for a in (values.get("KEEP") or "").split(",") if a.strip()]
    return values


# ── list ─────────────────────────────────────────────────────────────────────

def cmd_list(args) -> int:
    data = load()
    cur = data.get("currency", "")
    order = ["wanted", "ordered", "arrived", "measured", "dropped"]
    for status in order:
        rows = [p for p in data["parts"] if p["status"] == status]
        if not rows:
            continue
        total = sum(p["price"] * p["qty"] for p in rows)
        print(f"\n{status.upper()}  ({len(rows)} lines, {total:,.0f} {cur})")
        for p in rows:
            src = p.get("source") or {}
            where = src.get("amazon") and f"amazon {src['amazon']}" or src.get("shop") or (src.get("url") and "maker's site") or "-"
            gate = f"  gates {', '.join(p['gates'])}" if p.get("gates") and status in ("wanted", "ordered") else ""
            print(f"  {p['id']:14s} ×{p['qty']:<2d} {p['price']:8.2f}  {where:22s} {p['pick'][:70]}{gate}")
    return 0


# ── cart-url ─────────────────────────────────────────────────────────────────

def cart_url(data: dict, domain: str) -> str:
    items = wanted_asins(data)
    q = "&".join(f"ASIN.{i}={a}&Quantity.{i}={n}" for i, (a, n, _) in enumerate(items, 1))
    return f"https://www.{domain}/gp/aws/cart/add.html?{q}"


def cmd_cart_url(args) -> int:
    data, e = load(), env()
    items = wanted_asins(data)
    print(f"{len(items)} lines from Amazon:")
    for a, n, p in items:
        print(f"  {a}  ×{n}  {p['pick'][:70]}")
    url = cart_url(data, e["AMAZON_DOMAIN"])
    print("\n" + url)
    others = [p for p in data["parts"] if p["status"] == "wanted" and not (p.get("source") or {}).get("amazon")]
    if others:
        print("\nNot on Amazon, buy separately:")
        for p in others:
            src = p.get("source") or {}
            print(f"  {p['id']:14s} ×{p['qty']}  {src.get('url') or src.get('shop')}  {p['pick'][:60]}")
    if args.open:
        webbrowser.open(url)
    return 0


# ── the browser: login and sync ──────────────────────────────────────────────

def browser(e: dict, headless: bool):
    from playwright.sync_api import sync_playwright

    pathlib.Path(e["AMAZON_PROFILE_DIR"]).mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    ctx = pw.chromium.launch_persistent_context(e["AMAZON_PROFILE_DIR"], headless=headless,
                                                viewport={"width": 1280, "height": 900})
    return pw, ctx


def cmd_login(args) -> int:
    e = env()
    pw, ctx = browser(e, headless=False)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(f"https://www.{e['AMAZON_DOMAIN']}/gp/cart/view.html")
    print("A browser is open. Sign in if it asks, wait until your cart shows, then close the window.")
    try:
        page.wait_for_event("close", timeout=0)
    except Exception:
        pass
    ctx.close()
    pw.stop()
    print(f"Session kept in {e['AMAZON_PROFILE_DIR']}")
    return 0


def read_cart(page, cart: str) -> list[dict]:
    """What is in the cart now: ASIN, quantity, title, and the item's id
    Amazon uses for its own delete button."""
    page.goto(cart)
    page.wait_for_timeout(1500)
    return page.evaluate("""() => [...document.querySelectorAll('[data-asin][data-itemid], .sc-list-item[data-asin]')]
        .map(d => ({asin: d.dataset.asin, itemId: d.dataset.itemid || null,
                    qty: parseInt(d.querySelector('[name="quantityBox"], .a-dropdown-prompt, .sc-quantity-textfield')?.value
                                  || d.querySelector('.a-dropdown-prompt')?.innerText || '1', 10),
                    title: (d.querySelector('.sc-product-title, .a-truncate-cut')?.innerText || '').trim().slice(0, 80)}))""")


def cmd_sync(args) -> int:
    data, e = load(), env()
    want = {a: (n, p) for a, n, p in wanted_asins(data)}
    keep = set(e["KEEP"])
    pw, ctx = browser(e, headless=False)
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    cart = f"https://www.{e['AMAZON_DOMAIN']}/gp/cart/view.html"
    page.goto(cart)
    if "signin" in page.url or page.locator("#ap_email, #ap_email_login").count():
        print("Not signed in on this profile. Run `procure login` first.")
        ctx.close(); pw.stop()
        return 2
    now = read_cart(page, cart)
    print(f"Cart has {len(now)} lines.")
    # 1. Remove what is not wanted.
    for item in now:
        if item["asin"] in want or item["asin"] in keep:
            continue
        print(f"  remove  {item['asin']}  {item['title']}")
        if not args.dry_run:
            row = page.locator(f'.sc-list-item[data-asin="{item["asin"]}"], [data-itemid][data-asin="{item["asin"]}"]').first
            # Amazon's "item removed" message also carries data-action=delete
            # and is hidden, so ask for the visible control only.
            btn = row.locator('input[data-action="delete"], input[value="Delete"], .sc-action-delete input, .sc-action-delete a')
            btn = btn.locator("visible=true").first
            if btn.count() == 0:
                btn = row.get_by_role("button", name="Delete").first
            btn.click(timeout=10000)
            page.wait_for_timeout(2000)
    # 2. Add or fix what is.
    have = {i["asin"]: i["qty"] for i in read_cart(page, cart)} if not args.dry_run else {i["asin"]: i["qty"] for i in now}
    missing = [(a, n) for a, (n, p) in want.items() if have.get(a, 0) != n]
    for a, n in missing:
        print(f"  add     {a}  ×{n}  {want[a][1]['pick'][:60]}")
    if missing and not args.dry_run:
        q = "&".join(f"ASIN.{i}={a}&Quantity.{i}={n}" for i, (a, n) in enumerate(missing, 1))
        page.goto(f"https://www.{e['AMAZON_DOMAIN']}/gp/aws/cart/add.html?{q}")
        page.wait_for_timeout(2500)
        # The add-by-URL page lists the items and waits for a confirmation.
        confirm = page.locator('input[name="add"], input[value="Add to Cart"], input[value="Add to cart"], '
                               '#add-to-cart-button, button:has-text("Add to cart"), input[type="submit"][value*="Cart"]')
        if confirm.locator("visible=true").count():
            confirm.locator("visible=true").first.click()
            page.wait_for_timeout(3000)
        have = {i["asin"]: i["qty"] for i in read_cart(page, cart)}
        failed = []
        # Whatever is still missing goes in from its own product page.
        for a, n in missing:
            if have.get(a, 0) == n:
                continue
            print(f"  adding {a} from its product page")
            page.goto(f"https://www.{e['AMAZON_DOMAIN']}/dp/{a}")
            page.wait_for_timeout(2500)
            qty = page.locator("#quantity")
            if qty.count() and n > 1:
                try:
                    qty.select_option(str(n))
                except Exception:
                    pass
            button = page.locator('#add-to-cart-button, input[name="submit.add-to-cart"], '
                                  'button:has-text("Add to cart"), input[value="Add to Cart"], '
                                  '[data-csa-c-content-id*="add-to-cart"] button').locator("visible=true")
            try:
                button.first.click(timeout=10000)
                page.wait_for_timeout(3000)
            except Exception:
                failed.append((a, n))
                print(f"  could not find an add button on {a}; add it by hand: https://www.{e['AMAZON_DOMAIN']}/dp/{a}")
        final = read_cart(page, cart)
        print(f"Cart now has {len(final)} lines:")
        for i in final:
            mark = "ok" if i["asin"] in want and i["qty"] == want[i["asin"]][0] else ("keep" if i["asin"] in keep else "??")
            print(f"  {mark:4s} {i['asin']}  ×{i['qty']}  {i['title']}")
        still = [a for a in want if a not in {i["asin"] for i in final}]
        for a in still:
            print(f"  MISSING {a}  ×{want[a][0]}  {want[a][1]['pick'][:60]}  → https://www.{e['AMAZON_DOMAIN']}/dp/{a}")
    print("\nNothing was bought. Check out when you are ready.")
    if not args.dry_run:
        print("The window stays open for you; close it when done.")
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
    ctx.close(); pw.stop()
    return 0


# ── arrived / ordered ────────────────────────────────────────────────────────

def cmd_ordered(args) -> int:
    data = load()
    today = dt.date.today().isoformat()
    for p in data["parts"]:
        if p["id"] in args.ids:
            p["status"] = "ordered"; p["ordered"] = today
            print(f"{p['id']}: ordered {today}")
    save(data)
    return 0


def cmd_arrived(args) -> int:
    data = load()
    part = next((p for p in data["parts"] if p["id"] == args.id), None)
    if part is None:
        print(f"no part {args.id}"); return 2
    values = dict(kv.split("=", 1) for kv in args.kv)
    if part.get("measure") and not values:
        print(f"{part['id']} gates {', '.join(part.get('gates', []))}. Measure and record:")
        for m in part["measure"]:
            print(f"  - {m}")
        print(f"then: procure arrived {part['id']} key=value ...")
        part["status"] = "arrived"
        save(data)
        return 0
    part["status"] = "measured" if values else "arrived"
    part["arrived"] = dt.date.today().isoformat()
    if values:
        part["measured"] = {**part.get("measured", {}), **values}
        print(f"{part['id']}: recorded {values}")
        if part.get("gates"):
            print(f"update in the model: {', '.join(part['gates'])}")
    save(data)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="procure", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    c = sub.add_parser("cart-url"); c.add_argument("--open", action="store_true"); c.set_defaults(fn=cmd_cart_url)
    sub.add_parser("login").set_defaults(fn=cmd_login)
    s = sub.add_parser("sync"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(fn=cmd_sync)
    o = sub.add_parser("ordered"); o.add_argument("ids", nargs="+"); o.set_defaults(fn=cmd_ordered)
    a = sub.add_parser("arrived"); a.add_argument("id"); a.add_argument("kv", nargs="*"); a.set_defaults(fn=cmd_arrived)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
