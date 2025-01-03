import os
from enum import Enum
from pathlib import Path

from commons.utils import load_from_yml

# --- Utils and Config ---
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "outputs"

# -- conf.yml ---

CONF = load_from_yml(PROJECT_ROOT / "conf.yml")

# --- API ---
APITALLY_CLIENT_ID = os.environ.get("APITALLY_CLIENT_ID")
API_HOST = CONF.get("DZG_API_HOST", "localhost")
API_PORT = int(CONF.get("DZG_API_PORT", 8502)) or None


# --- Styling ---

EDGE_WIDTH = 3


class EdgeLabel:
    FOUND = "FOUND"
    RELATED = "IS_RELATED"
    AUTHOR = "IS_AUTHOR"
    PART_OF = "PART_OF"


class NodeColor(Enum):
    PRIMARY = "#ff673d"
    SECONDARY = "#b1e6c4"
    TERTIARY = "#dddddd"
    BACKBONE = "#dddddd"
