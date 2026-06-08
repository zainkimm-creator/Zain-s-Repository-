"""Load paper/supplement reference data used by validation parts."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PAPER_REFERENCE_PATH = PROJECT_ROOT / "data" / "paper_reference" / "paper1_isa_supplement_parameters.json"


@lru_cache(maxsize=1)
def load_paper_reference() -> dict[str, Any]:
    return json.loads(PAPER_REFERENCE_PATH.read_text(encoding="utf-8"))


def paper_reference_path() -> str:
    return str(PAPER_REFERENCE_PATH)
