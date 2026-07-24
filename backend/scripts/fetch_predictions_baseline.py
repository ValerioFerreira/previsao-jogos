#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/fetch_predictions_baseline.py
======================================
Coleta em ESCALA (8117 fixtures) do endpoint `/predictions` da api-football,
pra comparar contra o nosso modelo (Dixon-Coles NB) — ver
`scripts/adhoc_compare_apifootball_predictions.py` pro cálculo das métricas.

Extrai o padrão do piloto (`tier3_exploratory_checks.py::check2_predictions_baseline`,
n=40) e troca o `time.sleep(0.15)` ingênuo por `quota_tracker.throttle()`/
`note_call()` de verdade (throttle real de 380 req/min compartilhado, cota
diária rastreada via GET /status).

Fonte dos fixture_id: `data/built/backtest_predictions.parquet` (8117 jogos já
finalizados, resultado real conhecido, período 2025-01-11 a 2026-05-31).

Salva a resposta CRUA (`response[0]` inteiro) em
`data/raw/predictions_baseline/<fixture_id>.json` e um manifesto incremental
`data/raw/predictions_baseline/_manifest.jsonl` (1 linha por fixture).

IDEMPOTENTE — pula fixture já salvo, pra poder retomar depois de uma
interrupção (limite de sessão, cota, etc.).

Uso:
    python scripts/fetch_predictions_baseline.py
    python scripts/fetch_predictions_baseline.py --limit 500   # smoke test
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import httpx  # noqa: E402
import pandas as pd  # noqa: E402

from app.services.fixture_fetch import BASE, _key  # noqa: E402
from scripts import quota_tracker  # noqa: E402

PREDICTIONS_PARQUET = ROOT / "data" / "built" / "backtest_predictions.parquet"
OUT_DIR = ROOT / "data" / "raw" / "predictions_baseline"
MANIFEST = OUT_DIR / "_manifest.jsonl"

# Margem de segurança abaixo da cota diária real (75000) — deixa folga pra
# outros coletores/cron do mesmo dia, mesmo processo isolado.
QUOTA_SAFETY_MARGIN = 500


def _get(path: str, **params) -> tuple[dict, int]:
    r = httpx.get(BASE + path, headers={"x-apisports-key": _key()}, params=params, timeout=30)
    code = r.status_code
    r.raise_for_status()
    j = json.loads(r.content.decode("utf-8", errors="replace"))
    return j, code


def _append_manifest(rec: dict) -> None:
    with MANIFEST.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="processa só os N primeiros pendentes (smoke test)")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not MANIFEST.exists():
        MANIFEST.touch()

    df = pd.read_parquet(PREDICTIONS_PARQUET)
    fixture_ids = df["fixture_id"].drop_duplicates().astype(int).tolist()
    total = len(fixture_ids)
    print(f"[fetch_predictions_baseline] {total} fixture_id únicos em {PREDICTIONS_PARQUET.name}")

    pending = [fid for fid in fixture_ids if not (OUT_DIR / f"{fid}.json").exists()]
    already_done = total - len(pending)
    print(f"[fetch_predictions_baseline] {already_done} já coletados, {len(pending)} pendentes")

    if args.limit:
        pending = pending[: args.limit]
        print(f"[fetch_predictions_baseline] --limit {args.limit}: processando só {len(pending)}")

    n_ok = 0
    n_empty = 0
    n_error = 0
    t0 = time.time()

    for i, fid in enumerate(pending, start=1):
        remaining = quota_tracker.remaining()
        if remaining < QUOTA_SAFETY_MARGIN:
            print(f"[fetch_predictions_baseline] PARADO: cota restante ({remaining}) abaixo da margem "
                  f"de segurança ({QUOTA_SAFETY_MARGIN}). {len(pending) - i + 1} fixtures ainda pendentes.")
            break

        quota_tracker.throttle()
        try:
            resp, http_code = _get("/predictions", fixture=fid)
            quota_tracker.note_call()
        except httpx.HTTPStatusError as e:
            quota_tracker.note_call()
            n_error += 1
            _append_manifest({"fixture_id": fid, "status": "http_error",
                               "http_code": e.response.status_code if e.response is not None else None,
                               "error": str(e)})
            continue
        except Exception as e:
            n_error += 1
            _append_manifest({"fixture_id": fid, "status": "error", "http_code": None, "error": str(e)})
            continue

        body = resp.get("response") or []
        if not body:
            n_empty += 1
            _append_manifest({"fixture_id": fid, "status": "empty", "http_code": http_code})
            continue

        out_path = OUT_DIR / f"{fid}.json"
        out_path.write_text(json.dumps(body[0], ensure_ascii=False), encoding="utf-8")
        n_ok += 1
        _append_manifest({"fixture_id": fid, "status": "ok", "http_code": http_code})

        if i % 500 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed * 60 if elapsed > 0 else 0.0
            print(f"[fetch_predictions_baseline] {i}/{len(pending)} processados "
                  f"(ok={n_ok} empty={n_empty} error={n_error}) — {rate:.0f} req/min — "
                  f"cota restante ~{quota_tracker.remaining()}")

    elapsed = time.time() - t0
    print(f"[fetch_predictions_baseline] FIM. {n_ok} ok, {n_empty} vazios, {n_error} erros, "
          f"{elapsed:.0f}s decorridos.")
    n_saved_total = sum(1 for _ in OUT_DIR.glob("*.json"))
    print(f"[fetch_predictions_baseline] total de arquivos salvos em disco agora: {n_saved_total}/{total}")


if __name__ == "__main__":
    main()
