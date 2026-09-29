"""All tunable values for SewerSense live here."""

from __future__ import annotations

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_ROOT.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE per line). Real environment variables always win."""
    if os.getenv("SEWERSENSE_SKIP_DOTENV") or not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_dotenv(PROJECT_ROOT / ".env")
DATA_DIR = Path(os.getenv("SEWERSENSE_DATA_DIR", str(BACKEND_ROOT / "data")))
DATABASE_PATH = Path(os.getenv("SEWERSENSE_DB_PATH", str(DATA_DIR / "sewersense.sqlite")))
EXTRACTION_CACHE_DIR = DATA_DIR / "extraction-cache"

CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173").split(",")
    if origin.strip()
]

HYDERABAD_LAT_RANGE = (17.25, 17.55)
HYDERABAD_LON_RANGE = (78.25, 78.65)

# --- Synthetic data -----------------------------------------------------------------------------
SIMULATION_REPORT_COUNT = 100
BASELINE_REPORT_COUNT = 300

# --- Clustering ---------------------------------------------------------------------------------
DUPLICATE_SIMILARITY_THRESHOLD = 0.80
CLUSTER_THRESHOLD = 0.55
UNLOCATED_SEMANTIC_THRESHOLD = 0.50
CLUSTER_RADIUS_M = 1_000.0
CLUSTER_TOP_K_SEMANTIC = 5
GEO_SCALE_M = 150.0
GEO_SCALE_LOCALITY_M = 400.0
# A locality-only mention could be anywhere within roughly this radius of the centroid.
LOCALITY_UNCERTAINTY_M = 350.0
GEO_ROAD_FACTOR = 0.9
TIME_SCALE_HOURS = 24.0
# Device pins further than this from the text-resolved place are ignored as unreliable.
GPS_MAX_DISAGREEMENT_M = 350.0

CLUSTER_WEIGHTS = {
    "semantic": 0.30,
    "geographic": 0.35,
    "temporal": 0.15,
    "category": 0.20,
}
COMPATIBLE_CATEGORY_SCORE = 0.6
COMPATIBLE_GROUPS = (
    frozenset({"overflow", "road_flooding", "sewage_in_house", "drain_blockage", "blockage"}),
    frozenset({"foul_smell", "blockage", "overflow"}),
    frozenset({"manhole", "overflow"}),
    frozenset({"damaged_pipeline", "overflow", "road_flooding"}),
)
CATEGORIES = (
    "overflow",
    "blockage",
    "foul_smell",
    "manhole",
    "sewage_in_house",
    "damaged_pipeline",
    "drain_blockage",
    "road_flooding",
)

# --- Corridor -----------------------------------------------------------------------------------
CORRIDOR_MIN_POINTS = 3
CORRIDOR_MIN_LENGTH_M = 30.0
CORRIDOR_MIN_EIGEN_RATIO = 3.0
CORRIDOR_WIDTH_M = 12.0
CORRIDOR_LOW_PERCENTILE = 0.10
CORRIDOR_HIGH_PERCENTILE = 0.90
MIN_RADIUS_M = 35.0
HOUSEHOLD_FRONTAGE_M = 4.0

# --- Velocity -----------------------------------------------------------------------------------
VELOCITY_BUCKETS = 6
# Below this many reports in the 6-hour window a trend is not asserted (label STEADY).
VELOCITY_MIN_WINDOW_REPORTS = 3
VELOCITY_RULES = {"rapid_ratio": 2.5, "rapid_min_recent": 6, "increasing_ratio": 1.5, "steady_ratio": 0.67}
VELOCITY_VALUES = {"RAPIDLY ESCALATING": 1.0, "INCREASING": 0.65, "STEADY": 0.3, "DECLINING": 0.1}

# --- Priority -----------------------------------------------------------------------------------
PRIORITY_WEIGHTS = {
    "Independent volume": 0.18,
    "Source diversity": 0.10,
    "Duration unresolved": 0.12,
    "Velocity": 0.15,
    "Residential impact": 0.15,
    "Road obstruction": 0.08,
    "Health risk": 0.12,
    "Sensitive location": 0.10,
}
VOLUME_SATURATION_SOURCES = 30
SOURCE_TYPE_COUNT = 6
OFFICIAL_FIELD_DIVERSITY_BOOST = 0.15
DURATION_SATURATION_HOURS = 24.0
HOUSEHOLD_SATURATION = 40
HOUSEHOLDS_PER_SOURCE = 0.8
SENSITIVE_RADIUS_M = 150.0
SEVERITY_FLOOR_MIN_SEVERITY = 4
SEVERITY_FLOOR_PRIORITY = 75
PRIORITY_BANDS = ((80, "CRITICAL"), (60, "HIGH"), (35, "MEDIUM"), (0, "LOW"))

# --- Confidence ---------------------------------------------------------------------------------
CONFIDENCE_WEIGHTS = {"diversity": 0.35, "sources": 0.25, "geo": 0.20, "corroboration": 0.20}
CONFIDENCE_SOURCE_SATURATION = 8
GEO_QUALITY_SCORES = {"exact": 1.0, "road": 0.8, "locality": 0.45, "none": 0.0}
CONFIDENCE_BANDS = ((0.7, "HIGH"), (0.45, "MEDIUM"), (0.0, "LOW"))

# --- Hybrid extraction --------------------------------------------------------------------------
EXTRACTION_MODE = os.getenv("EXTRACTION_MODE", "hybrid").lower()  # "hybrid" or "rules"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "8"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "0"))
LLM_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "1024"))
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "12"))
# Wall-clock budget for all LLM extraction in one request; unfinished reports fall back to rules.
LLM_BATCH_DEADLINE_SECONDS = float(os.getenv("LLM_BATCH_DEADLINE_SECONDS", "3.5"))
OPEN_SOURCE_LLM_ENDPOINT = os.getenv("OPEN_SOURCE_LLM_ENDPOINT", "")
OPEN_SOURCE_LLM_MODEL = os.getenv("OPEN_SOURCE_LLM_MODEL", "")
EXTRACTION_SCHEMA_VERSION = "2"
LLM_MIN_CATEGORY_CONFIDENCE = 0.7


def llm_api_key() -> str:
    """Read at call time so tests and operators can toggle the key without re-importing."""
    return os.getenv("ANTHROPIC_API_KEY", "")


def ensure_data_directories() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    EXTRACTION_CACHE_DIR.mkdir(parents=True, exist_ok=True)


# --- Live ingestion (optional; demo mode never needs these) ---------------------------------------
# Live reports go to a separate SQLite file with the same schema so real articles never merge
# into the deterministic demo incidents.
LIVE_DATABASE_PATH = Path(os.getenv("SEWERSENSE_LIVE_DB_PATH", str(DATA_DIR / "sewersense-live.sqlite")))
INGEST_MAX_TEXT_CHARS = 1200

TAVILY_API_URL = os.getenv("TAVILY_API_URL", "https://api.tavily.com/search")
TAVILY_QUERIES = [
    query.strip()
    for query in os.getenv(
        "TAVILY_QUERIES",
        "Hyderabad sewage overflow|Hyderabad sewerage complaint|Hyderabad drainage overflow|Hyderabad open manhole|"
        "Hyderabad sewage leak|Hyderabad nala overflow|Kukatpally sewage|Hyderabad sewer problem",
    ).split("|")
    if query.strip()
]
TAVILY_TOPIC = os.getenv("TAVILY_TOPIC", "news")
TAVILY_TIME_RANGE = os.getenv("TAVILY_TIME_RANGE", "month")  # day | week | month | year | "" for none
TAVILY_MAX_RESULTS = int(os.getenv("TAVILY_MAX_RESULTS", "5"))
TAVILY_TIMEOUT_SECONDS = float(os.getenv("TAVILY_TIMEOUT_SECONDS", "15"))

APIFY_API_BASE = os.getenv("APIFY_API_BASE", "https://api.apify.com/v2")
APIFY_ACTOR_ID = os.getenv("APIFY_ACTOR_ID", "")  # e.g. apify~google-search-scraper (no default on purpose)
APIFY_ACTOR_INPUT = os.getenv("APIFY_ACTOR_INPUT", "{}")  # JSON passed to the Actor as its input
APIFY_UNWIND = os.getenv("APIFY_UNWIND", "")  # e.g. organicResults for SERP-style Actors
APIFY_SOURCE_TYPE = os.getenv("APIFY_SOURCE_TYPE", "social")  # how Apify items are labelled in the pipeline
APIFY_MAX_ITEMS = int(os.getenv("APIFY_MAX_ITEMS", "50"))
APIFY_TIMEOUT_SECONDS = float(os.getenv("APIFY_TIMEOUT_SECONDS", "120"))


def tavily_api_key() -> str:
    return os.getenv("TAVILY_API_KEY", "")


def apify_api_token() -> str:
    return os.getenv("APIFY_API_TOKEN", "")


def apify_actor_id() -> str:
    return os.getenv("APIFY_ACTOR_ID", APIFY_ACTOR_ID)
