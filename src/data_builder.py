"""
data_builder.py
Loads CSV files from Google Drive, computes all breadth indicators,
and saves processed data to /data/processed/ for fast reuse.
"""

import os
import io
import json
import logging
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from functools import lru_cache

import numpy as np
import pandas as pd
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ─── CONFIG ──────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "processed"
DATA_DIR.mkdir(parents=True, exist_ok=True)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_PATH = BASE_DIR / "config" / "token.json"
CREDS_PATH = BASE_DIR / "config" / "credentials.json"

# ─── GOOGLE DRIVE FOLDER IDs ─────────────────────────────────────────────────
# (Mapped from exploration of VMT Drive / CSV2 folder)
FOLDER_IDS = {
    "CSV2_ROOT":         "1jwRCI-WNgECr7bCGBYrqDggl6LoHXCL8",
    "Advances_Declines": "1X2eOE2lFwQzaAX1hZ4H6wMl5RuaiHRxJ",
    "ADLines":           "1gwF1swE8NQM8j4wDf1cJzkEv0H7f3vJD",
    "McClellan":         "1sou4J3-KsVbD5GTW_cd9hUpd1ctCRLmD",
    "New_High_New_Low":  "191dL7nqaMR5p7IxCUnMF9C4cN8k0vSiA",
    "Moving_Average":    "1jcIm6a55khr-H0WdrPpqn-MEmRr_g8-0",
    "Common":            "1dcGXbBBRvzxry2Xqy723p1Tvd8Fl6N1G",
    "Sectors":           "1KMWRdU5iDC7zNEYMWdpFuRK4_tsY3kan",
}

