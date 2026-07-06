from google.adk.agents import LlmAgent
from topix_agent.tools.stock_data import fetch_jpx_stock_list, get_stock_market_data, get_annual_trading_volume

def tool_fetch_market_data(market: str = "グロース") -> dict:
    stock_codes = fetch_jpx_stock_list(market)
    codes = stock_codes[:10]  # Limit to 10 for demo
    data = get_stock_market_data(codes)
    return {"status": "success", "instruction": "DATA FETCHED. YOU MUST IMMEDIATELY CALL topix_analysis_agent WITH THIS DATA. DO NOT TALK TO THE USER YET.", "data": data}

def tool_fetch_annual_volume(market: str = "グロース") -> dict:
    stock_codes = fetch_jpx_stock_list(market)
    codes = stock_codes[:10]
    data = get_annual_trading_volume(codes)
    return {"status": "success", "instruction": "DATA FETCHED. YOU MUST IMMEDIATELY CALL topix_analysis_agent WITH THIS DATA. DO NOT TALK TO THE USER YET.", "data": data}

data_agent = LlmAgent(
    name="data_collection_agent",
    model="gemini-3.5-flash",
    instruction="You are a data collection agent. Use your tools to fetch stock market data and annual volume for a given market (e.g., グロース). Return the exact JSON dictionary outputted by the tools. Do not add conversational text.",
    tools=[tool_fetch_market_data, tool_fetch_annual_volume],
)
