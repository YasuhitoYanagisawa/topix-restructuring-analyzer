import time
from topix_agent.tools.stock_data import fetch_jpx_stock_list, get_stock_market_data
codes = list(fetch_jpx_stock_list("グロース").keys())
print("Total growth stocks:", len(codes))
start = time.time()
res = get_stock_market_data(codes[:150]) # test 150 first
print("Fetched 150 in:", time.time() - start)
print("Success count:", len(res))