# ─── FILE NAME MAPPING ────────────────────────────────────────────────────────
# Maps logical indicator name → (folder_key, filename_on_drive)
FILE_MAP = {
    # AD Lines (✅ direct data)
    "ADLines_Vnindex":        ("ADLines", "ADLines_Vnindex.csv"),
    "ADLines_VN30":           ("ADLines", "ADLines_VN30.csv"),
    "ADLines_VN100":          ("ADLines", "ADLines_VN100.csv"),
    "ADLines_Vnindex_EMA_10": ("ADLines", "ADLines_Vnindex_EMA_10.csv"),
    "ADLines_VN30_EMA_10":    ("ADLines", "ADLines_VN30_EMA_10.csv"),
    "ADLines_VN100_EMA_10":   ("ADLines", "ADLines_VN100_EMA_10.csv"),

    # Advances / Declines / Volume raw
    "Advances_Vnindex":  ("Advances_Declines", "Advances_Vnindex.csv"),
    "Declines_Vnindex":  ("Advances_Declines", "Declines_Vnindex.csv"),
    "Advances_VN30":     ("Advances_Declines", "Advances_VN30.csv"),
    "Declines_VN30":     ("Advances_Declines", "Declines_VN30.csv"),
    "Advances_VN100":    ("Advances_Declines", "Advances_VN100.csv"),
    "Declines_VN100":    ("Advances_Declines", "Declines_VN100.csv"),
    "TotalIssues_Vnindex": ("Advances_Declines", "TotalIssues_.csv"),  # trailing _
    "TotalIssues_VN30":    ("Advances_Declines", "TotalIssues_VN30.csv"),
    "TotalIssues_VN100":   ("Advances_Declines", "TotalIssues_VN100.csv"),
    "UpVolume_Vnindex":    ("Advances_Declines", "UpVolume_Vnindex.csv"),
    "DownVolume_Vnindex":  ("Advances_Declines", "DownVolume_Vnindex.csv"),
    "UpVolume_VN30":       ("Advances_Declines", "UpVolume_VN30.csv"),
    "DownVolume_VN30":     ("Advances_Declines", "DownVolume_VN30.csv"),
    "UpVolume_VN100":      ("Advances_Declines", "UpVolume_VN100.csv"),
    "DownVolume_VN100":    ("Advances_Declines", "DownVolume_VN100.csv"),
    "TotalVolume_Vnindex": ("Advances_Declines", "TotalVolume_Vnindex.csv"),
    "TotalVolume_VN30":    ("Advances_Declines", "TotalVolume_VN30.csv"),

    # McClellan (✅ direct data)
    "McClellanOsc_Vnindex":       ("McClellan", "McClellanOsc_Vnindex.csv"),
    "McClellanOsc_VN30":          ("McClellan", "McClellanOsc_VN30.csv"),
    "McClellanOsc_VN100":         ("McClellan", "McClellanOsc_VN100.csv"),
    "McClellanOsc_ratio_Vnindex": ("McClellan", "McClellanOsc_ratio_Vnindex.csv"),
    "McClellanOsc_ratio_VN30":    ("McClellan", "McClellanOsc_ratio_VN30.csv"),
    "McClellanOsc_ratio_VN100":   ("McClellan", "McClellanOsc_ratio_VN100.csv"),
    "McClellanOsc_sum_Vnindex":   ("McClellan", "McClellanOsc_sum_Vnindex.csv"),
    "McClellanOsc_sum_VN30":      ("McClellan", "McClellanOsc_sum_VN30.csv"),
    "McClellanOsc_sum_VN100":     ("McClellan", "McClellanOsc_sum_VN100.csv"),

    # New High / Low (✅ direct data)
    "New_High_1_Vnindex_day":   ("New_High_New_Low", "New_High_1_Vnindex_day.csv"),
    "New_Low_1_Vnindex_day":    ("New_High_New_Low", "New_Low_1_Vnindex_day.csv"),
    "New_High_52_Vnindex_week": ("New_High_New_Low", "New_High_52_Vnindex_week.csv"),
    "New_Low_52_Vnindex_week":  ("New_High_New_Low", "New_Low_52_Vnindex_week.csv"),
    "New_High_52_VN30_week":    ("New_High_New_Low", "New_High_52_VN30_week.csv"),
    "New_High_52_VN100_week":   ("New_High_New_Low", "New_High_52_VN100_week.csv"),
    "New_Low_52_VN100_week":    ("New_High_New_Low", "New_Low_52_VN100_week.csv"),

    # Moving Averages (✅ direct data)
    "Above_Ma_20_Vnindex":  ("Moving_Average", "Above_Ma_20_Vnindex.csv"),
    "Above_Ma_20_VN30":     ("Moving_Average", "Above_Ma_20_VN30.csv"),
    "Above_Ma_20_VN100":    ("Moving_Average", "Above_Ma_20_VN100.csv"),
    "Above_Ma_50_VN30":     ("Moving_Average", "Above_Ma_50_VN30.csv"),
    "Above_Ma_50_VN100":    ("Moving_Average", "Above_Ma_50_VN100.csv"),
    "Above_Ma_100_Vnindex": ("Moving_Average", "Above_Ma_100_Vnindex.csv"),
    "Above_Ma_100_VN30":    ("Moving_Average", "Above_Ma_100_VN30.csv"),
    "Above_Ma_100_VN100":   ("Moving_Average", "Above_Ma_100_VN100.csv"),
    "Above_Ma_200_Vnindex": ("Moving_Average", "Above_Ma_200_Vnindex.csv"),
    "Above_Ma_200_VN30":    ("Moving_Average", "Above_Ma_200_VN30.csv"),
    "VNINDEX_with_AboveMA_20_50_100_200": ("Moving_Average", "VNINDEX_with_AboveMA_20_50_100_200.csv"),

    # Sector (✅ direct data)
    "VNINDEX": ("CSV2_ROOT", "VNINDEX.csv"),
    "VNENE":   ("Sectors", "VNENE.csv"),
    "VNCOND":  ("Sectors", "VNCOND.csv"),
    "VNCONS":  ("Sectors", "VNCONS.csv"),
    "VNFIN":   ("Sectors", "VNFIN.csv"),
    "VNHEAL":  ("Sectors", "VNHEAL.csv"),
    "VNIND":   ("Sectors", "VNIND.csv"),
    "VNIT":    ("Sectors", "VNIT.csv"),
    "VNMAT":   ("Sectors", "VNMAT.csv"),
    "VNREAL":  ("Sectors", "VNREAL.csv"),
    "VNUTI":   ("Sectors", "VNUTI.csv"),
}

SECTOR_NAMES = ["VNENE", "VNCOND", "VNCONS", "VNFIN", "VNHEAL",
                "VNIND", "VNIT", "VNMAT", "VNREAL", "VNUTI"]
INDICES = ["Vnindex", "VN30", "VN100"]

# ─── GOOGLE DRIVE AUTH ────────────────────────────────────────────────────────

