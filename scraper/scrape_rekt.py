"""
rekt.news Playwright scraper
Extracts all -rekt exploit post-mortems with full metadata.

Usage:
    pip install playwright beautifulsoup4
    playwright install chromium
    python scraper/scrape_rekt.py
"""

import asyncio
import csv
import os
import re
import zipfile
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

BASE_URL = "https://rekt.news"
DATA_DIR = Path(__file__).parent.parent / "data"
RAW_DIR = DATA_DIR / "raw"
FAILURES_LOG = Path(__file__).parent / "failures.log"

# Regex patterns
RE_ETH_ADDR = re.compile(r'0x[a-fA-F0-9]{40}(?![a-fA-F0-9])')
RE_TX_HASH  = re.compile(r'0x[a-fA-F0-9]{64}(?![a-fA-F0-9])')
RE_AMOUNT   = re.compile(
    r'\$[\d,]+(?:\.\d+)?\s*(?:million|billion|thousand|[MBK])\b'
    r'|\$[\d,]{4,}',
    re.IGNORECASE,
)


def slug_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def is_exploit_url(url: str) -> bool:
    slug = slug_from_url(url)
    return slug.endswith("-rekt")


async def get_article_links(page, page_num: int) -> list[tuple[str, str]]:
    """Return list of (title, url) from one listing page."""
    if page_num == 0:
        url = BASE_URL + "/"
    else:
        url = f"{BASE_URL}/?page={page_num}"

    await page.goto(url, wait_until="networkidle")
    await asyncio.sleep(2)

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    articles = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("https://rekt.news/") and is_exploit_url(href):
            title = a.get_text(strip=True)
            if title:
                articles.append((title, href))

    # Also check relative links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("/") and not href.startswith("//") and is_exploit_url(href):
            full = BASE_URL + href
            title = a.get_text(strip=True)
            if title and full not in [u for _, u in articles]:
                articles.append((title, full))

    return articles


def extract_amount(text: str) -> str:
    matches = RE_AMOUNT.findall(text)
    if not matches:
        return ""
    # Return the first match (usually in the lede)
    return matches[0].strip()


async def scrape_article(page, url: str) -> dict:
    """Scrape a single article page. Returns metadata dict."""
    await page.goto(url, wait_until="networkidle")
    await asyncio.sleep(2)

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # Title
    title_el = soup.find("h1") or soup.find("h2")
    title = title_el.get_text(strip=True) if title_el else slug_from_url(url)

    # Date
    date_str = ""
    time_el = soup.find("time")
    if time_el:
        date_str = time_el.get("datetime", "") or time_el.get_text(strip=True)
    if not date_str:
        for el in soup.find_all(class_=re.compile(r"date|time|publish", re.I)):
            t = el.get_text(strip=True)
            if t:
                date_str = t
                break

    # Normalise date to YYYY-MM-DD
    date_clean = ""
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y", "%d %b %Y"):
        try:
            date_clean = datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
            break
        except ValueError:
            pass
    if not date_clean:
        # Try ISO prefix
        m = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
        date_clean = m.group(1) if m else "0000-00-00"

    # Tags
    tags = []
    tag_section = soup.find(class_=re.compile(r"tag|label|category", re.I))
    if tag_section:
        for a in tag_section.find_all("a"):
            t = a.get_text(strip=True)
            if t:
                tags.append(t)

    # Body text
    main = soup.find("main") or soup.find("article") or soup.find(class_=re.compile(r"content|body|post", re.I))
    body_parts = []
    container = main if main else soup
    skip_phrases = {"subscribe", "log in", "t&c", "all rights reserved", "copyright", "donate"}
    for tag in container.find_all(["p", "h1", "h2", "h3", "h4", "h5", "blockquote", "li"]):
        text = tag.get_text(separator=" ", strip=True)
        low = text.lower()
        if any(s in low for s in skip_phrases):
            continue
        if len(text) > 15:
            body_parts.append(text)

    body = "\n\n".join(body_parts)
    full_text = body

    # Extract addresses and hashes from full page text
    page_text = soup.get_text()
    eth_addresses = sorted(set(RE_ETH_ADDR.findall(page_text)))
    tx_hashes = sorted(set(
        h for h in RE_TX_HASH.findall(page_text)
        if h not in eth_addresses  # 66-char hashes won't match 40-char, but be safe
    ))
    amount = extract_amount(body or page_text)

    return {
        "title": title,
        "date": date_clean,
        "date_raw": date_str,
        "tags": tags,
        "url": url,
        "slug": slug_from_url(url),
        "amount_lost": amount,
        "eth_addresses": eth_addresses,
        "tx_hashes": tx_hashes,
        "body": full_text,
    }


