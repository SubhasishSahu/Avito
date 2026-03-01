"""
core/context_data.py
Static reference data: indices, sectors, commodity flags.
"""
from __future__ import annotations

INDICES: list[dict] = [
    # ── INDIA ──
    {"id":"NIFTY50",   "label":"Nifty 50",       "exchange":"NSE",    "city":"Mumbai",    "x":649,"y":254,"region":"India",       "group":"india",    "sectors":["Banking","IT","Energy","Auto","Pharma","NBFC","Finance","Infrastructure","Metals","FMCG","Defence","Cement","Utilities"]},
    {"id":"NIFTYBANK", "label":"Nifty Bank",      "exchange":"NSE",    "city":"Mumbai",    "x":655,"y":250,"region":"India",       "group":"india",    "sectors":["Banking","NBFC","Finance"]},
    {"id":"NIFTYIT",   "label":"Nifty IT",        "exchange":"NSE",    "city":"Mumbai",    "x":655,"y":258,"region":"India",       "group":"india",    "sectors":["IT"]},
    {"id":"SENSEX",    "label":"Sensex",           "exchange":"BSE",    "city":"Mumbai",    "x":643,"y":252,"region":"India",       "group":"india",    "sectors":["Banking","IT","Energy","Auto","Pharma","Finance","Metals","FMCG"]},
    # ── ASIA PACIFIC ──
    {"id":"NIKKEI",    "label":"Nikkei 225",       "exchange":"TSE",    "city":"Tokyo",     "x":820,"y":192,"region":"Asia",        "group":"asia",     "sectors":["Auto","IT","Metals","Energy"]},
    {"id":"HANGSENG",  "label":"Hang Seng",        "exchange":"HKEX",   "city":"Hong Kong", "x":791,"y":242,"region":"Asia",        "group":"asia",     "sectors":["Metals","Energy","Finance","IT"]},
    {"id":"SHANGHAI",  "label":"SSE Composite",    "exchange":"SSE",    "city":"Shanghai",  "x":784,"y":214,"region":"Asia",        "group":"asia",     "sectors":["Metals","Energy","Infrastructure","Auto"]},
    {"id":"SGX",       "label":"STI",              "exchange":"SGX",    "city":"Singapore", "x":773,"y":289,"region":"Asia",        "group":"asia",     "sectors":["Banking","Energy","Logistics","Finance"]},
    {"id":"KOSPI",     "label":"KOSPI",            "exchange":"KRX",    "city":"Seoul",     "x":807,"y":200,"region":"Asia",        "group":"asia",     "sectors":["IT","Auto","Metals"]},
    {"id":"ASX200",    "label":"ASX 200",          "exchange":"ASX",    "city":"Sydney",    "x":855,"y":378,"region":"Asia-Pac",    "group":"asia",     "sectors":["Metals","Mining","Energy","Banking"]},
    # ── EUROPE ──
    {"id":"FTSE100",   "label":"FTSE 100",         "exchange":"LSE",    "city":"London",    "x":433,"y":148,"region":"Europe",      "group":"europe",   "sectors":["Banking","Energy","Metals","Pharma","Finance"]},
    {"id":"DAX",       "label":"DAX 40",           "exchange":"XETRA",  "city":"Frankfurt", "x":462,"y":148,"region":"Europe",      "group":"europe",   "sectors":["Auto","IT","Metals","Engineering"]},
    {"id":"CAC40",     "label":"CAC 40",           "exchange":"Euronext","city":"Paris",    "x":447,"y":158,"region":"Europe",      "group":"europe",   "sectors":["Auto","Pharma","Banking","FMCG","Logistics"]},
    {"id":"EUROSTOXX", "label":"Euro Stoxx 50",    "exchange":"Euronext","city":"Amsterdam","x":456,"y":142,"region":"Europe",      "group":"europe",   "sectors":["Banking","Auto","Energy","IT"]},
    {"id":"SMI",       "label":"SMI Switzerland",  "exchange":"SIX",    "city":"Zurich",    "x":462,"y":158,"region":"Europe",      "group":"europe",   "sectors":["Pharma","Banking","FMCG"]},
    # ── AMERICAS ──
    {"id":"SP500",     "label":"S&P 500",          "exchange":"NYSE",   "city":"New York",  "x":213,"y":192,"region":"Americas",    "group":"americas", "sectors":["IT","Banking","Energy","Pharma","Auto","Finance"]},
    {"id":"NASDAQ",    "label":"Nasdaq 100",        "exchange":"NASDAQ", "city":"New York",  "x":217,"y":196,"region":"Americas",    "group":"americas", "sectors":["IT","Finance"]},
    {"id":"DJIA",      "label":"Dow Jones",         "exchange":"NYSE",   "city":"New York",  "x":209,"y":195,"region":"Americas",    "group":"americas", "sectors":["Banking","IT","Auto","Energy","Pharma"]},
    {"id":"TSX",       "label":"TSX Composite",    "exchange":"TSX",    "city":"Toronto",   "x":200,"y":165,"region":"Americas",    "group":"americas", "sectors":["Mining","Energy","Banking","Metals"]},
    {"id":"BOVESPA",   "label":"Bovespa",           "exchange":"B3",     "city":"São Paulo", "x":280,"y":345,"region":"Americas",    "group":"americas", "sectors":["Metals","Energy","Banking","Mining"]},
    # ── MIDDLE EAST ──
    {"id":"TADAWUL",   "label":"Tadawul",           "exchange":"Tadawul","city":"Riyadh",   "x":557,"y":248,"region":"Middle East", "group":"mideast",  "sectors":["Energy","Banking","Infrastructure"]},
    {"id":"DFMGI",     "label":"DFM Dubai",         "exchange":"DFM",    "city":"Dubai",    "x":574,"y":258,"region":"Middle East", "group":"mideast",  "sectors":["Energy","Banking","Infrastructure","Logistics"]},
    # ── AFRICA ──
    {"id":"JSE",       "label":"JSE All Share",     "exchange":"JSE",    "city":"Johannesburg","x":507,"y":368,"region":"Africa",   "group":"africa",   "sectors":["Metals","Mining","Banking","Energy"]},
    {"id":"EGX30",     "label":"EGX 30",            "exchange":"EGX",    "city":"Cairo",    "x":500,"y":235,"region":"Africa",      "group":"africa",   "sectors":["Banking","Energy","Infrastructure"]},
    # ── COMMODITY HUBS ──
    {"id":"BRENT",     "label":"Brent Crude",       "exchange":"ICE",    "city":"London/ICE","x":428,"y":138,"region":"Commodity",  "group":"commodity","sectors":["Energy","FMCG","Logistics","Auto","Cement"]},
    {"id":"WTI",       "label":"WTI Crude",         "exchange":"NYMEX",  "city":"Cushing OK","x":198,"y":200,"region":"Commodity",  "group":"commodity","sectors":["Energy","FMCG","Logistics"]},
    {"id":"LME_CU",    "label":"LME Copper",        "exchange":"LME",    "city":"London",   "x":436,"y":143,"region":"Commodity",   "group":"commodity","sectors":["Metals","Mining","Infrastructure","Engineering"]},
    {"id":"GOLD_COMEX","label":"Gold",              "exchange":"COMEX",  "city":"New York", "x":206,"y":188,"region":"Commodity",   "group":"commodity","sectors":["Banking","Finance"]},
    {"id":"DUBAI_OIL", "label":"Dubai Crude",       "exchange":"DME",    "city":"Dubai",    "x":570,"y":252,"region":"Commodity",   "group":"commodity","sectors":["Energy","Logistics"]},
    {"id":"BDI",       "label":"Baltic Dry",        "exchange":"Baltic", "city":"London",   "x":430,"y":153,"region":"Commodity",   "group":"commodity","sectors":["Logistics","Metals","FMCG","Energy"]},
    {"id":"PALM_OIL",  "label":"Palm Oil",          "exchange":"Bursa",  "city":"Kuala Lumpur","x":768,"y":285,"region":"Commodity","group":"commodity","sectors":["FMCG"]},
]

