def evaluate_topix_candidate(market_cap: float, annual_volume: float) -> bool:
    """Evaluate if a stock meets TOPIX criteria."""
    return market_cap >= 40_000_000_000 and annual_volume > 0
