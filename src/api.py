"""
api.py — FastAPI backend for Market Breadth Dashboard
Reads from /data/processed/ parquet files (built by data_builder.py)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from data_builder import load_processed, filter_date, df_to_records, INDICES, SECTOR_NAMES

log = logging.getLogger(__name__)

app = FastAPI(
    title="Market Breadth API",
    description="Bloomberg-style market breadth indicators for Vietnamese stock market",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── HELPERS ─────────────────────────────────────────────────────────────────

def _get(dataset: str, index: str, start: str | None, end: str | None) -> pd.DataFrame:
    """Load, filter, and validate a dataset."""
    idx_key = index.lower().replace("vnindex", "vnindex").replace("vn30", "VN30").replace("vn100", "VN100")
    # Normalise
    if index.upper() == "VNINDEX":
        idx_norm = "Vnindex"
    elif index.upper() == "VN30":
        idx_norm = "VN30"
    elif index.upper() == "VN100":
        idx_norm = "VN100"
    else:
        raise HTTPException(400, f"Unknown index '{index}'. Use VNINDEX, VN30, or VN100.")

    dataset_name = f"{dataset}_{idx_norm}"
    try:
        df = load_processed(dataset_name)
    except FileNotFoundError:
        raise HTTPException(404, f"Dataset '{dataset_name}' not found. Run data_builder first.")

    df = filter_date(df, start, end)
    return df


def _json(df: pd.DataFrame):
    if df.empty:
        return JSONResponse({"data": [], "count": 0})
    records = df_to_records(df)
    return JSONResponse({"data": records, "count": len(records)})


# ─── COMMON QUERY PARAMS ─────────────────────────────────────────────────────

DEFAULT_INDEX = Query("VNINDEX", description="Index: VNINDEX | VN30 | VN100")
START_DATE = Query(None, description="Start date YYYY-MM-DD (default: 1 year ago)")
END_DATE = Query(None, description="End date YYYY-MM-DD (default: today)")


def default_start():
    return (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Market Breadth API", "docs": "/docs"}


@app.get("/market-overview")
def market_overview(
    index: str = DEFAULT_INDEX,
    start: Optional[str] = START_DATE,
    end: Optional[str] = END_DATE,
):
    """
    AD Line, EMA10 overlay, Daily Net Advances, A/D Ratio.
    """
    if start is None:
        start = default_start()
    df = _get("market_overview", index, start, end)
    return _json(df)


@app.get("/participation")
def participation(
    index: str = DEFAULT_INDEX,
    start: Optional[str] = START_DATE,
    end: Optional[str] = END_DATE,
):
    """
    % Stocks Advancing and % Stocks Declining.
    """
    if start is None:
        start = default_start()
    df = _get("participation", index, start, end)
    return _json(df)


@app.get("/volume-breadth")
def volume_breadth(
    index: str = DEFAULT_INDEX,
    start: Optional[str] = START_DATE,
    end: Optional[str] = END_DATE,
):
    """
    Up/Down Volume Ratio, Net Volume, Cumulative Volume Index.
    """
    if start is None:
        start = default_start()
    df = _get("volume_breadth", index, start, end)
    return _json(df)


@app.get("/volume")
def volume(
    index: str = Query("VNINDEX", description="VNINDEX or VN30 only"),
    start: Optional[str] = START_DATE,
    end: Optional[str] = END_DATE,
):
    """
    OBV Breadth (cumulative sign-weighted volume).
    """
    if index.upper() not in ("VNINDEX", "VN30"):
        raise HTTPException(400, "OBV Breadth only available for VNINDEX and VN30.")
    if start is None:
        start = default_start()
    df = _get("volume", index, start, end)
    return _json(df)


@app.get("/momentum")
def momentum(
    index: str = DEFAULT_INDEX,
    start: Optional[str] = START_DATE,
    end: Optional[str] = END_DATE,
):
    """
    McClellan Oscillator (raw + ratio), New High/Low, NH/NL Ratio.
    """
    if start is None:
        start = default_start()
    df = _get("momentum", index, start, end)
    return _json(df)


@app.get("/trend")
def trend(
    index: str = DEFAULT_INDEX,
    start: Optional[str] = START_DATE,
    end: Optional[str] = END_DATE,
):
    """
    McClellan Summation, % Above MA (20/50/100/200), High-Low Index.
    """
    if start is None:
        start = default_start()
    df = _get("trend", index, start, end)
    return _json(df)


@app.get("/sector")
def sector(
    start: Optional[str] = START_DATE,
    end: Optional[str] = END_DATE,
    metrics: str = Query(
        "price,adline,outperform",
        description="Comma-separated: price | adline | outperform"
    ),
):
    """
    Sector AD Lines and % Sector Outperforming VNINDEX.
    """
    if start is None:
        start = (datetime.now() - timedelta(days=365 * 2)).strftime("%Y-%m-%d")

    try:
        df = load_processed("sector")
    except FileNotFoundError:
        raise HTTPException(404, "Sector data not built yet. Run data_builder.")

    df = filter_date(df, start, end)

    # Filter columns based on requested metrics
    wanted_metrics = [m.strip() for m in metrics.split(",")]
    keep_cols = []
    for sec in SECTOR_NAMES:
        if "price" in wanted_metrics and sec in df.columns:
            keep_cols.append(sec)
        if "adline" in wanted_metrics and f"{sec}_ADLine" in df.columns:
            keep_cols.append(f"{sec}_ADLine")
        if "outperform" in wanted_metrics and f"{sec}_Outperf" in df.columns:
            keep_cols.append(f"{sec}_Outperf")

    df = df[[c for c in keep_cols if c in df.columns]]
    return _json(df)


@app.get("/vnindex")
def vnindex_price(
    start: Optional[str] = START_DATE,
    end: Optional[str] = END_DATE,
):
    """VNINDEX close price for chart overlays."""
    if start is None:
        start = default_start()
    try:
        df = load_processed("vnindex")
    except FileNotFoundError:
        raise HTTPException(404, "VNINDEX data not built.")
    df = filter_date(df, start, end)
    return _json(df)


@app.get("/available-dates")
def available_dates():
    """Return min/max dates available for each dataset."""
    info = {}
    for name in [
        "market_overview_Vnindex",
        "participation_Vnindex",
        "volume_breadth_Vnindex",
        "momentum_Vnindex",
        "trend_Vnindex",
        "sector",
    ]:
        try:
            df = load_processed(name)
            info[name] = {
                "start": df.index.min().strftime("%Y-%m-%d"),
                "end":   df.index.max().strftime("%Y-%m-%d"),
                "rows":  len(df),
            }
        except Exception:
            info[name] = None
    return info


# ─── RUN ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
