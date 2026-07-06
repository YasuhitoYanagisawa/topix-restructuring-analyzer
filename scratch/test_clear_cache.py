import os
import sys

# Add root directory to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from topix_agent.tools.stock_data import check_and_update_cache_if_needed, load_local_cache

def main():
    cache_path = "topix_agent/tools/topix_stock_cache.json"
    
    # 1. Clear the cache file
    if os.path.exists(cache_path):
        print(f"Deleting cache file at {cache_path}...")
        os.remove(cache_path)
    else:
        print("Cache file does not exist. Good to go.")
        
    # 2. Trigger check_and_update_cache_if_needed
    print("Triggering check_and_update_cache_if_needed(). This will rebuild the cache...")
    check_and_update_cache_if_needed()
    
    # 3. Verify rebuilding was successful
    if os.path.exists(cache_path):
        print("Cache file successfully rebuilt!")
        cache = load_local_cache()
        print(f"Total stocks in new cache: {len(cache)}")
        
        # Verify cover (5253), McDonald's (2702), PowerX (485A), Nakanishi (7716)
        test_codes = ["5253", "2702", "485A", "7716", "7014"]
        print("\nVerifying key candidate entries in the rebuilt cache:")
        for code in test_codes:
            if code in cache:
                item = cache[code]
                float_ratio = item.get("float_ratio", 0.0)
                float_mc = item.get("market_cap", 0) * float_ratio
                print(f"Code: {code} ({item['company_name']}), FFW: {float_ratio}, Float MC: {float_mc:,.0f} JPY, MC: {item['market_cap']:,} JPY, Price: {item['price']} JPY, Volume: {item['annual_volume']:,}, Sector: {item['industry_33']}")
            else:
                print(f"ERROR: Code {code} is missing from the rebuilt cache!")
    else:
        print("ERROR: Cache file was NOT rebuilt!")

if __name__ == "__main__":
    main()
