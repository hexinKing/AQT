from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Signal:
    symbol: str
    strategy: str
    direction: str  # BUY / SELL
    price: float
    reason: str


class BaseStrategy:
    name: str = "base"

    def evaluate(self, df: pd.DataFrame, params: dict) -> Optional[Signal]:
        raise NotImplementedError
