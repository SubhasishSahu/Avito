"""
core/context_data.py
Clustered index model — one dot per city/region.
Each CLUSTER has member sub-indices shown on expand.
Selecting a cluster selects all its member sectors (union).
"""
from __future__ import annotations

# ══════════════════════════════════════════════════════════════
# CLUSTERS  — one dot on the map per geographic location
# members[] = sub-indices inside the cluster
# sectors   = union of all member sectors
# ══════════════════════════════════════════════════════════════
CLUSTERS: list[dict] = [

    # ── INDIA ──────────────────────────────────────────────────
    {
        "id": "INDIA", "label": "India", "city": "Mumbai",
        "x": 649, "y": 254, "group": "india",
        "members": [
            {"id":"NIFTY50",   "label":"Nifty 50",      "exchange":"NSE", "note":"Broad market — 50 large caps"},
            {"id":"NIFTYBANK", "label":"Nifty Bank",     "exchange":"NSE", "note":"Top 12 banking stocks"},
            {"id":"NIFTYIT",   "label":"Nifty IT",       "exchange":"NSE", "note":"Top IT sector index"},
            {"id":"SENSEX",    "label":"Sensex",          "exchange":"BSE", "note":"BSE flagship — 30 stocks"},
        ],
        "sectors": ["Banking","IT","Energy","Auto","Pharma","NBFC","Finance",
                    "Infrastructure","Metals","FMCG","Defence","Cement","Utilities"],
    },

    # ── JAPAN ──────────────────────────────────────────────────
    {
        "id": "JAPAN", "label": "Japan", "city": "Tokyo",
        "x": 820, "y": 192, "group": "asia",
        "members": [
            {"id":"NIKKEI",  "label":"Nikkei 225",  "exchange":"TSE",  "note":"225 large Japanese companies"},
            {"id":"TOPIX",   "label":"TOPIX",        "exchange":"TSE",  "note":"All Tokyo Stock Exchange 1st section"},
        ],
        "sectors": ["Auto","IT","Metals","Energy","Engineering"],
    },

    # ── HONG KONG / CHINA ──────────────────────────────────────
    {
        "id": "CHINA_HK", "label": "China/HK", "city": "Hong Kong",
        "x": 791, "y": 235, "group": "asia",
        "members": [
            {"id":"HANGSENG", "label":"Hang Seng",      "exchange":"HKEX", "note":"HK blue chips"},
            {"id":"SHANGHAI", "label":"SSE Composite",  "exchange":"SSE",  "note":"All Shanghai-listed stocks"},
            {"id":"CSI300",   "label":"CSI 300",        "exchange":"SSE",  "note":"Top 300 A-share companies"},
        ],
        "sectors": ["Metals","Energy","Finance","IT","Infrastructure","Auto"],
    },

    # ── SOUTHEAST ASIA / SINGAPORE ─────────────────────────────
    {
        "id": "SEA", "label": "SE Asia", "city": "Singapore",
        "x": 773, "y": 289, "group": "asia",
        "members": [
            {"id":"SGX",   "label":"STI Singapore", "exchange":"SGX",  "note":"Straits Times Index — 30 stocks"},
            {"id":"SET50", "label":"SET 50",        "exchange":"SET",  "note":"Thailand top 50"},
            {"id":"JKSE",  "label":"IDX Composite", "exchange":"IDX",  "note":"Indonesia all stocks"},
        ],
        "sectors": ["Banking","Energy","Logistics","Finance","FMCG"],
    },

    # ── SOUTH KOREA ────────────────────────────────────────────
    {
        "id": "KOREA", "label": "Korea", "city": "Seoul",
        "x": 807, "y": 200, "group": "asia",
        "members": [
            {"id":"KOSPI",  "label":"KOSPI",    "exchange":"KRX", "note":"Korea Composite Stock Index"},
            {"id":"KOSDAQ", "label":"KOSDAQ",   "exchange":"KRX", "note":"Korea tech & growth companies"},
        ],
        "sectors": ["IT","Auto","Metals","Pharma"],
    },

    # ── AUSTRALIA ──────────────────────────────────────────────
    {
        "id": "AUSTRALIA", "label": "Australia", "city": "Sydney",
        "x": 855, "y": 378, "group": "asia",
        "members": [
            {"id":"ASX200", "label":"ASX 200", "exchange":"ASX", "note":"Top 200 Australian companies"},
        ],
        "sectors": ["Metals","Mining","Energy","Banking"],
    },

    # ── UK / LONDON ────────────────────────────────────────────
    {
        "id": "LONDON", "label": "London", "city": "London",
        "x": 433, "y": 148, "group": "europe",
        "members": [
            {"id":"FTSE100", "label":"FTSE 100",    "exchange":"LSE", "note":"UK top 100 companies"},
            {"id":"FTSE250", "label":"FTSE 250",    "exchange":"LSE", "note":"UK mid-cap index"},
        ],
        "sectors": ["Banking","Energy","Metals","Pharma","Finance","Mining"],
    },

    # ── EUROPE CONTINENT ───────────────────────────────────────
    {
        "id": "EUROPE", "label": "Europe", "city": "Frankfurt",
        "x": 462, "y": 150, "group": "europe",
        "members": [
            {"id":"DAX",       "label":"DAX 40",        "exchange":"XETRA",   "note":"German top 40"},
            {"id":"CAC40",     "label":"CAC 40",        "exchange":"Euronext", "note":"French top 40"},
            {"id":"EUROSTOXX", "label":"Euro Stoxx 50", "exchange":"Euronext", "note":"Eurozone top 50"},
            {"id":"SMI",       "label":"SMI",           "exchange":"SIX",      "note":"Swiss top 20"},
        ],
        "sectors": ["Auto","IT","Metals","Engineering","Pharma","Banking","FMCG","Logistics"],
    },

    # ── US MARKETS ─────────────────────────────────────────────
    {
        "id": "US", "label": "US Markets", "city": "New York",
        "x": 213, "y": 192, "group": "americas",
        "members": [
            {"id":"SP500",  "label":"S&P 500",    "exchange":"NYSE",   "note":"500 large US companies"},
            {"id":"NASDAQ", "label":"Nasdaq 100", "exchange":"NASDAQ", "note":"100 largest non-financial"},
            {"id":"DJIA",   "label":"Dow Jones",  "exchange":"NYSE",   "note":"30 blue-chip industrials"},
        ],
        "sectors": ["IT","Banking","Energy","Pharma","Auto","Finance","FMCG"],
    },

    # ── CANADA ─────────────────────────────────────────────────
    {
        "id": "CANADA", "label": "Canada", "city": "Toronto",
        "x": 200, "y": 165, "group": "americas",
        "members": [
            {"id":"TSX", "label":"TSX Composite", "exchange":"TSX", "note":"Canada's main exchange"},
        ],
        "sectors": ["Mining","Energy","Banking","Metals"],
    },

    # ── BRAZIL ─────────────────────────────────────────────────
    {
        "id": "BRAZIL", "label": "Brazil", "city": "São Paulo",
        "x": 280, "y": 345, "group": "americas",
        "members": [
            {"id":"BOVESPA", "label":"Bovespa", "exchange":"B3", "note":"Brazil's main index"},
        ],
        "sectors": ["Metals","Energy","Banking","Mining"],
    },

    # ── MIDDLE EAST ────────────────────────────────────────────
    {
        "id": "MIDEAST", "label": "Middle East", "city": "Dubai",
        "x": 565, "y": 253, "group": "mideast",
        "members": [
            {"id":"TADAWUL", "label":"Tadawul",   "exchange":"Saudi", "note":"Saudi Arabia main market"},
            {"id":"DFMGI",   "label":"DFM Dubai", "exchange":"DFM",   "note":"Dubai Financial Market"},
            {"id":"ADX",     "label":"ADX",       "exchange":"ADX",   "note":"Abu Dhabi Securities Exchange"},
        ],
        "sectors": ["Energy","Banking","Infrastructure","Logistics"],
    },

    # ── AFRICA ─────────────────────────────────────────────────
    {
        "id": "AFRICA", "label": "Africa", "city": "Johannesburg",
        "x": 507, "y": 365, "group": "africa",
        "members": [
            {"id":"JSE",   "label":"JSE All Share", "exchange":"JSE", "note":"South Africa main index"},
            {"id":"EGX30", "label":"EGX 30",        "exchange":"EGX", "note":"Egypt's blue chips"},
        ],
        "sectors": ["Metals","Mining","Banking","Energy","Infrastructure"],
    },

    # ── COMMODITY: OIL ─────────────────────────────────────────
    {
        "id": "COM_OIL", "label": "Crude Oil", "city": "Oil Hubs",
        "x": 430, "y": 136, "group": "commodity",
        "members": [
            {"id":"BRENT",    "label":"Brent Crude",  "exchange":"ICE",   "note":"Global benchmark, North Sea"},
            {"id":"WTI",      "label":"WTI Crude",    "exchange":"NYMEX", "note":"US benchmark, Cushing OK"},
            {"id":"DUBAI_OIL","label":"Dubai Crude",  "exchange":"DME",   "note":"Middle East benchmark"},
        ],
        "sectors": ["Energy","FMCG","Logistics","Auto","Cement"],
    },

    # ── COMMODITY: METALS ──────────────────────────────────────
    {
        "id": "COM_METALS", "label": "Metals", "city": "LME London",
        "x": 424, "y": 155, "group": "commodity",
        "members": [
            {"id":"LME_CU",  "label":"LME Copper", "exchange":"LME",   "note":"Global copper benchmark"},
            {"id":"LME_AL",  "label":"LME Aluminium","exchange":"LME",  "note":"Global aluminium benchmark"},
            {"id":"GOLD",    "label":"Gold (COMEX)", "exchange":"COMEX","note":"Safe haven & jewellery demand"},
            {"id":"COAL",    "label":"Coking Coal",  "exchange":"Qld",  "note":"Steelmaking coal — Australia"},
        ],
        "sectors": ["Metals","Mining","Infrastructure","Engineering","Banking","Finance"],
    },

    # ── COMMODITY: AGRI / SHIPPING ─────────────────────────────
    {
        "id": "COM_AGRI", "label": "Agri/Freight", "city": "Global",
        "x": 500, "y": 130, "group": "commodity",
        "members": [
            {"id":"PALM_OIL","label":"Palm Oil",       "exchange":"Bursa", "note":"Edible oil — MY/ID supply"},
            {"id":"BDI",     "label":"Baltic Dry",     "exchange":"Baltic","note":"Global dry freight costs"},
            {"id":"USDINR",  "label":"USD/INR",        "exchange":"NSE",   "note":"Rupee exchange rate"},
        ],
        "sectors": ["FMCG","Logistics","IT","Pharma","Energy","Metals"],
    },
]

