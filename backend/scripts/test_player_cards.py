#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/test_player_cards.py — VALIDAÇÃO do prop "Jogador a levar cartão"
========================================================================
Espelha a validação temporal do modelo de goleador (build_scorer_model.py), mas com o
alvo = jogador recebeu cartão (amarelo ou vermelho) no jogo. Mede AUC/LogLoss/ECE do
modelo vs a taxa-base, sob CV temporal expanding. Promove SÓ se ficar no padrão dos
outros modelos do site (goleador: AUC ~0.74, lift claro e consistente). A bateria EXP8
já indicou cartão de jogador fraco (~0.58, idiossincrático/árbitro) — este script
confirma sob o gate antes de decidir.

Uso: python scripts/test_player_cards.py [--scope selecao|clube]
"""
import sys, json, argparse, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss, roc_auc_score
warnings.filterwarnings("ignore")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WINS = [3, 5, 10]
FEATS = ["base_carded", "form_carded_5", "form_carded_10", "form_fouls_5",
         "minutes_base", "is_home", "pos_def", "pos_mid", "ref_strictness"]


def load_from_cache(scope="selecao"):
    from app.services import raw_cache
    pg = []
    for d in raw_cache.iter_all_raw(scope):
        if not d:
            continue
        fx = d.get("fixture") or {}
        date = (fx.get("date") or "")[:10]
        status = ((fx.get("status") or {}).get("short"))
        if status not in ("FT", "AET", "PEN"):
            continue
        teams = d.get("teams") or {}
        hid = (teams.get("home") or {}).get("id"); aid = (teams.get("away") or {}).get("id")
        ref = (fx.get("referee") or "").split(",")[0].strip()
        key = f"{date}|{hid}|{aid}"
        if not (date and d.get("players")):
            continue
        for pb in d["players"]:
            tid = (pb.get("team") or {}).get("id")
            for p in pb.get("players", []):
                pl = p.get("player") or {}
                st = (p.get("statistics") or [{}])[0]
                g = st.get("games") or {}
                mins = g.get("minutes")
                if mins is None:
                    continue
                cards = st.get("cards") or {}
                fouls = st.get("fouls") or {}
                pos = g.get("position") or ""
                pg.append(dict(
                    date=date, key=key, player_id=pl.get("id"), team_id=tid, ref=ref,
                    is_home=int(tid == hid), pos=pos, minutes=mins or 0,
                    yellow=(cards.get("yellow") or 0), red=(cards.get("red") or 0),
                    fouls=(fouls.get("committed") or 0),
                ))
    pg = pd.DataFrame(pg).dropna(subset=["player_id"]).drop_duplicates(["date", "player_id", "team_id"])
    return pg.sort_values(["player_id", "date"]).reset_index(drop=True)


def referee_strictness(pg):
    """Média de cartões/jogo do árbitro (point-in-time, shift para não vazar)."""
    permatch = pg.groupby(["date", "key", "ref"], as_index=False).agg(cards=("yellow", "sum"))
    permatch["cards"] += pg.groupby(["date", "key", "ref"], as_index=False).agg(r=("red", "sum"))["r"]
    permatch = permatch.sort_values("date")
    permatch["ref_strictness"] = permatch.groupby("ref")["cards"].transform(
        lambda s: s.shift(1).expanding(min_periods=3).mean())
    glob = permatch["cards"].mean()
    permatch["ref_strictness"] = permatch["ref_strictness"].fillna(glob)
    return permatch.set_index("key")["ref_strictness"].to_dict(), glob


def build_features(pg):
    pg = pg[pg["minutes"] >= 1].copy()
    pg["carded"] = ((pg["yellow"] + pg["red"]) > 0).astype(int)
    gc = pg["carded"].mean()
    refmap, glob_ref = referee_strictness(pg)
    parts = []
    for pid, g in pg.groupby("player_id", sort=False):
        g = g.sort_values("date"); npri = np.arange(len(g))
        cc = g["carded"].shift(1).cumsum().fillna(0).values
        d = {"idx": g.index, "n_prior": npri,
             "base_carded": (cc + 5 * gc) / (npri + 5),
             "minutes_base": g["minutes"].shift(1).rolling(5, min_periods=1).mean().values,
             "form_fouls_5": g["fouls"].shift(1).rolling(5, min_periods=1).mean().values}
        for w in WINS:
            d[f"form_carded_{w}"] = g["carded"].shift(1).rolling(w, min_periods=1).mean().values
        parts.append(pd.DataFrame(d).set_index("idx"))
    F = pd.concat(parts).sort_index()
    for c in F.columns:
        pg[c] = F[c]
    pg["pos_def"] = (pg["pos"] == "D").astype(int)
    pg["pos_mid"] = (pg["pos"] == "M").astype(int)
    pg["ref_strictness"] = [refmap.get(k, glob_ref) for k in pg["key"]]
    pg["form_fouls_5"] = pg["form_fouls_5"].fillna(pg["fouls"].mean())
    return pg.dropna(subset=FEATS + ["carded"]).reset_index(drop=True), gc


def temporal_validation(df):
    d = df[df["n_prior"] >= 3].sort_values("date").reset_index(drop=True)
    cuts = np.linspace(0.5, 0.85, 4); res = []
    for c in cuts:
        n = int(len(d) * c); m = int(len(d) * min(c + 0.15, 1.0))
        tr, te = d.iloc[:n], d.iloc[n:m]
        if len(te) < 300:
            continue
        clf = HistGradientBoostingClassifier(max_iter=200, max_depth=3, learning_rate=0.05, random_state=42)
        clf.fit(tr[FEATS], tr["carded"])
        p = clf.predict_proba(te[FEATS])[:, 1]
        pbase = te["base_carded"].clip(1e-4, 1 - 1e-4).values
        edges = np.linspace(0, 1, 11); ece = 0.0
        for b in range(10):
            mk = (p >= edges[b]) & (p < edges[b + 1])
            if mk.mean() > 0:
                ece += mk.mean() * abs(te["carded"].values[mk].mean() - p[mk].mean())
        res.append(dict(fold=round(c, 2), n=len(te),
                        auc_base=roc_auc_score(te["carded"], pbase), auc_model=roc_auc_score(te["carded"], p),
                        ll_base=log_loss(te["carded"], pbase, labels=[0, 1]),
                        ll_model=log_loss(te["carded"], p, labels=[0, 1]), ece=ece))
    return pd.DataFrame(res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["selecao", "clube"], default="selecao")
    a = ap.parse_args()
    print(f"Carregando cache (scope={a.scope})...", flush=True)
    pg = load_from_cache(a.scope)
    df, gc = build_features(pg)
    print(f"player-games: {len(df)} | levou cartao={df.carded.mean():.3f} | jogadores={df.player_id.nunique()}", flush=True)
    print("\n=== VALIDACAO TEMPORAL (jogador a levar cartao: modelo vs taxa-base) ===", flush=True)
    R = temporal_validation(df)
    print(R.round(4).to_string(index=False), flush=True)
    dauc = (R.auc_model - R.auc_base).mean()
    print(f"\n  >> AUC base {R.auc_base.mean():.3f} -> modelo {R.auc_model.mean():.3f} ({dauc:+.3f}) "
          f"| LogLoss {R.ll_base.mean():.4f} -> {R.ll_model.mean():.4f} | ECE {R.ece.mean()*100:.2f}%", flush=True)
    # Padrão do site: goleador tem AUC ~0.74 e lift consistente. Gate simples aqui.
    ok = R.auc_model.mean() >= 0.68 and dauc >= 0.02 and int((R.auc_model > R.auc_base).sum()) >= len(R) - 1
    print(f"  >> VEREDITO (padrao do site, ~goleador): {'PROMOVER' if ok else 'NAO PROMOVER (abaixo do padrao)'}", flush=True)


if __name__ == "__main__":
    main()
