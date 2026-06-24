#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/confed_map.py  (#1 — Confederation Shrinkage, engenharia de dados)
=========================================================================
Mapeia cada selecao -> confederacao pela PLURALIDADE de jogos em torneios
continentais/regionais (robusto a convidados: Mexico na Copa America tem muito mais
jogos CONCACAF). Fonte: martj42 (historico completo). Friendly / WC qualification /
torneios multi-confed sao ignorados na atribuicao (nao indicam confederacao).

Depois calcula o Indice de Isolamento Phi_C (ultimos 3 anos):
    Phi_C = 1 - (jogos inter-confederacao de C) / (total de jogos de C)

Saida: api/model_artifacts/confed_map.json  {team: confed, "_phi": {C: phi}}
Local, 0 requests. Nao toca producao (so cria o artefato de apoio ao shrinkage).
"""
import sys, json, re
from pathlib import Path
from collections import defaultdict
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "cache_apifootball" / "results_martj42.csv"
OUT = ROOT / "api" / "model_artifacts" / "confed_map.json"
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# substrings (lower) que identificam a confederacao do torneio
PATTERNS = {
    "UEFA": ["uefa euro", "uefa nations", "british home", "nordic championship",
             "baltic cup", "central european international"],
    "CAF": ["african cup of nations", "african nations championship", "cecafa",
            "cosafa", "cabral", "cemac", "uniffac", "wafu", "amilcar"],
    "AFC": ["afc asian cup", "aff championship", "gulf cup", "king's cup", "merdeka",
            "saff", "eaff", "asian games", "southeast asian games", "waff", "south asian"],
    "CONCACAF": ["gold cup", "concacaf", "cfu caribbean", "uncaf", "cccf",
                 "windward islands", "caribbean cup"],
    "CONMEBOL": ["copa am"],            # Copa America
    "OFC": ["oceania nations", "south pacific games", "pacific games"],
}
# torneios que NAO indicam confederacao (todos jogam) ou multi-confed
IGNORE = ["friendly", "world cup", "confederations cup", "olympic", "island games",
          "conifa", "muratti", "arab cup", "korea cup", "kirin", "nehru"]


def confed_of_tournament(t):
    tl = str(t).lower()
    if any(ig in tl for ig in IGNORE):
        return None
    for conf, pats in PATTERNS.items():
        if any(p in tl for p in pats):
            return conf
    return None


def main():
    m = pd.read_csv(CSV, parse_dates=["date"])
    m["conf_t"] = m["tournament"].map(confed_of_tournament)

    # contagem por (time, confederacao) usando jogos confed-especificos
    cnt = defaultdict(lambda: defaultdict(int))
    sub = m.dropna(subset=["conf_t"])
    for _, r in sub.iterrows():
        cnt[r["home_team"]][r["conf_t"]] += 1
        cnt[r["away_team"]][r["conf_t"]] += 1
    team_confed = {t: max(c.items(), key=lambda x: x[1])[0] for t, c in cnt.items()}

    # Indice de isolamento Phi_C (ultimos 3 anos)
    recent = m[m["date"] >= (m["date"].max() - pd.Timedelta(days=3 * 365))].copy()
    recent["hc"] = recent["home_team"].map(team_confed)
    recent["ac"] = recent["away_team"].map(team_confed)
    rr = recent.dropna(subset=["hc", "ac"])
    phi, detail = {}, {}
    for C in PATTERNS:
        games = rr[(rr.hc == C) | (rr.ac == C)]
        inter = games[games.hc != games.ac]
        n = len(games)
        phi[C] = round(1 - len(inter) / n, 4) if n else None
        detail[C] = {"jogos_3a": int(n), "inter": int(len(inter)), "intra": int(n - len(inter))}

    out = dict(sorted(team_confed.items()))
    out["_phi"] = phi
    out["_detail"] = detail
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # relatorio
    from collections import Counter
    by = Counter(team_confed.values())
    print(f"selecoes mapeadas: {len(team_confed)}  | por confederacao: {dict(by)}")
    print("\nIndice de Isolamento Phi_C (ultimos 3 anos) — maior = mais isolado:")
    for C in sorted(phi, key=lambda x: -(phi[x] or 0)):
        d = detail[C]
        print(f"  {C:9s} Phi={phi[C]}  ({d['intra']} intra / {d['inter']} inter de {d['jogos_3a']} jogos)")
    # checagem: cobertura dos times do modelo
    meta = json.load(open(ROOT / "api/model_artifacts/meta.json", encoding="utf-8"))
    teams = meta["teams"]
    mapped = sum(1 for t in teams if t in team_confed)
    missing = [t for t in teams if t not in team_confed]
    print(f"\ntimes do modelo mapeados: {mapped}/{len(teams)}")
    if missing:
        print(f"  sem confederacao ({len(missing)}): {missing[:20]}{' ...' if len(missing)>20 else ''}")
    print(f"\nsalvo: {OUT}")


if __name__ == "__main__":
    main()
