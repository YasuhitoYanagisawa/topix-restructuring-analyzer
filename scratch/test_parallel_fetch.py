import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import topix_agent.tools.stock_data as sd
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf
import json
import time

def fetch_shares_outstanding_parallel(stocks: list) -> dict[str, int]:
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
            logger.debug(f"fast_info failed for {ticker}: {e}")
        return code, None

    start = time.time()
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {executor.submit(fetch_one, s): s for s in stocks}
        completed_count = 0
        for future in as_completed(futures):
            code, shares = future.result()
            if shares:
                results[code] = shares
            completed_count += 1
            if completed_count % 10 == 0:
                logger.info(f"Fetched: {completed_count}/{len(stocks)}")
    
    logger.info(f"Completed in {time.time() - start:.2f} seconds. Found: {len(results)}/{len(stocks)}")
    return results

def main():
    test_codes = ["5253", "135A", "141A", "147A", "186A", "215A", "2160", "247A", "278A", "290A", "485A", "4816", "7203"]
    stocks = [{"code": c} for c in test_codes]
    res = fetch_shares_outstanding_parallel(stocks)
    print("Results:", json.dumps(res, indent=2))

if __name__ == "__main__":
    main()