def get_drive_service():
    """Authenticate and return Google Drive service."""
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDS_PATH.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {CREDS_PATH}. "
                    "Download OAuth2 credentials from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_PATH.parent.mkdir(exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds)


_service_cache = None

def drive_service():
    global _service_cache
    if _service_cache is None:
        _service_cache = get_drive_service()
    return _service_cache


# ─── FILE DISCOVERY ───────────────────────────────────────────────────────────

_folder_file_cache: dict[str, dict[str, str]] = {}

def list_folder_files(folder_id: str) -> dict[str, str]:
    """Return {filename: file_id} for all CSV files in a Drive folder."""
    if folder_id in _folder_file_cache:
        return _folder_file_cache[folder_id]

    svc = drive_service()
    result = {}
    page_token = None
    while True:
        resp = svc.files().list(
            q=f"'{folder_id}' in parents and mimeType='text/csv' and trashed=false",
            fields="nextPageToken, files(id, name)",
            pageSize=200,
            pageToken=page_token,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        ).execute()
        for f in resp.get("files", []):
            result[f["name"]] = f["id"]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break

    _folder_file_cache[folder_id] = result
    return result


def find_file_id(folder_key: str, filename: str) -> str | None:
    """Look up a file ID given folder key and filename."""
    folder_id = FOLDER_IDS[folder_key]
    files = list_folder_files(folder_id)
    # Exact match first
    if filename in files:
        return files[filename]
    # Case-insensitive fallback
    fl = filename.lower()
    for name, fid in files.items():
        if name.lower() == fl:
            return fid
    return None


# ─── CSV DOWNLOAD + PARSE ─────────────────────────────────────────────────────

def download_csv(file_id: str, indicator_name: str) -> pd.DataFrame:
    """Download a CSV from Drive and return a clean DataFrame."""
    svc = drive_service()
    request = svc.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buf.seek(0)

    try:
        df = pd.read_csv(buf)
        df.columns = df.columns.str.strip()
        df = df.loc[:, ~df.columns.str.startswith("Unnamed")]

        # Detect date column: "Date" (breadth files) or "datetime" (sector files)
        if "Date" in df.columns:
            date_col = "Date"
        elif "datetime" in df.columns:
            date_col = "datetime"
        else:
            date_col = df.columns[0]

        # Detect value column: prefer "Close"/"close", else last numeric column
        cols_lower = {c.lower(): c for c in df.columns}
        if "close" in cols_lower:
            value_col = cols_lower["close"]
        else:
            value_col = df.select_dtypes("number").columns[-1]

        df = df[[date_col, value_col]].rename(columns={date_col: "Date", value_col: indicator_name})
        df["Date"] = pd.to_datetime(df["Date"], dayfirst=False)
        df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
        # Keep only the date part (drop time component)
        df.index = df.index.normalize()
        df[indicator_name] = pd.to_numeric(df[indicator_name], errors="coerce")
        return df
    except Exception as e:
        log.error(f"Failed to parse {indicator_name}: {e}")
        return pd.DataFrame()


def load_indicator(name: str) -> pd.DataFrame:
    """Load a single indicator series from Drive (with local cache)."""
    cache_path = DATA_DIR / f"{name}.parquet"

    # Use cache if < 24 hours old
    if cache_path.exists():
        age = datetime.now().timestamp() - cache_path.stat().st_mtime
        if age < 86400:
            return pd.read_parquet(cache_path)

    if name not in FILE_MAP:
        log.warning(f"No file mapping for '{name}'")
        return pd.DataFrame()

    folder_key, filename = FILE_MAP[name]
    file_id = find_file_id(folder_key, filename)

    if file_id is None:
        log.warning(f"File not found on Drive: {filename} in {folder_key}")
        return pd.DataFrame()

    df = download_csv(file_id, name)
    if not df.empty:
        df.to_parquet(cache_path)
    return df


# ─── COMPUTE DERIVED INDICATORS ───────────────────────────────────────────────

def safe_div(a: pd.Series, b: pd.Series, fill=np.nan) -> pd.Series:
    """Division with zero/NaN guard."""
    return a.div(b.replace(0, np.nan)).fillna(fill)


