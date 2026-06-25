from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API_DIR = ROOT / "api"
sys.path.insert(0, str(API_DIR))

from fastapi.testclient import TestClient  # noqa: E402
from predictor import Predictor  # noqa: E402
from app.main import app  # noqa: E402


CASES = [
    {"home_team": "Brazil", "away_team": "Argentina", "neutral": True, "tournament": "Copa do Mundo"},
    {"home_team": "France", "away_team": "England", "neutral": True, "tournament": "Copa do Mundo"},
]


def normalized_api_response(payload: dict) -> dict:
    client = TestClient(app)
    response = client.post("/predict", json=payload)
    response.raise_for_status()
    data = response.json()
    data.pop("odds", None)
    return data


def direct_predictor_response(payload: dict) -> dict:
    predictor = Predictor(art_dir=str(API_DIR / "model_artifacts"))
    return predictor.predict(**payload)


def main() -> int:
    print("Validacao de fidelidade API x predictor.py")
    failures = 0
    for payload in CASES:
        direct = direct_predictor_response(payload)
        api = normalized_api_response(payload)
        label = f"{payload['home_team']} x {payload['away_team']}"
        if direct == api:
            print(f"[OK] {label}: respostas identicas")
        else:
            failures += 1
            print(f"[FALHA] {label}: divergencia encontrada")
            print(json.dumps({"predictor": direct, "api": api}, ensure_ascii=False, indent=2))
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
