from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.validation.studies import logging_rate_study


if __name__ == "__main__":
    print(logging_rate_study())
