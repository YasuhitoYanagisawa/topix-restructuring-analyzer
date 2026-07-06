import logging
import json
from google.genai import Client
import os
import asyncio
import threading
from topix_agent.tools.stock_data import fetch_jpx_stock_list, get_stock_market_data, get_annual_trading_volume

logger = logging.getLogger(__name__)

class PipelineAgent:
    def __init__(self):
        self.client = Client(api_key=os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))
        self.model = "gemini-3.1-flash-lite"
        
    async def generate_response(self, message: str, session_id: str):
        # 1. Classify intent: Is it RUN_GROWTH, RUN_STANDARD, RUN_ALL, or CHAT_QUESTION?
        intent_prompt = f"""Analyze the user message and classify their intent into one of the following categories:
- RUN_GROWTH: The user explicitly wants to run the TOPIX candidate screening or analysis only for the Growth (グロース) market. (e.g. "グロース市場の分析", "グロース市場のみ")
- RUN_STANDARD: The user explicitly wants to run the TOPIX candidate screening or analysis only for the Standard (スタンダード) market. (e.g. "スタンダード市場の分析", "スタンダード市場のみ")
- RUN_ALL: The user wants to run the TOPIX candidate screening or analysis for all markets (both Growth and Standard), or the user gave a general analysis command without specifying a market (e.g. "分析開始", "TOPIX採用候補の銘柄を分析して、リストアップしてください。").
- CHAT_QUESTION: The user is asking a specific question, like searching for sectors, asking about entertainment stocks, asking about rules, or discussing specific stocks. (e.g. "エンタメ銘柄で何かありますか？", "カバーは入ってる？", "TOPIXの基準について教えて")

User Message: "{message}"

Respond with ONLY the category name (RUN_GROWTH, RUN_STANDARD, RUN_ALL, or CHAT_QUESTION) without any other text."""
        
        try:
            classification = self.client.models.generate_content(
                model=self.model,
                contents=intent_prompt
            ).text.strip()
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            classification = "RUN_ALL" # Fallback
            
        logger.info(f"User Message: {message} -> Classified Intent: {classification}")
        
        if "CHAT_QUESTION" in classification:
            # Answer user's question using current cache database candidates
            yield "data: {\"type\": \"status\", \"content\": \"回答を準備中...\"}\n\n"
            
            try:
                from topix_agent.tools.stock_data import load_local_cache
                cache = load_local_cache()
                if not cache:
                    yield "data: {\"type\": \"status\", \"content\": \"データベースを初期化中です（約60秒〜90秒）...\"}\n\n"
                    msg = "**[System]** データベースファイルが見つかりません。初回起動時の自動構築処理を開始します（約60秒〜90秒）。完了するまでこのままお待ちください...\n\n"
                    yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"
                    
                    import topix_agent.tools.stock_data as sd
                    if not getattr(sd, "UPDATE_IN_PROGRESS", False):
                        threading.Thread(target=sd.check_and_update_cache_if_needed, daemon=True).start()
                        
                    while True:
                        await asyncio.sleep(2.0)
                        cache = load_local_cache()
                        if cache and len(cache) >= 2000:
                            break
                        yield "data: {\"type\": \"status\", \"content\": \"データベース再構築中...\"}\n\n"
                    msg = "**[System]** データベースの構築が完了しました！回答を準備します。\n\n---\n\n"
                    yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"

                # Retrieve all standard and growth stocks from cache
                jpx_growth = fetch_jpx_stock_list("グロース")
                jpx_standard = fetch_jpx_stock_list("スタンダード")
                stock_codes_dict = {}
                stock_codes_dict.update(jpx_growth)
                stock_codes_dict.update(jpx_standard)
                
                codes = list(stock_codes_dict.keys())
                market_data = get_stock_market_data(codes)
                volume_data = get_annual_trading_volume(codes)
                
                candidates = []
                for code in market_data:
                    m_info = market_data[code]
                    v_info = volume_data.get(code, {})
                    market_cap = m_info.get("market_cap", 0)
                    annual_turnover = v_info.get("annual_turnover_value", 0)
                    turnover_ratio = annual_turnover / market_cap if market_cap > 0 else 0
                    
                    if market_cap >= 35000000000 and turnover_ratio >= 0.15:
                        candidates.append({
                            "code": code,
                            "company_name": stock_codes_dict.get(code, "Unknown"),
                            "price": m_info.get("price", 0),
                            "market_cap": market_cap,
                            "annual_volume": v_info.get("annual_volume", 0),
                            "turnover_ratio": round(turnover_ratio, 4),
                            "industry_33": m_info.get("industry_33", "-"),
                            "industry_17": m_info.get("industry_17", "-"),
                            "market": "グロース" if code in jpx_growth else "スタンダード"
                        })
                
                # Ask Gemini to map the question to JPX industries
                industry_mapping_prompt = f"""You are a JPX Industry Mapper.
User Question: "{message}"

JPX 33 Industries:
['水産・農林業', '鉱業', '建設業', '食料品', '繊維製品', 'パルプ・紙', '化学', '医薬品', '石油・石炭製品', 'ゴム製品', 'ガラス・土石製品', '鉄鋼', '非鉄金属', '金属製品', '機械', '電気機器', '輸送用機器', '精密機器', 'その他製品', '電気・ガス業', '陸運業', '海運業', '空運業', '倉庫・運輸関連業', '情報・通信業', '卸売業', '小売業', '銀行業', '証券、商品先物取引業', '保険業', 'その他金融業', '不動産業', 'サービス業']

JPX 17 Industries:
['食品', 'エネルギー資源', '建設・資材', '素材・化学', '医薬品', '機械', '電機・精密', '情報通信・サービス他', '自動車・輸送機', '鉄鋼・非鉄', '小売', '銀行', '金融（除く銀行）', '不動産', '運輸・物流', '電力・ガス', '商業']

Identify which of these industries are relevant to the user's question. For example, if the user asks about "資源" or "エネルギー", relevant industries might be "鉱業", "石油・石炭製品", "エネルギー資源", "鉄鋼・非鉄" etc. If they ask about "魚" or "水産", relevant industries might be "水産・農林業", "食品", "小売業" etc.
Return a JSON array of the matching industry names from the lists above. If none match, return [].
Return ONLY the JSON array (e.g. ["鉱業", "エネルギー資源"]). Do NOT wrap in markdown blocks."""

                try:
                    industries_text = self.client.models.generate_content(
                        model=self.model,
                        contents=industry_mapping_prompt
                    ).text.strip()
                    if "```" in industries_text:
                        industries_text = industries_text.split("```")[1].replace("json", "").strip()
                    matched_industries = json.loads(industries_text)
                except Exception as e:
                    logger.error(f"Failed to map industries: {e}")
                    matched_industries = []
                    
                # Scan all 2161 stocks in the database to find matches for the mapped industries
                sector_stocks = []
                if matched_industries:
                    for code in market_data:
                        m_info = market_data[code]
                        v_info = volume_data.get(code, {})
                        ind33 = m_info.get("industry_33", "-")
                        ind17 = m_info.get("industry_17", "-")
                        
                        if any(ind in [ind33, ind17] for ind in matched_industries):
                            market_cap = m_info.get("market_cap", 0)
                            turnover_ratio = v_info.get("annual_turnover_value", 0) / market_cap if market_cap > 0 else 0
                            sector_stocks.append({
                                "code": code,
                                "company_name": stock_codes_dict.get(code, "Unknown"),
                                "price": m_info.get("price", 0),
                                "market_cap": market_cap,
                                "annual_volume": v_info.get("annual_volume", 0),
                                "turnover_ratio": round(turnover_ratio, 4),
                                "industry_33": ind33,
                                "industry_17": ind17,
                                "market": "Growth" if code in jpx_growth else "Standard"
                            })
                    # Sort sector stocks by market cap descending and limit to top 30
                    sector_stocks = sorted(sector_stocks, key=lambda x: x["market_cap"], reverse=True)[:30]
                    
                chat_prompt = f"""You are the TOPIX Restructuring Analyzer Agent.
Answer the user's question about TOPIX restructuring candidates.

User Question: "{message}"

Matched Industry Classifications: {matched_industries}

All Stocks in these Industries (Standard & Growth markets, sorted by float-adjusted market cap):
{json.dumps(sector_stocks, ensure_ascii=False)}

Current Overall Screened Candidates (Growth & Standard - meeting the TOPIX 35B+ float-adjusted threshold):
{json.dumps(candidates, ensure_ascii=False)}

TOPIX New Criteria (from Oct 2026):
- Targets: All markets (Prime, Standard, Growth)
- New Inclusion Criteria:
  1. Annual turnover ratio >= 0.2
  2. Float market cap in top 96% cumulative (typically around 40 billion JPY or more).

CRITICAL TERMINOLOGY RULES:
1. The `market_cap` field in the provided data is the calculated **流通時価総額 (Float-adjusted Market Cap)**, NOT the full market capitalization (全体時価総額).
2. When mentioning these values, you MUST strictly refer to them as **「Float-adjusted Market Cap」** (or Flow Market Cap) in English, and clarify that they are float-adjusted (e.g. "Float-adjusted Market Cap of approx 41.4 Billion JPY (Full Market Cap is 103.5 Billion JPY)" or similar).

Answer the question clearly in English.
- If the user asks about a specific sector or topic (e.g. resources, entertainment, etc.), find and list the companies in that sector from the "All Stocks in these Industries" list above. State their current price, annual volume, **Float-adjusted Market Cap**, and turnover ratio, and explain whether they meet or are close to meeting the TOPIX criteria.
- If none of the companies in that sector meet the criteria, state that clearly and list the largest ones as reference.
- Explain that you scanned all 2,161 Growth & Standard stocks dynamically to find these.
- If the user asks about why there are no borderline candidates in Growth, explain that there is a natural gap in the Growth market between 34B JPY and 41B JPY (e.g. Cover 5253 is at 41.4B JPY and GENDA 9166 is at 42.4B JPY, while the next largest ones are below 34B JPY), meaning all Growth stocks that meet the 35B JPY baseline also happen to meet the strict 40B JPY criteria.
- Always include a standard investment disclaimer in English at the end of your response."""
                
                response_stream = self.client.models.generate_content_stream(
                    model=self.model,
                    contents=chat_prompt
                )
                for chunk in response_stream:
                    if chunk.text:
                        yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(chunk.text)}}}\n\n"
                        await asyncio.sleep(0.01)
                yield "data: {\"type\": \"done\", \"content\": \"\"}\n\n"
            except Exception as e:
                logger.error(f"Chat question answering failed: {e}")
                yield f"data: {{\"type\": \"message\", \"content\": \"申し訳ありません。回答の生成中にエラーが発生しました。\"}}\n\n"
            return

        # ----------------------------------------------------
        # Standard Scan / Run Analysis Intent
        # ----------------------------------------------------
        markets_to_scan = []
        if "RUN_GROWTH" in classification:
            markets_to_scan = ["Growth"]
        elif "RUN_STANDARD" in classification:
            markets_to_scan = ["Standard"]
        else:
            markets_to_scan = ["Growth", "Standard"]
            
        markets_str = " & ".join(markets_to_scan)
            
        # 1. Data Collection
        yield "data: {\"type\": \"status\", \"content\": \"Parsing Request...\"}\n\n"
        
        # Check if cache is empty. If it is, wait for the background initialization thread to write it.
        from topix_agent.tools.stock_data import load_local_cache
        cache = load_local_cache()
        if not cache:
            yield "data: {\"type\": \"status\", \"content\": \"Initializing Database Cache (approx. 60-90s)...\"}\n\n"
            msg = "**[System]** Database cache file not found. Rebuilding database (approx. 60-90s)... Please wait.\n\n"
            yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"
            
            import topix_agent.tools.stock_data as sd
            if not getattr(sd, "UPDATE_IN_PROGRESS", False):
                threading.Thread(target=sd.check_and_update_cache_if_needed, daemon=True).start()
                
            while True:
                await asyncio.sleep(2.0)
                cache = load_local_cache()
                if cache and len(cache) >= 2000:
                    break
                yield "data: {\"type\": \"status\", \"content\": \"Rebuilding Database Cache...\"}\n\n"
            msg = "**[System]** Database cache built successfully! Commencing screening analysis.\n\n---\n\n"
            yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"

        msg = f"**[System]** Request received. Setting target markets to \"{markets_str}\" and starting screening...\n\n---\n\n"
        yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"
        await asyncio.sleep(0.05)
        
        yield "data: {\"type\": \"status\", \"content\": \"Fetching Ticker List from JPX...\"}\n\n"
        msg = f"**[Data Agent]** Connecting to JPX database to query all tickers in {markets_str} markets...\n\n"
        yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"
        await asyncio.sleep(0.05)
        
        # Load codes from selected markets
        stock_codes_dict = {}
        jpx_growth = {}
        jpx_standard = {}
        if "Growth" in markets_to_scan:
            jpx_growth = fetch_jpx_stock_list("グロース")
            stock_codes_dict.update(jpx_growth)
        if "Standard" in markets_to_scan:
            jpx_standard = fetch_jpx_stock_list("スタンダード")
            stock_codes_dict.update(jpx_standard)
            
        codes = list(stock_codes_dict.keys())
        
        msg = f"**[Data Agent]** Query complete. Extracted a total of {len(codes)} target tickers for {markets_str}.\n\n"
        yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"
        await asyncio.sleep(0.05)
        
        yield f"data: {{\"type\": \"status\", \"content\": \"Loading Market Data (Target: {len(codes)} tickers)...\"}}\n\n"
        msg = f"**[Data Agent]** Querying high-performance cache and Yahoo Finance APIs to load prices, market caps, and volumes...\n\n"
        yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"
        await asyncio.sleep(0.05)
        
        market_data = get_stock_market_data(codes)
        volume_data = get_annual_trading_volume(codes)
        
        # Merge data
        cleaned_data = {}
        for code in market_data:
            m_info = market_data[code]
            v_info = volume_data.get(code, {})
            cleaned_data[code] = {
                "company_name": stock_codes_dict.get(code, "Unknown"),
                "price": m_info.get("price", 0),
                "market_cap": m_info.get("market_cap", 0),
                "annual_volume": v_info.get("annual_volume", 0),
                "annual_turnover_value": v_info.get("annual_turnover_value", 0),
                "market": "Growth" if code in jpx_growth else "Standard"
            }
            
        # Filter and categorize candidates
        eligible_candidates = {}
        borderline_candidates = {}
        
        for code, info in cleaned_data.items():
            market_cap = info["market_cap"]  # Float-adjusted Market Cap
            turnover_value = info["annual_turnover_value"]
            turnover_ratio = turnover_value / market_cap if market_cap > 0 else 0
            
            # Strict TOPIX criteria: Float MC >= 40B JPY AND Turnover >= 0.20
            if market_cap >= 40000000000 and turnover_ratio >= 0.20:
                info["turnover_ratio"] = round(turnover_ratio, 4)
                eligible_candidates[code] = info
            # Baseline/Borderline: Float MC >= 35B JPY AND Turnover >= 0.15
            elif market_cap >= 35000000000 and turnover_ratio >= 0.15:
                info["turnover_ratio"] = round(turnover_ratio, 4)
                borderline_candidates[code] = info

        # Sort matched candidates by float-adjusted market cap descending
        sorted_eligible = sorted(eligible_candidates.items(), key=lambda x: x[1]["market_cap"], reverse=True)
        sorted_borderline = sorted(borderline_candidates.items(), key=lambda x: x[1]["market_cap"], reverse=True)
        
        total_eligible_count = len(eligible_candidates)
        total_borderline_count = len(borderline_candidates)
        total_matched_count = total_eligible_count + total_borderline_count

        msg = f"**[Data Agent]** Data collection and screening complete for all {len(codes)} stocks.\n"
        msg += f"Detected **{total_eligible_count} eligible candidates** and **{total_borderline_count} borderline candidates**. Handing data over to Analysis Agent...\n\n---\n\n"
        yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"
        await asyncio.sleep(0.05)
        
        yield "data: {\"type\": \"status\", \"content\": \"Calculating Float-adjusted Market Cap...\"}\n\n"
        yield "data: {\"type\": \"status\", \"content\": \"Calculating Annual Turnover Ratio...\"}\n\n"
        
        # 2. Analysis
        yield "data: {\"type\": \"status\", \"content\": \"Screening Restructuring Candidates...\"}\n\n"
        msg = f"**[Analysis Agent]** Starting qualitative analysis on {total_eligible_count} eligible and {total_borderline_count} borderline candidates...\n\n"
        yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"
        await asyncio.sleep(0.05)
        
        analysis_prompt = f"""You are the topix_analysis_agent.
Analyze the following filtered stock candidates for TOPIX eligibility.
Criteria for strict eligibility: float_market_cap (流通時価総額) >= 40,000,000,000 and annual turnover > 0.2.
Borderline candidates are those meeting the baseline (float_market_cap >= 35B and turnover >= 0.15) but failing the strict criteria.

Strictly Eligible Candidates:
{json.dumps(dict(sorted_eligible), ensure_ascii=False)}

Borderline Candidates:
{json.dumps(dict(sorted_borderline), ensure_ascii=False)}

Output a concise summary in English of your analysis (do NOT output any raw JSON list or full stock tables):
1. Number of strictly eligible candidates vs borderline candidates.
2. Highlight a few key prominent candidates in both categories (e.g., Trial Holdings 141A, PowerX 485A, Cover 5253, Genda 9166, Nissan Shatai 7222, Kitagawa Seiki 6327, etc.) and explain why they fit or are borderline.
3. Summary of sector distribution.
Keep your response under 300 words."""

        analysis_result = ""
        response_stream = self.client.models.generate_content_stream(
            model=self.model,
            contents=analysis_prompt
        )
        for chunk in response_stream:
            if chunk.text:
                analysis_result += chunk.text
                yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(chunk.text)}}}\n\n"
                await asyncio.sleep(0.01)
                
        msg = f"\n\n**[Analysis Agent]** Qualitative analysis complete. Handing results over to Report Agent...\n\n---\n\n"
        yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"
        await asyncio.sleep(0.05)
        
        # 3. Report
        yield "data: {\"type\": \"status\", \"content\": \"Generating Final Markdown Report...\"}\n\n"
        yield "data: {\"type\": \"status\", \"content\": \"Generating Final Markdown Report...\"}\n\n"
        msg = f"**[Report Agent]** Analysis received. Formatting final investment report and structured tables...\n\n"
        yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(msg)}}}\n\n"
        await asyncio.sleep(0.05)
        
        report_prompt = f"""You are the report_agent.
Format the following analysis and candidates into a stunning, professional English Markdown report.
Do not output raw JSON. Use headings, bullet points, and bold text to highlight recommended stocks.

Eligible Candidates Data:
{json.dumps(dict(sorted_eligible), ensure_ascii=False)}

Borderline Candidates Data:
{json.dumps(dict(sorted_borderline), ensure_ascii=False)}

Analysis Summary:
{analysis_result}

CRITICAL:
1. State clearly under the main header:
   - Total number of **Eligible Candidates** (Strictly Eligible: Float MC >= 40B JPY and Annual Turnover >= 0.20) is {total_eligible_count}.
   - Total number of **Borderline Candidates** (Borderline: Float MC 35B-40B JPY, or Annual Turnover 0.15-0.20) is {total_borderline_count}.
2. You MUST generate TWO separate tables:
   - **Table 1: TOPIX Restructuring Eligible Candidates (Float Market Cap >= 40B JPY and Annual Turnover >= 0.20)**
     This table must contain ALL candidates from Eligible Candidates Data. Do not omit any!
   - **Table 2: Borderline Candidates (Float Market Cap 35B-40B JPY, or Annual Turnover 0.15-0.20)**
     This table must contain ALL candidates from Borderline Candidates Data. Do not omit any! If there are no borderline candidates, write "None".
3. Both tables MUST contain columns named EXACTLY:
   - Ticker
   - Company Name
   - Market ("Growth" or "Standard")
   - Current Price
   - Annual Volume
   - Float Market Cap
   - Annual Turnover Ratio
4. Below the tables, provide a professional summary of the findings based on the Analysis Summary.
5. Also mention: "Note: This analysis screens all listed tickers in the target markets (596 Growth / 1,565 Standard). To bypass Yahoo Finance rate limits, a high-performance cached database is used."

Analysis:
{analysis_result}"""
        
        response_stream = self.client.models.generate_content_stream(
            model=self.model,
            contents=report_prompt
        )
        for chunk in response_stream:
            if chunk.text:
                yield f"data: {{\"type\": \"message\", \"content\": {json.dumps(chunk.text)}}}\n\n"
                await asyncio.sleep(0.01)
        yield "data: {\"type\": \"done\", \"content\": \"\"}\n\n"

def create_agent():
    return PipelineAgent()
