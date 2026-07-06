import logging
import pandas as pd
import yfinance as yf
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import urllib.request
import json
import re
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

UPDATE_IN_PROGRESS = False

# --- Patch curl_cffi for yfinance SSL issue on Windows ---
try:
    import curl_cffi.requests
    orig_request = curl_cffi.requests.Session.request
    def patched_request(self, method, url, **kwargs):
        kwargs["verify"] = False
        return orig_request(self, method, url, **kwargs)
    curl_cffi.requests.Session.request = patched_request
except ImportError:
    pass
# ---------------------------------------------------------

def fetch_jpx_stock_list(market: str = "Growth") -> dict[str, str]:
    url = "https://www.jpx.co.jp/english/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_e.xls"
    try:
        df = pd.read_excel(url)
        m_query = "Growth" if market in ["グロース", "Growth"] else "Standard"
        if market:
            df = df[df["Section/Products"].str.contains(m_query, na=False)]
        codes = df["Local Code"].astype(str).tolist()
        names = df["Name (English)"].astype(str).tolist()
        return dict(zip(codes, names))
    except Exception as e:
        logger.error(f"Error fetching JPX data: {e}")
        return {"7203": "トヨタ自動車", "9984": "ソフトバンクグループ"}

def fetch_jpx_float_ratios() -> dict[str, float]:
    """
    Scrapes the JPX revisions page, finds the link to the official Float Factor Weight (FFW) CSV file,
    downloads it, and parses the float ratio for each stock code.
    """
    logger.info("Scraping JPX revisions page for float ratios (FFW)...")
    url = "https://www.jpx.co.jp/markets/indices/revisions-indices/"
    headers = {"User-Agent": "Mozilla/5.0"}
    ratios = {}
    try:
        # 1. Scrape the page to find the FFW CSV link
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            html = response.read().decode("utf-8", errors="ignore")
        
        soup = BeautifulSoup(html, "html.parser")
        csv_url = None
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "ffw" in href.lower() and href.endswith(".csv"):
                if href.startswith("/"):
                    csv_url = "https://www.jpx.co.jp" + href
                else:
                    csv_url = href
                break
        
        if not csv_url:
            # Try a broader regex search as fallback
            match = re.search(r'href="([^"]*ffw[^"]*\.csv)"', html, re.IGNORECASE)
            if match:
                href = match.group(1)
                if href.startswith("/"):
                    csv_url = "https://www.jpx.co.jp" + href
                else:
                    csv_url = href
        
        if csv_url:
            logger.info(f"Downloading JPX official float ratios from: {csv_url}")
            csv_req = urllib.request.Request(csv_url, headers=headers)
            with urllib.request.urlopen(csv_req) as csv_resp:
                csv_data = csv_resp.read().decode("shift_jis", errors="ignore")
            
            # Parse FFW CSV: Code is column 4, FFW is column 5
            # Header format: Date,Issues(Japanese),Issues(English),Code,FFW
            lines = csv_data.splitlines()
            for line in lines:
                parts = line.strip().split(",")
                if len(parts) >= 5:
                    code_str = parts[3].strip()
                    ffw_str = parts[4].strip()
                    if code_str.isdigit() and len(code_str) == 4:
                        try:
                            ratios[code_str] = float(ffw_str)
                        except ValueError:
                            pass
            logger.info(f"Successfully loaded {len(ratios)} float ratios from JPX CSV.")
        else:
            logger.warning("Could not find JPX official float ratio CSV link on the revisions page.")
    except Exception as e:
        logger.error(f"Error fetching JPX float ratios: {e}")
    return ratios

import os
import json

GROWTH_OVERRIDES = {}

STANDARD_OVERRIDES = {}

def load_local_cache() -> dict:
    cache_path = os.path.join(os.path.dirname(__file__), "topix_stock_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading cache file: {e}")
    return {}

