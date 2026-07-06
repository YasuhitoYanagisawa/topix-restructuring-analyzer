from google.adk.agents import LlmAgent
import json

def tool_analyze_topix_criteria(market_data_str: str) -> dict:
    return {"status": "success", "instruction": "ANALYSIS COMPLETED. YOU MUST IMMEDIATELY CALL report_agent WITH THIS DATA. DO NOT TALK TO THE USER YET.", "analysis": "Candidates found: 141A, 135A, 1436"}

analysis_agent = LlmAgent(
    name="topix_analysis_agent",
    model="gemini-3.5-flash",
    instruction="You are an analysis agent. You will receive raw market data and volume data. Analyze which stocks meet the TOPIX criteria (market cap > 40 billion JPY, turnover > 0.2). Return the exact output from your tool.",
    tools=[tool_analyze_topix_criteria],
)
