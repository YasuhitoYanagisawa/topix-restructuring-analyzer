"""
MCP Server for Stock Data
カスタムMCPサーバー：株式データ取得ツールをMCPプロトコルで公開する。
Google ADKエージェントからMcpToolsetを通じて接続される。
"""
import asyncio
import json
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

from topix_agent.tools.stock_data import (
    fetch_jpx_stock_list,
    get_stock_market_data,
    get_annual_trading_volume,
)
from topix_agent.tools.topix_calc import (
    evaluate_topix_candidate,
    screen_topix_candidates,
    format_candidates_summary,
)

# MCPサーバーの初期化
mcp = FastMCP(
    "topix-stock-data",
    description="TOPIX銘柄分析用の株式データ取得MCPサーバー",
)


@mcp.tool()
def get_stock_list(market: str = "all") -> str:
    """東証上場銘柄一覧を取得する。

    JPX公式データから銘柄コード・銘柄名・市場区分を取得します。
    marketパラメータで取得する市場区分をフィルタリングできます。

    Args:
        market: "standard"（スタンダード）, "growth"（グロース）, or "all"（全て）

    Returns:
        銘柄リスト（JSON文字列）
    """
    stocks = fetch_jpx_stock_list(market_filter=market)
    return json.dumps(stocks[:100], ensure_ascii=False)  # 最初の100件


@mcp.tool()
def get_market_data_for_codes(codes_json: str) -> str:
    """指定銘柄コードの時価総額・出来高等のマーケットデータを取得する。

    yfinanceから最新の市場データを取得します。

    Args:
        codes_json: 銘柄コードのJSONリスト（例: '["7203", "9984"]'）

    Returns:
        マーケットデータ（JSON文字列）
    """
    codes = json.loads(codes_json)
    data = get_stock_market_data(codes[:50])  # 最大50件
    return json.dumps(data, ensure_ascii=False, default=str)


@mcp.tool()
def get_volume_data_for_codes(codes_json: str) -> str:
    """指定銘柄の年間出来高・売買代金データを取得する。

    過去1年の出来高データから年間売買代金回転率の計算に必要な値を取得します。

    Args:
        codes_json: 銘柄コードのJSONリスト

    Returns:
        出来高データ（JSON文字列）
    """
    codes = json.loads(codes_json)
    data = get_annual_trading_volume(codes[:50])
    return json.dumps(data, ensure_ascii=False, default=str)


@mcp.tool()
def analyze_topix_candidate(
    code: str,
    name: str,
    market: str,
    market_cap: float,
    float_shares: float,
    shares_outstanding: float,
    annual_turnover_value: float,
) -> str:
    """単一銘柄のTOPIX新規採用可能性を評価する。

    Args:
        code: 銘柄コード
        name: 銘柄名
        market: 市場区分
        market_cap: 時価総額（円）
        float_shares: 浮動株数
        shares_outstanding: 発行済株式数
        annual_turnover_value: 年間売買代金（円）

    Returns:
        評価結果（JSON文字列）
    """
    result = evaluate_topix_candidate(
        code=code,
        name=name,
        market=market,
        market_cap=market_cap,
        float_shares=float_shares,
        shares_outstanding=shares_outstanding,
        annual_turnover_value=annual_turnover_value,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


if __name__ == "__main__":
    mcp.run()
