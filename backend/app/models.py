from pydantic import BaseModel, Field
from typing import Literal, Optional

class AnalyzeRequest(BaseModel):
    symbol: str = Field(default="NVDA", min_length=1, max_length=15)
    company: str = Field(default="NVIDIA", max_length=80)
    investment_amount: float = Field(default=1000, gt=0, le=1000000)
    portfolio_value: float = Field(default=10000, gt=0, le=10000000)
    horizon: Literal["day", "week", "month", "year"] = "month"
    risk_tolerance: Literal["conservative", "balanced", "aggressive"] = "balanced"
    max_position_pct: float = Field(default=20, gt=0, le=100)