def _fetch_single_stock_info(ticker: str):
    t = yf.Ticker(ticker)
    info = t.info
    fast_info = t.fast_info
    full_mc = info.get("marketCap", fast_info.get("market_cap", 0))
    float_shares = info.get("floatShares")
    shares_outstanding = info.get("sharesOutstanding", fast_info.get("shares", 0))
    
    if float_shares and shares_outstanding:
        float_ratio = float_shares / shares_outstanding
    else:
        float_ratio = 0.70
        
    float_mc = int(full_mc * float_ratio)
    return {
        "market_cap": float_mc,  # Float-adjusted Market Cap (流通時価総額)
        "full_market_cap": full_mc,
        "shares_outstanding": shares_outstanding,
        "price": info.get("currentPrice", fast_info.get("last_price", 0)),
        "float_shares": float_shares or (shares_outstanding * float_ratio)
    }

def get_stock_market_data(codes: list[str]) -> dict:
    results = {}
    cache = load_local_cache()
    
    # If scanning many stocks, use cache directly to avoid rate limits
    if len(codes) > 10:
        logger.info(f"Requested market data for {len(codes)} stocks. Using cache to bypass rate-limiting.")
        for code in codes:
            if code in cache:
                cached = cache[code]
                full_mc = cached.get("market_cap", 0)
                float_ratio = cached.get("float_ratio", 0.50 if cached.get("market") == "グロース" else 0.70)
                float_mc = int(full_mc * float_ratio)
                results[code] = {
                    "market_cap": float_mc,  # Float-adjusted Market Cap (流通時価総額)
                    "full_market_cap": full_mc,
                    "shares_outstanding": full_mc / cached.get("price", 1) if cached.get("price", 1) > 0 else 0,
                    "price": cached.get("price", 0),
                    "float_shares": float_mc / cached.get("price", 1) if cached.get("price", 1) > 0 else 0
                }
        return results

    with ThreadPoolExecutor(max_workers=min(len(codes), 20)) as executor:
        future_to_code = {executor.submit(_fetch_single_stock_info, f"{code}.T"): code for code in codes}
        for future in as_completed(future_to_code):
            code = future_to_code[future]
            try:
                results[code] = future.result()
            except Exception as e:
                logger.warning(f"yfinance failed for {code}: {e}. Falling back to cache.")
                if code in cache:
                    cached = cache[code]
                    full_mc = cached.get("market_cap", 0)
                    float_ratio = cached.get("float_ratio", 0.50 if cached.get("market") == "グロース" else 0.70)
                    float_mc = int(full_mc * float_ratio)
                    results[code] = {
                        "market_cap": float_mc,  # Float-adjusted Market Cap (流通時価総額)
                        "full_market_cap": full_mc,
                        "shares_outstanding": full_mc / cached.get("price", 1) if cached.get("price", 1) > 0 else 0,
                        "price": cached.get("price", 0),
                        "float_shares": float_mc / cached.get("price", 1) if cached.get("price", 1) > 0 else 0
                    }
    return results

def get_annual_trading_volume(codes: list[str]) -> dict:
    results = {}
    cache = load_local_cache()
    
    # If scanning many stocks, use cache directly to avoid rate limits
    if len(codes) > 10:
        logger.info(f"Requested trading volume for {len(codes)} stocks. Using cache to bypass rate-limiting.")
        for code in codes:
            if code in cache:
                cached = cache[code]
                results[code] = {
                    "annual_volume": cached.get("annual_volume", 0),
                    "annual_turnover_value": cached.get("annual_turnover_value", 0)
                }
        return results

    tickers = [f"{code}.T" for code in codes]
    try:
        data = yf.download(tickers, period="1y", group_by="ticker", progress=False, threads=True)
        for ticker in tickers:
            code = ticker.replace(".T", "")
            df = data if len(tickers) == 1 else data[ticker]
            annual_volume = df["Volume"].sum() if "Volume" in df else 0
            results[code] = {
                "annual_volume": int(annual_volume),
                "annual_turnover_value": int(annual_volume * df["Close"].mean() if "Close" in df else 0)
            }
    except Exception as e:
        logger.warning(f"Error fetching volume for {codes}: {e}. Falling back to cache.")
        for code in codes:
            if code in cache:
                cached = cache[code]
                results[code] = {
                    "annual_volume": cached.get("annual_volume", 0),
                    "annual_turnover_value": cached.get("annual_turnover_value", 0)
                }
    return results

def save_local_cache(cache: dict):
    cache_path = os.path.join(os.path.dirname(__file__), "topix_stock_cache.json")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        logger.info(f"Successfully saved cache with {len(cache)} stocks.")
    except Exception as e:
        logger.error(f"Error writing cache file: {e}")

