from typing import Optional

import pandas as pd

from .base import BaseStrategy, Signal


class GridStrategy(BaseStrategy):
    name = "grid"

    def evaluate(self, df: pd.DataFrame, params: dict) -> Optional[Signal]:
        """
        params: {grid_pct: float, base_price: float}
        grid_pct e.g. 0.03 = 3% grid spacing
        """
        if df.empty:
            return None

        grid_pct = params.get("grid_pct", 0.03)
        base_price = params.get("base_price", 0)
        if base_price <= 0:
            return None

        last_price = float(df["close"].iloc[-1])
        prev_price = float(df["close"].iloc[-2]) if len(df) >= 2 else last_price

        # Check up to 5 grid levels
        for n in range(1, 6):
            buy_level = base_price * (1 - grid_pct * n)
            sell_level = base_price * (1 + grid_pct * n)

            # Price fell into buy zone
            if prev_price > buy_level and last_price <= buy_level * 1.002:
                return Signal(
                    symbol="",
                    strategy=self.name,
                    direction="BUY",
                    price=last_price,
                    reason=f"价格 {last_price:.2f} 触及买入网格 L{n} ({buy_level:.2f})，网格间隔 {grid_pct*100:.0f}%",
                    meta={"grid_level": n, "base_price": base_price, "grid_pct": grid_pct},
                )

            # Price rose into sell zone
            if prev_price < sell_level and last_price >= sell_level * 0.998:
                return Signal(
                    symbol="",
                    strategy=self.name,
                    direction="SELL",
                    price=last_price,
                    reason=f"价格 {last_price:.2f} 触及卖出网格 L{n} ({sell_level:.2f})，网格间隔 {grid_pct*100:.0f}%",
                    meta={"grid_level": n, "base_price": base_price, "grid_pct": grid_pct},
                )

        return None