SECTORS: list[dict] = [
    {"id":"Banking",       "label":"Banking",   "icon":"🏦","color":"#38b6ff","stocks":["HDFCBANK","ICICIBANK","SBIN","KOTAKBANK","AXISBANK"]},
    {"id":"IT",            "label":"IT",        "icon":"💻","color":"#a78bfa","stocks":["TCS","INFY","HCLTECH","WIPRO","TECHM"]},
    {"id":"Energy",        "label":"Energy",    "icon":"⚡","color":"#f5a623","stocks":["RELIANCE","ONGC","BPCL","ADANIGREEN","NTPC"]},
    {"id":"Auto",          "label":"Auto",      "icon":"🚗","color":"#34d399","stocks":["MARUTI","M&M","BAJAJ-AUTO","HEROMOTOCO","EICHERMOT"]},
    {"id":"Pharma",        "label":"Pharma",    "icon":"💊","color":"#f472b6","stocks":["SUNPHARMA","DRREDDY","CIPLA","DIVISLAB","LAURUSLABS"]},
    {"id":"Metals",        "label":"Metals",    "icon":"⚙️","color":"#94a3b8","stocks":["TATASTEEL","JSWSTEEL","HINDALCO","NMDC","NATIONALUM"]},
    {"id":"FMCG",          "label":"FMCG",      "icon":"🛒","color":"#00e5a0","stocks":["HINDUNILVR","ITC","NESTLEIND","BRITANNIA","TATACONSUM"]},
    {"id":"Finance",       "label":"Finance",   "icon":"📈","color":"#22d3ee","stocks":["BAJFINANCE","JIOFIN","PFC","RECLTD","CAMS"]},
    {"id":"Infrastructure","label":"Infra",     "icon":"🏗️","color":"#fb923c","stocks":["LT","ADANIPORTS","RVNL","GPPL","ENGINERSIN"]},
    {"id":"Defence",       "label":"Defence",   "icon":"🛡️","color":"#ff4757","stocks":["HAL","MAZDOCK","BDL","ZENTEC","PARAS"]},
    {"id":"NBFC",          "label":"NBFC",      "icon":"🏛️","color":"#6366f1","stocks":["BAJFINANCE","BAJAJFINSV","SPANDANA"]},
    {"id":"Cement",        "label":"Cement",    "icon":"🏚️","color":"#d4a574","stocks":["ULTRACEMCO","GRASIM"]},
    {"id":"Mining",        "label":"Mining",    "icon":"⛏️","color":"#84cc16","stocks":["COALINDIA","NMDC","HINDCOPPER"]},
    {"id":"Logistics",     "label":"Logistics", "icon":"🚢","color":"#e879f9","stocks":["DELHIVERY","ADANIPORTS"]},
    {"id":"Utilities",     "label":"Utilities", "icon":"🔌","color":"#2dd4bf","stocks":["POWERGRID","NTPC"]},
]