def build_file_content(article: dict) -> str:
    addrs = ", ".join(article["eth_addresses"]) if article["eth_addresses"] else "none found"
    hashes = ", ".join(article["tx_hashes"]) if article["tx_hashes"] else "none found"
    tags = ", ".join(article["tags"]) if article["tags"] else ""
    lines = [
        f"Title: {article['title']}",
        f"Date: {article['date']}",
        f"Tags: {tags}",
        f"URL: {article['url']}",
        f"Amount Lost: {article['amount_lost']}",
        f"Attacker Addresses: {addrs}",
        f"Transaction Hashes: {hashes}",
        "=" * 60,
        "",
        article["body"],
    ]
    return "\n".join(lines)


async def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    all_addresses = []  # (address, label, slug, date)
    all_tx_hashes = []  # (tx_hash, context, slug, date)
    failures = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        # ── Phase 1: Collect all exploit article links ──────────────────
        print("Phase 1 — Collecting exploit article links from 40 pages...")
        seen_urls: set[str] = set()
        all_articles: list[tuple[str, str]] = []

        for page_num in range(0, 40):
            try:
                links = await get_article_links(page, page_num)
                new = [(t, u) for t, u in links if u not in seen_urls]
                for t, u in new:
                    seen_urls.add(u)
                    all_articles.append((t, u))
                print(f"  Page {page_num:02d}/39 — {len(new)} new exploit links ({len(all_articles)} total)")
            except Exception as e:
                print(f"  Page {page_num} ERROR: {e}")
            await asyncio.sleep(2)

        print(f"\nFound {len(all_articles)} unique exploit articles.\n")

        # ── Phase 2: Scrape each article ────────────────────────────────
        print("Phase 2 — Scraping articles...")
        scraped: list[dict] = []

        for i, (title, url) in enumerate(all_articles, 1):
            slug = slug_from_url(url)
            try:
                article = await scrape_article(page, url)
                scraped.append(article)

                # Save .txt file
                filename = f"{article['date']}_{slug}.txt"
                filepath = RAW_DIR / filename
                filepath.write_text(build_file_content(article), encoding="utf-8")

                # Collect addresses/hashes
                for addr in article["eth_addresses"]:
                    all_addresses.append((addr, "attacker/unknown", slug, article["date"]))
                for txh in article["tx_hashes"]:
                    ctx = f"from {article['title']}"
                    all_tx_hashes.append((txh, ctx, slug, article["date"]))

                char_count = len(article["body"])
                addr_count = len(article["eth_addresses"])
                print(f"  [{i:3d}/{len(all_articles)}] Scraped {slug} ({char_count:,} chars, {addr_count} addresses found)")

            except Exception as e:
                msg = f"  [{i:3d}/{len(all_articles)}] FAILED {slug}: {e}"
                print(msg)
                failures.append(msg)

            # Polite delay: 2–3 seconds
            await asyncio.sleep(2.5)

        await browser.close()

    # ── Phase 3: Write CSVs ─────────────────────────────────────────────
    addr_csv = DATA_DIR / "all_addresses.csv"
    with open(addr_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["address", "label", "article_slug", "article_date"])
        w.writerows(all_addresses)
    print(f"\nWrote {len(all_addresses)} addresses → {addr_csv}")

    tx_csv = DATA_DIR / "all_tx_hashes.csv"
    with open(tx_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tx_hash", "context", "article_slug", "article_date"])
        w.writerows(all_tx_hashes)
    print(f"Wrote {len(all_tx_hashes)} tx hashes → {tx_csv}")

    # ── Phase 4: Zip raw files ──────────────────────────────────────────
    zip_path = DATA_DIR / "rekt_exploits_dataset.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(RAW_DIR.glob("*.txt")):
            zf.write(f, f.name)
    print(f"Zipped {len(scraped)} files → {zip_path}")

    # ── Failures log ────────────────────────────────────────────────────
    if failures:
        FAILURES_LOG.write_text("\n".join(failures), encoding="utf-8")
        print(f"\n{len(failures)} failures logged to {FAILURES_LOG}")

    print(f"\nDone. {len(scraped)}/{len(all_articles)} articles scraped successfully.")


if __name__ == "__main__":
    asyncio.run(main())
