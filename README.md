# 📊 Market Breadth Dashboard — Bloomberg Style

A full-stack financial analytics dashboard for Vietnamese stock market breadth data (VNINDEX, VN30, VN100). Built with FastAPI + Streamlit + Plotly in a Bloomberg Terminal-inspired dark UI.

---

## Architecture

```
Google Drive (VMT Drive / CSV2)
    ↓ google-api-python-client
src/data_builder.py  →  data/processed/*.parquet
    ↓ (read by)
src/api.py  (FastAPI, port 8000)
    ↓ (HTTP calls)
src/app.py  (Streamlit, port 8501)
```

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/<your-username>/market-breadth-dashboard.git
cd market-breadth-dashboard
```

### 2. Create virtual environment

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/Mac
# OR
.venv\Scripts\activate         # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Google Drive Authentication

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → Enable **Google Drive API**
3. Create **OAuth 2.0 Credentials** (Desktop app)
4. Download `credentials.json` → place it in `config/credentials.json`

```
market-breadth-dashboard/
├── config/
│   └── credentials.json   ← put here
```

First run will open a browser for OAuth consent. After auth, `config/token.json` is saved automatically.

---

## Running

### Step 1 — Build data (download from Drive + compute indicators)

```bash
cd src
python data_builder.py
```

This downloads all CSV files from Google Drive, computes all indicators, and saves to `data/processed/`.

**Expected time**: 3–10 minutes on first run (depends on Drive speed).

### Step 2 — Start the API

```bash
cd src
uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

API docs available at: http://localhost:8000/docs

### Step 3 — Start the dashboard

In a new terminal:

```bash
cd src
streamlit run app.py
```

Dashboard available at: http://localhost:8501

---

## Indicators

### 🔵 Market Overview
| Indicator | Formula | Source |
|-----------|---------|--------|
| AD Line | Cumulative (Advances − Declines) | ✅ Direct |
| Daily Net Advances | Advances − Declines | 🔶 Computed |
| A/D Ratio | Advances / Declines | 🔶 Computed |

### 🟣 Participation
| Indicator | Formula | Source |
|-----------|---------|--------|
| % Stocks Advancing | Advances / TotalIssues | 🔶 Computed |
| % Stocks Declining | Declines / TotalIssues | 🔶 Computed |

### 🟠 Volume Breadth
| Indicator | Formula | Source |
|-----------|---------|--------|
| Up/Down Volume Ratio | UpVolume / DownVolume | 🔶 Computed |
| Net Volume | UpVolume − DownVolume | 🔶 Computed |
| Cumulative Volume Index | Cumsum(UpVol − DownVol) | 🔶 Computed |

### 🟢 Volume
| Indicator | Formula | Source |
|-----------|---------|--------|
| OBV Breadth | Cumsum(sign(Adv−Dec) × TotalVolume) | 🔶 Computed |

### 🔴 Momentum
| Indicator | Formula | Source |
|-----------|---------|--------|
| McClellan Oscillator | — | ✅ Direct |
| New Highs/Lows (52W) | — | ✅ Direct |
| NH/NL Ratio | NH / (NH + NL) | ✅ Direct |

### 🟢 Trend
| Indicator | Formula | Source |
|-----------|---------|--------|
| McClellan Summation | — | ✅ Direct |
| % Above MA (20/50/100/200) | — | ✅ Direct |
| High-Low Index | NH / (NH + NL) × 100 | ✅ Direct |

### 🟡 Sector
| Indicator | Formula | Source |
|-----------|---------|--------|
| Sector AD Line | Cumsum(sign(daily return)) | 🔶 Computed |
| % Sector Outperforming | Sector return > VNINDEX return | 🔶 Computed |

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /market-overview` | AD Line, Net Advances, A/D Ratio |
| `GET /participation` | % Advancing, % Declining |
| `GET /volume-breadth` | U/D Volume Ratio, Net Volume, CVI |
| `GET /volume` | OBV Breadth |
| `GET /momentum` | McClellan Osc, NH/NL |
| `GET /trend` | Summation, % Above MA, High-Low Index |
| `GET /sector` | Sector AD Lines, Outperformance |
| `GET /vnindex` | VNINDEX price (for overlays) |

**Query params**: `index` (VNINDEX/VN30/VN100), `start` (YYYY-MM-DD), `end` (YYYY-MM-DD)

---

## Data Cache

- Raw CSVs: cached as `.parquet` in `data/processed/` for 24 hours
- API responses: cached in Streamlit with `st.cache_data(ttl=300)` (5 min)
- To force rebuild: delete files in `data/processed/`

---

## Folder Structure

```
market-breadth-dashboard/
├── src/
│   ├── data_builder.py    # Data ingestion + indicator computation
│   ├── api.py             # FastAPI endpoints
│   └── app.py             # Streamlit dashboard
├── data/
│   └── processed/         # Auto-generated parquet files
├── config/
│   ├── credentials.json   # Google OAuth (you provide)
│   └── token.json         # Auto-generated after first auth
├── requirements.txt
└── README.md
```

---

## Deployment Notes

For GitHub deployment + production use:
- Use a **service account** instead of OAuth (better for servers)
- Store `credentials.json` as a GitHub Secret / environment variable
- Consider Docker for easier deployment (Dockerfile not included, easy to add)
- Set `GOOGLE_APPLICATION_CREDENTIALS` env var if using service account

---

## License

MIT
