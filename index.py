"""
Fragment Username Checker API
Developer: @sagarkun0
Channel: @foryoubysagar
"""

import re
import json
from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
from bs4 import BeautifulSoup

app = FastAPI(
    title="Fragment Username Checker API",
    description="Check if a Telegram username is on Fragment marketplace",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


async def get_ton_prices() -> tuple[float | None, float | None]:
    """Fetch live TON price in USD and INR from CoinGecko."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "the-open-network",
                    "vs_currencies": "usd,inr"
                }
            )
            data = resp.json()
            ton = data["the-open-network"]
            return ton["usd"], ton["inr"]
    except Exception:
        # Fallback approximate values
        return 5.0, 415.0


async def scrape_fragment(username: str) -> tuple[float | None, str]:
    """
    Scrape fragment.com for username price and status.
    Returns (price_in_ton, state) where state is 'fragment' | 'free' | 'error'
    """
    clean = username.lower().strip()
    url = f"https://fragment.com/username/{clean}"

    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers=HEADERS
        ) as client:
            resp = await client.get(url)

        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # ── Strategy 1: look for TON price in the raw HTML ──────────────────
        # Fragment renders prices like "5,000 TON" or "200TON" in the page
        ton_pattern = re.compile(r'([\d,]+(?:\.\d+)?)\s*TON', re.IGNORECASE)
        matches = ton_pattern.findall(html)

        # Filter out obviously irrelevant matches (e.g. "0 TON" from fee text)
        valid_prices = []
        for m in matches:
            val = float(m.replace(",", ""))
            if val > 0:
                valid_prices.append(val)

        # ── Strategy 2: check for known Fragment price CSS classes ───────────
        price_selectors = [
            ".tm-section-header-status",
            ".table-cell-value",
            "[class*='price']",
            "[class*='ton']",
            "strong",
        ]
        for sel in price_selectors:
            for tag in soup.select(sel):
                text = tag.get_text()
                m = ton_pattern.search(text)
                if m:
                    val = float(m.group(1).replace(",", ""))
                    if val > 0:
                        valid_prices.append(val)

        # ── Strategy 3: look for JSON-LD or inline JSON with price data ──────
        for script in soup.find_all("script"):
            script_text = script.get_text()
            if "TON" in script_text or "price" in script_text.lower():
                m = ton_pattern.search(script_text)
                if m:
                    val = float(m.group(1).replace(",", ""))
                    if val > 0:
                        valid_prices.append(val)

        # ── Determine result ─────────────────────────────────────────────────
        page_lower = html.lower()

        # Signs a username is NOT on fragment (free/unclaimed)
        not_found_signals = [
            "username not found",
            "page not found",
            "doesn't exist",
            "no such username",
            "not available on fragment",
        ]
        is_not_found = any(sig in page_lower for sig in not_found_signals)

        # Signs the username IS listed on fragment
        fragment_signals = [
            "buy for",
            "place a bid",
            "current price",
            "minimum bid",
            "auction ends",
            "buy now",
        ]
        is_fragment_page = any(sig in page_lower for sig in fragment_signals)

        if valid_prices and (is_fragment_page or not is_not_found):
            # Pick the largest price (most likely the actual listing price)
            price = max(valid_prices)
            return price, "fragment"

        return None, "free"

    except httpx.TimeoutException:
        return None, "error_timeout"
    except Exception as e:
        return None, f"error_{str(e)[:30]}"


@app.get("/", tags=["Info"])
async def root():
    return {
        "api": "Fragment Username Checker",
        "version": "1.0.0",
        "usage": "/check?username=tobi",
        "example": "/check?username=@tobi",
        "developer": "@sagarkun0",
        "channel": "@foryoubysagar",
    }


@app.get("/check", tags=["Checker"])
async def check_username(
    username: str = Query(..., description="Telegram username (with or without @)")
):
    """
    Check if a Telegram username is listed on Fragment marketplace.
    Returns price in TON, USD, and INR if listed.
    """
    # Clean the username
    clean = username.lstrip("@").strip()

    if not clean:
        return JSONResponse(
            {"error": "Username cannot be empty"},
            status_code=400
        )

    if not re.match(r'^[a-zA-Z0-9_]{3,32}$', clean):
        return JSONResponse(
            {
                "error": "Invalid username. Must be 3–32 chars, alphanumeric + underscores.",
                "username": f"@{clean}"
            },
            status_code=400
        )

    # Fetch prices concurrently with scraping
    import asyncio
    price_task = asyncio.create_task(get_ton_prices())
    fragment_result = await scrape_fragment(clean)
    usd_rate, inr_rate = await price_task

    ton_price, state = fragment_result

    # Handle scrape errors
    if state.startswith("error"):
        return JSONResponse(
            {
                "username": f"@{clean}",
                "state": "unknown",
                "Price_TON": "N/A",
                "₹inr": "N/A",
                "$usd": "N/A",
                "fragment_status": "Error",
                "message": f"Could not reach Fragment.com — try again later ⚠️",
                "developer": "@sagarkun0"
            },
            status_code=503
        )

    if state == "fragment" and ton_price is not None:
        # Calculate fiat equivalents
        usd_val = round(ton_price * (usd_rate or 5.0), 1)
        inr_val = round(ton_price * (inr_rate or 415.0), 1)

        # Format numbers with commas
        ton_fmt = f"{int(ton_price):,}" if ton_price == int(ton_price) else f"{ton_price:,.2f}"
        usd_fmt = f"$ {usd_val:,.1f}"
        inr_fmt = f"₹ {inr_val:,.1f}"

        return JSONResponse({
            "username": f"@{clean}",
            "state": "fragment",
            "Price_TON": ton_fmt,
            "₹inr": inr_fmt,
            "$usd": usd_fmt,
            "fragment_status": "Available",
            "message": "Username on Fragment 👀",
            "developer": "@sagarkun0"
        })

    else:
        return JSONResponse({
            "username": f"@{clean}",
            "state": "free",
            "Price_TON": "Unknown",
            "₹inr": "N/A",
            "$usd": "N/A",
            "fragment_status": "Unavailable",
            "message": "Free to Claim ✅ or from Deleted acc. Try To claim it 🙏",
            "developer": "@sagarkun0"
        })