def fetch_ticker_data_direct(ticker: str) -> dict | None:
    """Fetch 5-day chart data directly from Yahoo Finance query API as a fallback when yfinance fails."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            data = json.loads(res.read())
            result = data['chart']['result'][0]
            meta = result['meta']
            quote = result['indicators']['quote'][0]
            
            # Extract closes and volumes
            closes = [c for c in quote.get('close', []) if c is not None]
            volumes = [v for v in quote.get('volume', []) if v is not None]
            
            if not closes:
                return None
                
            price = meta.get('regularMarketPrice') or closes[-1]
            
            return {
                "Close": pd.Series(closes),
                "Volume": pd.Series(volumes) if volumes else pd.Series([0]*len(closes)),
                "price": price
            }
    except Exception as e:
        logger.error(f"Direct fallback query failed for {ticker}: {e}")
    return None

def fetch_shares_outstanding_parallel(stocks: list) -> dict[str, int]:
    """Fetch shares outstanding for all stocks in parallel using ThreadPoolExecutor."""
    results = {}
    logger.info(f"Fetching shares outstanding for {len(stocks)} stocks in parallel...")
    
    def fetch_one(stock):
        code = stock["code"]
        ticker = f"{code}.T"
        try:
            t = yf.Ticker(ticker)
            shares = t.fast_info.get("shares")
            if shares and shares > 0:
                return code, int(shares)
        except Exception as e:
            logger.debug(f"Failed to fetch shares for {ticker}: {e}")
        return code, None

    # Use ThreadPoolExecutor with 30 workers
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(fetch_one, s): s for s in stocks}
        completed_count = 0
        for future in as_completed(futures):
            code, shares = future.result()
            if shares:
                results[code] = shares
            completed_count += 1
            if completed_count % 300 == 0:
                logger.info(f"Fetched shares outstanding: {completed_count}/{len(stocks)}")
                
    logger.info(f"Parallel shares outstanding fetch complete. Found {len(results)}/{len(stocks)} stocks.")
    return results

def update_cache_autonomously():
    """Autonomously fetch the JPX stock list and update the cache with latest Yahoo Finance data.
    Uses batched yf.download to update prices and volumes without triggering rate limits.
    """
    global UPDATE_IN_PROGRESS
    UPDATE_IN_PROGRESS = True
    logger.info("Starting autonomous cache update...")
    try:
        # Fetch official FFW float ratios from JPX revisions page
        float_ratios = fetch_jpx_float_ratios()
        
        url = "https://www.jpx.co.jp/english/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_e.xls"
        try:
            df = pd.read_excel(url)
        except Exception as e:
            logger.error(f"Failed to fetch JPX English Excel list during update: {e}")
            return
            
        df_growth = df[df["Section/Products"].str.contains("Growth", na=False)]
        df_standard = df[df["Section/Products"].str.contains("Standard", na=False)]
        
        cache = load_local_cache()
        
        # Process all growth and standard stocks
        all_stocks = []
        for market_name, df_market in [("Growth", df_growth), ("Standard", df_standard)]:
            for _, row in df_market.iterrows():
                all_stocks.append({
                    "code": str(row["Local Code"]),
                    "name": str(row["Name (English)"]),
                    "market": market_name,
                    "size_class": str(row["Size (New Index Series)"]).strip(),
                    "industry_33": str(row["33 Sector(name)"]).strip(),
                    "industry_17": str(row["17 Sector(name)"]).strip()
                })
                
        logger.info(f"Total stocks to update: {len(all_stocks)}")
        
        # Fetch shares outstanding in parallel
        shares_dict = fetch_shares_outstanding_parallel(all_stocks)
        
        # Update cache in batches of 100 tickers using yf.download to get latest price and volume
        batch_size = 100
        for i in range(0, len(all_stocks), batch_size):
            batch = all_stocks[i:i+batch_size]
            tickers = [f"{s['code']}.T" for s in batch]
            
            logger.info(f"Updating batch {i//batch_size + 1}/{(len(all_stocks)-1)//batch_size + 1}...")
            try:
                # Download recent data (5 days is fast and has volume + close price)
                data = yf.download(tickers, period="5d", progress=False, group_by="ticker")
                
                for stock in batch:
                    code = stock["code"]
                    ticker = f"{code}.T"
                    
                    # Determine shares outstanding
                    shares = shares_dict.get(code)
                    if not shares and code in cache:
                        # Fallback to existing cache shares outstanding
                        old_entry = cache[code]
                        shares = old_entry.get("market_cap", 0) / old_entry.get("price", 1) if old_entry.get("price", 0) > 0 else 0
                        
                    if not shares:
                        # Last resort: estimate from size class
                        size_class = stock["size_class"]
                        if "TOPIX Core30" in size_class or "TOPIX Large70" in size_class:
                            shares = 500_000_000
                        elif "TOPIX Mid400" in size_class:
                            shares = 100_000_000
                        elif "TOPIX Small 1" in size_class:
                            shares = 25_000_000
                        elif "TOPIX Small 2" in size_class:
                            shares = 10_000_000
                        else:
                            shares = 5_000_000

                    default_entry = {
                        "company_name": stock["name"],
                        "price": 1000.0,
                        "market_cap": int(shares * 1000.0),
                        "annual_volume": 5_000_000,
                        "annual_turnover_value": 5_000_000_000,
                        "market": stock["market"],
                        "industry_33": stock["industry_33"],
                        "industry_17": stock["industry_17"]
                    }
                    
                    cached = cache.get(code, default_entry)
                    
                    df_ticker = data.get(ticker) if ticker in data else None
                    is_valid = df_ticker is not None and "Close" in df_ticker and len(df_ticker.dropna()) > 0
                    
                    if not is_valid:
                        logger.info(f"yfinance failed or returned empty for {ticker}. Trying direct API fallback...")
                        fallback_data = fetch_ticker_data_direct(ticker)
                        if fallback_data:
                            df_ticker = fallback_data
                            is_valid = True
                            
                    if is_valid and df_ticker is not None:
                        if "Close" in df_ticker and len(df_ticker) > 0:
                            last_price = df_ticker["Close"].dropna().iloc[-1] if not df_ticker["Close"].dropna().empty else cached["price"]
                            cached["price"] = float(last_price)
                            # Calculate market cap dynamically based on real shares and real price!
                            cached["market_cap"] = int(shares * cached["price"])
                            
                        # Calculate or estimate annual trading volume from the last 5 days
                        # (Scale 5-day volume to 250 trading days as an approximation of current run rate)
                        if "Volume" in df_ticker and len(df_ticker) > 0:
                            recent_volume = df_ticker["Volume"].dropna().sum()
                            estimated_annual_volume = int(recent_volume * 50) # 5 days * 50 = 250 days
                            if estimated_annual_volume > 0:
                                cached["annual_volume"] = estimated_annual_volume
                                cached["annual_turnover_value"] = int(estimated_annual_volume * cached["price"])
                                
                    # Assign official float ratio from JPX CSV if available
                    if code in float_ratios:
                        cached["float_ratio"] = float_ratios[code]
                    elif "float_ratio" not in cached:
                        # Fallback default float ratio based on market
                        cached["float_ratio"] = 0.50 if stock["market"] in ["グロース", "Growth"] else 0.70
                        
                    cache[code] = cached
            except Exception as e:
                logger.error(f"Error updating batch {tickers}: {e}")
                
            # Sleep for 1 second between batches to respect rate limits
            time.sleep(1.0)
            
        save_local_cache(cache)
        logger.info("Autonomous cache update completed successfully.")
    finally:
        UPDATE_IN_PROGRESS = False

def check_and_update_cache_if_needed():
    global UPDATE_IN_PROGRESS
    cache_path = os.path.join(os.path.dirname(__file__), "topix_stock_cache.json")
    if not os.path.exists(cache_path) or (time.time() - os.path.getmtime(cache_path)) > 86400:
        if not UPDATE_IN_PROGRESS:
            logger.info("Cache is missing or outdated (>24h). Triggering autonomous background update...")
            try:
                update_cache_autonomously()
            except Exception as e:
                logger.error(f"Failed to autonomously update cache: {e}")
                UPDATE_IN_PROGRESS = False


