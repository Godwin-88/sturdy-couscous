from __future__ import annotations

import csv
import io
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

import pandas as pd


@dataclass(frozen=True)
class MacroEvent:
    date: str
    event: str
    window_start: str
    window_end: str
    affected_tickers: str
    dampening: float


_DEFAULT_MACRO_CSV = """date,event,window_start,window_end,affected_tickers,dampening
2020-03-12,ECB Rate Decision,2020-03-11,2020-03-14,SPY;QQQ;-0.30
2020-06-10,FOMC Statement,2020-06-09,2020-06-12,SPY;QQQ;TLT;-0.25
2022-06-15,FOMC +100bps,2022-06-14,2022-06-17,SPY;QQQ;TLT;-0.35
2022-07-13,CPI YoY Print,2022-07-12,2022-07-15,SPY;QQQ;GLD;-0.20
2023-03-10,Silicon Valley Bank Failure,2023-03-09,2023-03-12,SPY;QQQ;TLT;-0.40
2024-11-06,US Election Day,2024-11-05,2024-11-08,SPY;QQQ;-0.25
"""


class _MacroCalendar:
    def __init__(self) -> None:
        rows: List[MacroEvent] = []
        reader = csv.DictReader(io.StringIO(_DEFAULT_MACRO_CSV))
        for row in reader:
            rows.append(MacroEvent(
                date=row["date"],
                event=row["event"],
                window_start=row["window_start"],
                window_end=row["window_end"],
                affected_tickers=row["affected_tickers"],
                dampening=float(row["dampening"]),
            ))
        self._rows = rows

    def on(self, ticker: str, dt: datetime) -> float:
        t = dt.date().isoformat()
        for row in self._rows:
            if row.date <= t <= row.window_end:
                tickers = [x.strip() for x in row.affected_tickers.split(";") if x.strip()]
                if ticker in tickers or "ALL" in tickers:
                    return float(row.dampening)
        return 0.0


_macro = _MacroCalendar()


class NewsOverlay:
    def __init__(self) -> None:
        self.approximation: str = "neutral pass-through (0.0) — historical RSS corpus not available"

    def get(self, ticker: str, dt: datetime) -> float:
        return 0.0


class MacroOverlay:
    def __init__(self) -> None:
        self.approximation: str = (
            "FRED economic calendar pre-event dampening windows replayed from "
            "bundled fallback calendar (static CSV)"
        )

    def get(self, ticker: str, dt: datetime) -> float:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return _macro.on(ticker, dt)


def get_overlay(
    overlay_name: str,
    ticker: str,
    dt: datetime,
    disabled: bool = False,
) -> float:
    if disabled:
        return 0.0
    name = overlay_name.lower()
    if name == "news":
        return NewsOverlay().get(ticker, dt)
    if name == "macro":
        return MacroOverlay().get(ticker, dt)
    raise ValueError(f"Unknown overlay {overlay_name!r}")