# ══════════════════════════════════════════════════════════════
# SECTORS
# ══════════════════════════════════════════════════════════════
SECTORS: list[dict] = [
    {"id":"Banking",        "label":"Banking",    "icon":"🏦","color":"#38b6ff","stocks":["HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK"]},
    {"id":"IT",             "label":"IT",         "icon":"💻","color":"#a78bfa","stocks":["TCS","INFY","HCLTECH","WIPRO","TECHM"]},
    {"id":"Energy",         "label":"Energy",     "icon":"⚡","color":"#f5a623","stocks":["RELIANCE","ONGC","BPCL","ADANIGREEN","NTPC"]},
    {"id":"Auto",           "label":"Auto",       "icon":"🚗","color":"#34d399","stocks":["MARUTI","M&M","BAJAJ-AUTO","HEROMOTOCO","EICHERMOT"]},
    {"id":"Pharma",         "label":"Pharma",     "icon":"💊","color":"#f472b6","stocks":["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB","LAURUSLABS"]},
    {"id":"Metals",         "label":"Metals",     "icon":"⚙️","color":"#94a3b8","stocks":["TATASTEEL","JSWSTEEL","HINDALCO","NMDC","NATIONALUM"]},
    {"id":"FMCG",           "label":"FMCG",       "icon":"🛒","color":"#00e5a0","stocks":["HINDUNILVR","ITC","NESTLEIND","BRITANNIA","TATACONSUM"]},
    {"id":"Finance",        "label":"Finance",    "icon":"📈","color":"#22d3ee","stocks":["BAJFINANCE","JIOFIN","PFC","RECLTD","CAMS"]},
    {"id":"Infrastructure", "label":"Infra",      "icon":"🏗️","color":"#fb923c","stocks":["LT","ADANIPORTS","RVNL","GPPL","ENGINERSIN"]},
    {"id":"Defence",        "label":"Defence",    "icon":"🛡️","color":"#ff4757","stocks":["HAL","MAZDOCK","BDL","ZENTEC","PARAS"]},
    {"id":"NBFC",           "label":"NBFC",       "icon":"🏛️","color":"#6366f1","stocks":["BAJFINANCE","BAJAJFINSV","SPANDANA"]},
    {"id":"Cement",         "label":"Cement",     "icon":"🏚️","color":"#d4a574","stocks":["ULTRACEMCO","GRASIM"]},
    {"id":"Mining",         "label":"Mining",     "icon":"⛏️","color":"#84cc16","stocks":["COALINDIA","NMDC","HINDCOPPER"]},
    {"id":"Logistics",      "label":"Logistics",  "icon":"🚢","color":"#e879f9","stocks":["DELHIVERY","ADANIPORTS"]},
    {"id":"Utilities",      "label":"Utilities",  "icon":"🔌","color":"#2dd4bf","stocks":["POWERGRID","NTPC"]},
]

