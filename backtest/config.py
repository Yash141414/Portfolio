from dataclasses import dataclass, field
from datetime import time


@dataclass(frozen=True)
class Costs:

    brokerage_per_order: float = 20.0      # Dhan: Rs 20 flat per executed F&O order
    stt_sell: float = 0.001                # 0.1% of premium on sell (verify: Budget 2026 may have raised it)
    exchange_txn: float = 0.0003503        # NSE option transaction charge, on premium
    sebi_per_crore: float = 10.0           # Rs 10 per crore of turnover
    stamp_buy: float = 0.00003             # 0.003% of premium on buy
    gst: float = 0.18                      # on brokerage + exchange + SEBI
    slippage_pts: float = 0.25             # adverse points per fill, floor
    slippage_pct: float = 0.005            # adverse % of premium per fill; the larger of the two applies


@dataclass(frozen=True)
class Config:
    """Backtest settings: capital, sizing limits, session times and charges (see field comments)."""
    capital_per_strategy: float = 1_000_000.0   # Rs 10 lakh sleeve per strategy
    risk_per_trade: float = 0.02                # fraction of sleeve equity lost if a trade hits its worst case
    max_lots: int = 20                          # well under the NIFTY freeze quantity
    session_open: time = time(9, 15)
    last_entry: time = time(14, 30)
    square_off: time = time(15, 15)             # all positions closed at this bar's open
    strike_step: int = 50
    costs: Costs = field(default_factory=Costs)


DEFAULT = Config()
