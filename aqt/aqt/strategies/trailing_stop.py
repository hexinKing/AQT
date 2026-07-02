from typing import Optional

import pandas as pd

from .base import BaseStrategy, Signal


class TrailingStopStrategy(BaseStrategy):
    name = "trailing_stop"

    def evaluate(self, df: pd.DataFrame, params: dict) -> Optional[Signal]:
        """
        params: {trail_pct: float, entry_price: float, highest_since_entry: float}
        Only produces SELL signals.
        highest_since_entry only tracks from entry, NOT full history.
        """
        if df.empty:
            return None

        trail_pct = params.get("trail_pct", 0.05)
        entry_price = params.get("entry_price", 0)
        if entry_price <= 0:
            return None

        # Running highest since entry — only updated with today's bar, never back-scanned
        highest = params.get("highest_since_entry", entry_price)

        # If this is the first run (highest not yet persisted), seed it from today's high too
        if "highest_since_entry" not in params:
            today_high = float(df["high"].iloc[-1])
            highest = max(entry_price, today_high)

        # Update with today's bar only
        today_high = float(df["high"].iloc[-1])
        if today_high > highest:
            highest = today_high

        params["highest_since_entry"] = highest

        last_price = float(df["close"].iloc[-1])
        trail_price = highest * (1 - trail_pct)

        if last_price < trail_price:
            return Signal(
                symbol="",
                strategy=self.name,
                direction="SELL",
                price=last_price,
                reason=f"价格 {last_price:.2f} 从入场后最高点 {highest:.2f} 回落 {trail_pct*100:.0f}%，触发移动止损 (止损价 {trail_price:.2f})",
                meta={"highest_since_entry": highest, "trail_price": round(trail_price, 2), "trail_pct": trail_pct},
            )

        return None
