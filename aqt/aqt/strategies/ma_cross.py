from typing import Optional

import pandas as pd

from .base import BaseStrategy, Signal


class MACrossStrategy(BaseStrategy):
    name = "ma_cross"

    def evaluate(self, df: pd.DataFrame, params: dict) -> Optional[Signal]:
        """
        params: {short_window: int, long_window: int}
        """
        short = params.get("short_window", 5)
        long = params.get("long_window", 20)

        if len(df) < long + 1:
            return None

        close = df["close"]
        short_ma = close.rolling(short).mean()
        long_ma = close.rolling(long).mean()

        # previous bar
        prev_short = short_ma.iloc[-2]
        prev_long = long_ma.iloc[-2]
        # current bar
        curr_short = short_ma.iloc[-1]
        curr_long = long_ma.iloc[-1]

        if pd.isna(prev_short) or pd.isna(prev_long) or pd.isna(curr_short) or pd.isna(curr_long):
            return None

        last_price = float(close.iloc[-1])

        # Golden cross: short crosses above long
        if prev_short <= prev_long and curr_short > curr_long:
            return Signal(
                symbol="",
                strategy=self.name,
                direction="BUY",
                price=last_price,
                reason=f"MA{short}({curr_short:.2f}) 上穿 MA{long}({curr_long:.2f}) → 金叉买入",
            )

        # Death cross: short crosses below long
        if prev_short >= prev_long and curr_short < curr_long:
            return Signal(
                symbol="",
                strategy=self.name,
                direction="SELL",
                price=last_price,
                reason=f"MA{short}({curr_short:.2f}) 下穿 MA{long}({curr_long:.2f}) → 死叉卖出",
            )

        return None