COMMODITY_FLAGS: list[dict] = [
    {"commodity":"Brent Crude","symbol":"BRENT","icon":"🛢️",
     "direction":"↑ price = headwind for importers, windfall for upstream",
     "sensitive_sectors":["Energy","FMCG","Auto","Logistics","Cement"],
     "beneficiary_sectors":["Energy"],
     "note":"India imports ~85% of crude. Every $10/bbl rise costs ~₹70,000 cr/yr.",
     "correlated_stocks":["RELIANCE","ONGC","BPCL","HINDUNILVR","MARUTI"]},
    {"commodity":"LME Copper","symbol":"LME_CU","icon":"🔶",
     "direction":"↑ price = input cost rise; signals global growth",
     "sensitive_sectors":["Metals","Infrastructure","Engineering","Auto"],
     "beneficiary_sectors":["Metals","Mining"],
     "note":"India imports ~50% copper needs. Rising with EV and infra build.",
     "correlated_stocks":["HINDALCO","NMDC","HINDCOPPER","LT","BHEL"]},
    {"commodity":"Coking Coal","symbol":"COAL","icon":"⬛",
     "direction":"↑ price = steelmaker margin compression",
     "sensitive_sectors":["Metals","Cement","Energy"],
     "beneficiary_sectors":["Mining"],
     "note":"India imports ~80% coking coal from Australia. Freight amplifies impact.",
     "correlated_stocks":["TATASTEEL","JSWSTEEL","ULTRACEMCO","COALINDIA"]},
    {"commodity":"Palm Oil","symbol":"PALM_OIL","icon":"🌴",
     "direction":"↑ price = FMCG input cost headwind",
     "sensitive_sectors":["FMCG"],
     "beneficiary_sectors":[],
     "note":"India is world's largest palm oil importer. Malaysia & Indonesia supply 90%+.",
     "correlated_stocks":["HINDUNILVR","BRITANNIA","NESTLEIND","TATACONSUM"]},
    {"commodity":"USD / INR","symbol":"USDINR","icon":"💱",
     "direction":"Rupee weakens → IT & Pharma exports gain in INR terms",
     "sensitive_sectors":["IT","Pharma"],
     "beneficiary_sectors":["IT","Pharma"],
     "note":"Every ₹1 depreciation adds ~1.5–2% to IT sector revenue in INR.",
     "correlated_stocks":["TCS","INFY","SUNPHARMA","DRREDDY","WIPRO"]},
    {"commodity":"Baltic Dry Index","symbol":"BDI","icon":"🚢",
     "direction":"↑ = higher freight → import costs rise across sectors",
     "sensitive_sectors":["Logistics","Metals","FMCG","Energy"],
     "beneficiary_sectors":["Logistics"],
     "note":"Red Sea disruptions adding 12–18 days to Europe–Asia shipping routes.",
     "correlated_stocks":["DELHIVERY","ADANIPORTS","TATASTEEL","HINDUNILVR"]},
    {"commodity":"Gold","symbol":"GOLD","icon":"🥇",
     "direction":"↑ = safe-haven demand; widens current account deficit",
     "sensitive_sectors":["Banking","Finance"],
     "beneficiary_sectors":[],
     "note":"India imports 800–900 tonnes/yr. High prices widen CAD.",
     "correlated_stocks":["HDFCBANK","SBIN","BAJFINANCE"]},
]

def get_indices() -> list[dict]:         return INDICES
def get_sectors() -> list[dict]:         return SECTORS
def get_commodity_flags() -> list[dict]: return COMMODITY_FLAGS

def sectors_for_indices(index_ids: list[str]) -> list[str]:
    idx_map = {i["id"]: i for i in INDICES}
    result: set[str] = set()
    for iid in index_ids:
        if iid in idx_map:
            result.update(idx_map[iid]["sectors"])
    return sorted(result)
