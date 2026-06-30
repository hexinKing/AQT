from typing import Optional

import pandas as pd

from .base import BaseStrategy, Signal


class TrailingStopStrategy(BaseStrategy):
    name = "trailing_stop"

    def evaluate(self, df: pd.DataFrame, params: dict) -> Optional[Signal]:
        """
        params: {trail_pct: float, entry_price: float, highest_since_entry: float}
        Only produces SELL signals.
        """
        if df.empty:
            return None

        trail_pct = params.get("trail_pct", 0.05)
        entry_price = params.get("entry_price", 0)
        if entry_price <= 0:
            return None

        highest = params.get("highest_since_entry", entry_price)
        close = df["close"].values

        # Update highest since entry
        for p in close:
            if p > highest:
                highest = float(p)

        # Record the updated highest in params so caller persists it
        params["highest_since_entry"] = highest

        last_price = float(close[-1])
        trail_price = highest * (1 - trail_pct)

        if last_price < trail_price:
            return Signal(
                symbol="",
                strategy=self.name,
                direction="SELL",
                price=last_price,
                reason=f"价格 {last_price:.2f} 从最高点 {highest:.2f} 回落 {trail_pct*100:.0f}%，触发移动止损 (止损价 {trail_price:.2f})",
            )

        return None
