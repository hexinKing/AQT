from dataclasses import dataclass, field
from typing import Optional

import pandas as pd


@dataclass
class Signal:
    symbol: str
    strategy: str
    direction: str  # BUY / SELL
    price: float
    reason: str
    meta: dict = field(default_factory=dict)  # extra context for downstream consumers


class BaseStrategy:
    name: str = "base"

    def evaluate(self, df: pd.DataFrame, params: dict) -> Optional[Signal]:
        raise NotImplementedError
