import yfinance as yf
import pandas as pd
import time
import requests
import os
import sys

# Load JPX stocks
print("Fetching JPX list...")
url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
df = pd.read_excel(url)
df_sg = df[df["市場・商品区分"].str.contains("スタンダード|グロース", na=False)]
codes = df_sg["コード"].astype(str).tolist()
names = df_sg["銘柄名"].astype(str).tolist()
ticker_to_name = dict(zip(codes, names))

print(f"Total Standard & Growth stocks: {len(codes)}")

# Let's test downloading a batch of 50 tickers to see if we can calculate the annual trading value
test_codes = codes[:50]
tickers = [f"{c}.T" for c in test_codes]

print("Downloading history for 50 tickers...")
try:
    # We download 1 year history of Close and Volume
    data = yf.download(tickers, period="1y", interval="1d", progress=False, group_by="ticker")
    print("Download completed. Processing...")
    
    valid_candidates = []
    for code in test_codes:
        ticker = f"{code}.T"
        if ticker in data:
            df_ticker = data[ticker]
            # Calculate annual trading value: sum of (Volume * Close)
            if "Volume" in df_ticker and "Close" in df_ticker:
                # drop nan
                df_ticker = df_ticker.dropna(subset=["Volume", "Close"])
                trading_value = (df_ticker["Volume"] * df_ticker["Close"]).sum()
                print(f"Code: {code} ({ticker_to_name[code]}), Trading Value: {trading_value:,.0f} JPY")
                if trading_value >= 7000000000:
                    valid_candidates.append(code)
                    
    print("Candidates with Trading Value >= 70億:", valid_candidates)
except Exception as e:
    print("Error:", e)