# ══════════════════════════════════════════════════════════════
# COMMODITY FLAGS
# ══════════════════════════════════════════════════════════════
COMMODITY_FLAGS: list[dict] = [
    {"commodity":"Crude Oil","symbol":"OIL","icon":"🛢️",
     "direction":"↑ = headwind for importers, windfall for upstream",
     "sensitive_sectors":["Energy","FMCG","Auto","Logistics","Cement"],
     "beneficiary_sectors":["Energy"],
     "note":"India imports ~85% of crude. Every $10/bbl rise costs ~₹70,000 cr/yr.",
     "correlated_stocks":["RELIANCE","ONGC","BPCL","HINDUNILVR","MARUTI"]},
    {"commodity":"Base Metals","symbol":"METALS","icon":"🔶",
     "direction":"↑ = input cost rise; also signals global growth momentum",
     "sensitive_sectors":["Metals","Infrastructure","Engineering","Auto"],
     "beneficiary_sectors":["Metals","Mining"],
     "note":"LME Copper is the bellwether. India imports ~50% of copper needs.",
     "correlated_stocks":["HINDALCO","NMDC","HINDCOPPER","LT","BHEL"]},
    {"commodity":"Coking Coal","symbol":"COAL","icon":"⬛",
     "direction":"↑ = steelmaker margin compression",
     "sensitive_sectors":["Metals","Cement"],
     "beneficiary_sectors":["Mining"],
     "note":"India imports ~80% from Australia. Freight amplifies impact.",
     "correlated_stocks":["TATASTEEL","JSWSTEEL","ULTRACEMCO","COALINDIA"]},
    {"commodity":"Palm Oil","symbol":"PALMOIL","icon":"🌴",
     "direction":"↑ = FMCG input cost headwind",
     "sensitive_sectors":["FMCG"],
     "beneficiary_sectors":[],
     "note":"India is world's largest importer. Malaysia & Indonesia supply 90%+.",
     "correlated_stocks":["HINDUNILVR","BRITANNIA","NESTLEIND","TATACONSUM"]},
    {"commodity":"USD / INR","symbol":"USDINR","icon":"💱",
     "direction":"Rupee weakens → IT & Pharma exports gain in INR terms",
     "sensitive_sectors":["IT","Pharma"],
     "beneficiary_sectors":["IT","Pharma"],
     "note":"Every ₹1 depreciation adds ~1.5–2% to IT sector revenue in INR.",
     "correlated_stocks":["TCS","INFY","SUNPHARMA","DRREDDY","WIPRO"]},
    {"commodity":"Freight (BDI)","symbol":"BDI","icon":"🚢",
     "direction":"↑ = higher import costs across commodity-dependent sectors",
     "sensitive_sectors":["Logistics","Metals","FMCG","Energy"],
     "beneficiary_sectors":["Logistics"],
     "note":"Red Sea disruptions adding 12–18 days to Europe–Asia routes.",
     "correlated_stocks":["DELHIVERY","ADANIPORTS","TATASTEEL","HINDUNILVR"]},
]

def get_clusters() -> list[dict]:        return CLUSTERS
def get_sectors() -> list[dict]:         return SECTORS
def get_commodity_flags() -> list[dict]: return COMMODITY_FLAGS

# back-compat shim — landing.html still injects __INDICES__
def get_indices() -> list[dict]:
    """Flatten clusters into individual index records for back-compat."""
    out = []
    for c in CLUSTERS:
        out.append({
            "id": c["id"], "label": c["label"], "city": c["city"],
            "x": c["x"], "y": c["y"], "group": c["group"],
            "region": c.get("region", c["city"]),
            "sectors": c["sectors"],
            "members": c["members"],
            "exchange": "/".join(set(m["exchange"] for m in c["members"])),
        })
    return out
