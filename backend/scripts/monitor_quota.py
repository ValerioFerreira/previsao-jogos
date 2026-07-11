#!/usr/bin/env python3
"""
Monitor da quota diaria: le os logs de prefetch e mostra progresso em tempo real.

Uso:
  python scripts/monitor_quota.py                    # acompanha em time
  python scripts/monitor_quota.py --static          # snapshot unico
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta

def parse_log(logfile: str) -> dict:
    """Extrai ultima execução e seu estado."""
    if not os.path.exists(logfile):
        return {"status": "nao_encontrado", "calls": 0, "remaining": None, "parou": None, "timestamp": None}

    lines = Path(logfile).read_text(encoding="utf-8").splitlines()

    state = {"status": None, "calls": 0, "remaining": None, "parou": None, "timestamp": None}

    for line in reversed(lines):
        # ">> Prefetch: 4889 novos | ... | 5705 chamadas | cota ~69156 | parou por: FIM"
        if ">>" in line and "chamadas" in line:
            state["status"] = "completo"
            m = re.search(r"(\d+)\s+chamadas", line); state["calls"] = int(m.group(1)) if m else 0
            m = re.search(r"cota ~(\d+)", line); state["remaining"] = int(m.group(1)) if m else None
            m = re.search(r"parou por: ([^\n]+)", line); state["parou"] = m.group(1).strip() if m else None

        # Timestamp: "===== Sun 07/13/2026 18:45:29.12 ====="
        if "=====" in line and ("/202" in line or datetime.now().year == 2026):
            try:
                # Tenta parse de multiplos formatos
                ts = line.replace("=", "").strip()
                state["timestamp"] = ts
            except:
                pass

    if state["status"] is None:
        state["status"] = "em_progresso"

    return state

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--static", action="store_true", help="snapshot unico (nao loop)")
    ap.add_argument("--interval", type=int, default=5, help="segundos entre atualizacoes")
    args = ap.parse_args()

    logdir = Path("data/state")
    logdir.mkdir(parents=True, exist_ok=True)

    wc_log = logdir / "prefetch_wc.log"
    clubs_log = logdir / "prefetch_clubs.log"

    print("\n" + "="*80)
    print("MONITOR DE QUOTA DIARIA - API Football")
    print("="*80)

    while True:
        wc = parse_log(str(wc_log))
        clubs = parse_log(str(clubs_log))

        total_calls = wc["calls"] + clubs["calls"]
        remaining = clubs["remaining"] if clubs["remaining"] is not None else wc["remaining"]
        used = 75000 - (remaining if remaining else 0)

        # Layout
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}]")
        print(f"├─ WC:    {wc['calls']:>6} chamadas | cota ~{wc['remaining'] or '?':>6} | {wc['status']}")
        print(f"├─ Clubes: {clubs['calls']:>6} chamadas | cota ~{clubs['remaining'] or '?':>6} | {clubs['status']}")
        print(f"├─ TOTAL: {total_calls:>6} / 75000 chamadas ({100*total_calls//75000}%)")
        print(f"└─ Restam: ~{remaining or '?':>6} requisições ({100*(remaining or 0)//75000}% da cota)")

        if used >= 75000:
            print(f"\n✅ QUOTA COMPLETA! Usado: {used} requisições")
            break

        if args.static:
            break

        print(f"   [próxima atualização em {args.interval}s... Ctrl+C para sair]", end="", flush=True)
        time.sleep(args.interval)
        print("\r" + " "*60 + "\r", end="", flush=True)

if __name__ == "__main__":
    main()