def compute_all_indicators() -> dict[str, pd.DataFrame]:
    """
    Load all raw data and compute derived indicators.
    Returns dict of {indicator_name: DataFrame} indexed by Date.
    """
    log.info("Loading raw data from Google Drive…")
    raw: dict[str, pd.Series] = {}

    for name in FILE_MAP:
        df = load_indicator(name)
        if not df.empty:
            raw[name] = df[name]
            log.info(f"  ✓ {name} ({len(df)} rows)")
        else:
            log.warning(f"  ✗ {name} (empty)")

    result: dict[str, pd.DataFrame] = {}

    # ── Market Overview ──────────────────────────────────────────────────────
    for idx in INDICES:
        adv_key = f"Advances_{idx}"
        dec_key = f"Declines_{idx}"

        if adv_key in raw and dec_key in raw:
            adv = raw[adv_key]
            dec = raw[dec_key]
            aligned = pd.concat([adv, dec], axis=1).dropna()

            # Daily Net Advances
            net = (aligned[adv_key] - aligned[dec_key]).rename(f"NetAdvances_{idx}")

            # A/D Ratio
            adr = safe_div(aligned[adv_key], aligned[dec_key]).rename(f"ADRatio_{idx}")

            result[f"market_overview_{idx}"] = pd.concat([
                raw.get(f"ADLines_{idx}", pd.Series(name=f"ADLines_{idx}")),
                raw.get(f"ADLines_{idx}_EMA_10", pd.Series(name=f"ADLines_{idx}_EMA_10")),
                net, adr,
            ], axis=1)

    # ── Participation ────────────────────────────────────────────────────────
    for idx in INDICES:
        adv_key = f"Advances_{idx}"
        dec_key = f"Declines_{idx}"
        tot_key = f"TotalIssues_{idx}"

        if adv_key in raw and dec_key in raw and tot_key in raw:
            adv = raw[adv_key]
            dec = raw[dec_key]
            tot = raw[tot_key]
            aligned = pd.concat([adv, dec, tot], axis=1).dropna()

            pct_adv = (safe_div(aligned[adv_key], aligned[tot_key]) * 100).rename(f"PctAdvancing_{idx}")
            pct_dec = (safe_div(aligned[dec_key], aligned[tot_key]) * 100).rename(f"PctDeclining_{idx}")

            result[f"participation_{idx}"] = pd.concat([pct_adv, pct_dec], axis=1)

    # ── Volume Breadth ───────────────────────────────────────────────────────
    for idx in INDICES:
        up_key = f"UpVolume_{idx}"
        dn_key = f"DownVolume_{idx}"

        if up_key in raw and dn_key in raw:
            up = raw[up_key]
            dn = raw[dn_key]
            aligned = pd.concat([up, dn], axis=1).dropna()

            ud_ratio  = safe_div(aligned[up_key], aligned[dn_key]).rename(f"UDVolumeRatio_{idx}")
            net_vol   = (aligned[up_key] - aligned[dn_key]).rename(f"NetVolume_{idx}")
            cum_vi    = net_vol.cumsum().rename(f"CumulativeVolumeIndex_{idx}")

            result[f"volume_breadth_{idx}"] = pd.concat([ud_ratio, net_vol, cum_vi], axis=1)

    # ── Volume (OBV Breadth) ─────────────────────────────────────────────────
    for idx in ["Vnindex", "VN30"]:
        adv_key  = f"Advances_{idx}"
        dec_key  = f"Declines_{idx}"
        tvol_key = f"TotalVolume_{idx}"

        if adv_key in raw and dec_key in raw and tvol_key in raw:
            adv  = raw[adv_key]
            dec  = raw[dec_key]
            tvol = raw[tvol_key]
            aligned = pd.concat([adv, dec, tvol], axis=1).dropna()

            sign_val = np.sign(aligned[adv_key] - aligned[dec_key])
            obv = (sign_val * aligned[tvol_key]).cumsum().rename(f"OBVBreadth_{idx}")

            result[f"volume_{idx}"] = obv.to_frame()

    # ── Momentum ─────────────────────────────────────────────────────────────
    for idx in INDICES:
        series = []
        for key in [
            f"McClellanOsc_{idx}",
            f"McClellanOsc_ratio_{idx}",
            f"New_High_52_{idx}_week" if idx != "VN30" else None,
            f"New_Low_52_{idx}_week"  if idx != "VN30" else None,
        ]:
            if key and key in raw:
                series.append(raw[key])

        # NH / NL Ratio
        nh_key = f"New_High_52_{idx}_week" if idx != "VN30" else "New_High_52_VN30_week"
        nl_key = f"New_Low_52_{idx}_week"
        if nh_key in raw and nl_key in raw:
            nh = raw[nh_key]
            nl = raw[nl_key]
            aligned = pd.concat([nh, nl], axis=1).dropna()
            nhnl_ratio = safe_div(
                aligned[nh_key], aligned[nh_key] + aligned[nl_key].abs()
            ).rename(f"NHNLRatio_{idx}")
            series.append(nhnl_ratio)

        if series:
            result[f"momentum_{idx}"] = pd.concat(series, axis=1)

    # ── Trend ────────────────────────────────────────────────────────────────
    for idx in INDICES:
        series = []
        for key in [
            f"McClellanOsc_sum_{idx}",
            f"Above_Ma_20_{idx}",
            f"Above_Ma_50_{idx}" if idx != "Vnindex" else None,
            f"Above_Ma_100_{idx}",
            f"Above_Ma_200_{idx}" if idx != "VN100" else None,
        ]:
            if key and key in raw:
                series.append(raw[key])

        # High-Low Index = NH / (NH + NL)
        nh_key = f"New_High_52_{idx}_week" if idx != "VN30" else "New_High_52_VN30_week"
        nl_key = f"New_Low_52_{idx}_week"
        if nh_key in raw and nl_key in raw:
            nh = raw[nh_key]
            nl = raw[nl_key].abs()
            aligned = pd.concat([nh, nl], axis=1).dropna()
            hl_idx = safe_div(aligned[nh_key], aligned[nh_key] + aligned[nl_key])
            hl_idx = (hl_idx * 100).rename(f"HighLowIndex_{idx}")
            series.append(hl_idx)

        if series:
            result[f"trend_{idx}"] = pd.concat(series, axis=1)

    # ── Sector ───────────────────────────────────────────────────────────────
    sector_frames = []
    vnindex = raw.get("VNINDEX")

    for sec in SECTOR_NAMES:
        sec_df = load_indicator(sec)
        if sec_df.empty:
            continue
        sec_s = sec_df[sec]

        # Simple AD Line approximation: cumulative daily return sign
        ret = sec_s.pct_change()
        ad_line = np.sign(ret).cumsum().rename(f"{sec}_ADLine")

        # % Sector Outperforming vs VNINDEX
        if vnindex is not None:
            vn_ret = vnindex.pct_change()
            outperf = ((ret - vn_ret) > 0).astype(int).rename(f"{sec}_Outperf")
            sector_frames.append(pd.concat([sec_s.rename(sec), ad_line, outperf], axis=1))
        else:
            sector_frames.append(pd.concat([sec_s.rename(sec), ad_line], axis=1))

    if sector_frames:
        result["sector"] = pd.concat(sector_frames, axis=1)

    # ── VNINDEX close (for overlays) ─────────────────────────────────────────
    if "VNINDEX" in raw:
        result["vnindex"] = raw["VNINDEX"].to_frame()

    # ── Save all to parquet ──────────────────────────────────────────────────
    log.info("Saving processed data to disk…")
    for name, df in result.items():
        out_path = DATA_DIR / f"{name}.parquet"
        df.dropna(how="all").to_parquet(out_path)
        log.info(f"  Saved {name}.parquet ({len(df)} rows, {len(df.columns)} cols)")

    # Manifest
    manifest = {
        "built_at": datetime.now().isoformat(),
        "datasets": {k: list(v.columns) for k, v in result.items()},
    }
    (DATA_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2))
    log.info("Build complete.")
    return result


# ─── FAST LOAD (for API) ──────────────────────────────────────────────────────

@lru_cache(maxsize=32)
def load_processed(name: str) -> pd.DataFrame:
    """Load a processed parquet file with LRU cache."""
    path = DATA_DIR / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Processed file not found: {name}. Run data_builder first.")
    return pd.read_parquet(path)


def filter_date(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    """Filter DataFrame by date range."""
    if start:
        df = df[df.index >= pd.to_datetime(start)]
    if end:
        df = df[df.index <= pd.to_datetime(end)]
    return df


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame to list of JSON-serializable records."""
    df = df.copy()
    df.index = df.index.strftime("%Y-%m-%d")
    df = df.where(df.notna(), None)  # NaN → null
    return [{"date": idx, **row} for idx, row in df.iterrows()]


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Starting data build…")
    compute_all_indicators()
