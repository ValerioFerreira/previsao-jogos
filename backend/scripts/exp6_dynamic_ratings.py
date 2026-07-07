#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/exp6_dynamic_ratings.py  —  EXPERIMENTO 1: Ratings Dinâmicos (DC evolutivo)
==================================================================================
Hipótese: o Elo pré-jogo + médias rolantes estáticas são um indicador DEFASADO da
força de seleções. Modelamos ataque(att_i) e defesa(def_i) de cada seleção como
variáveis latentes que EVOLUEM continuamente, atualizadas por gradiente (estilo Kalman/
online) após cada partida — em vez de features rolantes num GBM.

Modelo (Dixon-Coles dinâmico):
  λ_home = exp(mu + hfa*(1-neutral) + att[h] - def[a])
  λ_away = exp(mu +                    att[a] - def[h])
  P(x,y) = Pois(λ_home)(x) · Pois(λ_away)(y) · τ_DC(x,y; rho)   (correção placar baixo)
Atualização online (gradiente da log-verossimilhança Poisson), point-in-time (prevê ANTES
de ver o placar) e cronológica (evolução no tempo), com reversão à média (decay κ):
  att[h] += η·(y_h - λ_h);  def[a] += η·(λ_h - y_h)   (idem para o outro lado)
  att[i] *= (1-κ);          def[i] *= (1-κ)            (mean-reversion a cada update)

Gate (§6): CV temporal expanding, reduzir Log-loss do RESULTADO sem piorar ECE vs o
DixonColes-NB de PRODUÇÃO, consistente em folds/segmentos. Métricas: LogLoss, ECE, Brier.
Saída: docs/EXP6_RATINGS_DINAMICOS.md (gerado por scripts/report parte manual) + console.
"""
import sys, json, warnings
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import poisson
from sklearn.metrics import log_loss, brier_score_loss
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CSV = ROOT / "international_features_enriched_apifootball.csv"
META = json.load(open(ROOT / "model_artifacts" / "meta.json", encoding="utf-8"))
BASE = [f for f in META["base_feats"]]
CLASSES = ["A", "D", "H"]
MAXG = 10


def dc_tau(x, y, lh, la, rho):
    if x == 0 and y == 0: return 1 - lh * la * rho
    if x == 0 and y == 1: return 1 + lh * rho
    if x == 1 and y == 0: return 1 + la * rho
    if x == 1 and y == 1: return 1 - rho
    return 1.0


def joint_matrix(lh, la, rho):
    px = poisson.pmf(np.arange(MAXG + 1), lh)
    py = poisson.pmf(np.arange(MAXG + 1), la)
    M = np.outer(px, py)
    for x in (0, 1):
        for y in (0, 1):
            M[x, y] *= dc_tau(x, y, lh, la, rho)
    return M / M.sum()


def result_from_matrix(M):
    H = np.tril(M, -1).sum(); A = np.triu(M, 1).sum(); D = np.trace(M)
    s = H + A + D
    return np.array([A / s, D / s, H / s])  # [A,D,H]


def run_dynamic(df, eta, kappa, rho, hfa, mu, burn_frac=0.0):
    """Passa cronologicamente; devolve DataFrame com P[A,D,H], total-goals dist e y."""
    att, dff = {}, {}
    preds = []
    for _, r in df.iterrows():
        h, a = r["home_team"], r["away_team"]
        ah, dh = att.get(h, 0.0), dff.get(h, 0.0)
        aa, da = att.get(a, 0.0), dff.get(a, 0.0)
        neu = int(r.get("neutral", 0) or 0)
        lh = np.exp(mu + hfa * (1 - neu) + ah - da)
        la = np.exp(mu + aa - dh)
        lh = min(max(lh, 0.05), MAXG); la = min(max(la, 0.05), MAXG)
        M = joint_matrix(lh, la, rho)
        P = result_from_matrix(M)
        tot = np.array([np.fliplr(M).diagonal(offset=MAXG - k).sum() for k in range(2 * MAXG + 1)])  # dist total
        preds.append((P, tot, lh, la, ah, dh, aa, da))  # ratings pré-jogo (point-in-time)
        # update online
        yh, ya = int(r["home_score"]), int(r["away_score"])
        att[h] = ah + eta * (yh - lh); dff[a] = da + eta * (lh - yh)
        att[a] = aa + eta * (ya - la); dff[h] = dh + eta * (la - ya)
        for t in (h, a):
            att[t] *= (1 - kappa); dff[t] *= (1 - kappa)
    out = df.copy()
    out["Pdyn"] = [p[0] for p in preds]
    out["totdyn"] = [p[1] for p in preds]
    out["dyn_att_h"] = [p[4] for p in preds]; out["dyn_def_h"] = [p[5] for p in preds]
    out["dyn_att_a"] = [p[6] for p in preds]; out["dyn_def_a"] = [p[7] for p in preds]
    out["dyn_sup"] = out["dyn_att_h"] - out["dyn_def_a"] - (out["dyn_att_a"] - out["dyn_def_h"])
    return out


def ece_mc(y, P, nb=10):
    edges = np.linspace(0, 1, nb + 1); vals = []
    for i in range(3):
        yb = (np.asarray(y) == CLASSES[i]).astype(float); pb = P[:, i]; e = 0.0
        for b in range(nb):
            mk = (pb >= edges[b]) & (pb < edges[b + 1])
            if mk.mean() > 0: e += mk.mean() * abs(yb[mk].mean() - pb[mk].mean())
        vals.append(e)
    return float(np.mean(vals))


def brier_mc(y, P):
    Y = np.array([[1.0 if c == yi else 0.0 for c in CLASSES] for yi in y])
    return float(np.mean(np.sum((P - Y) ** 2, axis=1)))


def main():
    df = pd.read_csv(CSV, parse_dates=["date"], low_memory=False)
    df = df.dropna(subset=["home_score", "away_score"]).sort_values("date").reset_index(drop=True)
    df["result"] = np.where(df.home_score > df.away_score, "H", np.where(df.home_score == df.away_score, "D", "A"))
    df["absdiff"] = (df["home_elo_pre"] - df["away_elo_pre"]).abs()
    # baseline global (mu, hfa) a partir de todo o histórico (constantes; não é leakage forte)
    mu = np.log(max(df[["home_score", "away_score"]].mean().mean(), 0.5))
    hfa = np.log(max(df.home_score.mean(), 0.3)) - np.log(max(df.away_score.mean(), 0.3))
    print(f"N={len(df)} | mu={mu:.3f} hfa={hfa:.3f}", flush=True)

    # seleção de hiperparâmetros num split de validação (treino<=0.6, val 0.6-0.7)
    from dixon_coles_model import DixonColesNBRegressor
    best = None
    for eta in (0.03, 0.06, 0.10):
        for kappa in (0.0, 0.01, 0.02):
            out = run_dynamic(df, eta, kappa, rho=-0.05, hfa=hfa, mu=mu)
            v = out.iloc[int(len(df) * 0.6):int(len(df) * 0.7)]
            if len(v) < 100: continue
            P = np.vstack(v["Pdyn"].values); P = np.clip(P, 1e-6, 1); P = P / P.sum(1, keepdims=True)
            ll = log_loss(v["result"].values, P, labels=CLASSES)
            if best is None or ll < best[0]: best = (ll, eta, kappa, out)
    _, eta, kappa, out = best
    print(f">> hiperparâmetros: eta={eta} kappa={kappa} (val LL={best[0]:.4f})", flush=True)

    # === CV temporal expanding: dinâmico vs PRODUÇÃO (DC-NB) ===
    cuts = np.linspace(0.5, 0.85, 4); rows = []
    base_in = [c for c in BASE if c in df.columns]
    for c in cuts:
        n = int(len(df) * c); m = int(len(df) * min(c + 0.15, 1.0))
        tr, te = df.iloc[:n], df.iloc[n:m]
        if len(te) < 40: continue
        # produção: treina DC-NB no passado, prevê no bloco
        dc = DixonColesNBRegressor(); dc.fit(tr[base_in], tr.home_score.astype(int).values, tr.away_score.astype(int).values)
        Pprod = dc.predict_proba_markets(te[base_in])["result"]; Pprod = Pprod / Pprod.sum(1, keepdims=True)
        # dinâmico: já computado point-in-time em `out`
        Pdyn = np.vstack(out.iloc[n:m]["Pdyn"].values); Pdyn = np.clip(Pdyn, 1e-6, 1); Pdyn = Pdyn / Pdyn.sum(1, keepdims=True)
        yte = te["result"].values
        rows.append(dict(fold=round(c, 2), n=len(te),
                         prod_ll=log_loss(yte, Pprod, labels=CLASSES), dyn_ll=log_loss(yte, Pdyn, labels=CLASSES),
                         prod_ece=ece_mc(yte, Pprod), dyn_ece=ece_mc(yte, Pdyn),
                         prod_brier=brier_mc(yte, Pprod), dyn_brier=brier_mc(yte, Pdyn)))
    R = pd.DataFrame(rows)
    print("\n=== RESULTADO (dinâmico vs produção DC-NB) ===")
    print(R.to_string(index=False))
    dll = (R.dyn_ll - R.prod_ll).mean(); dece = (R.dyn_ece - R.prod_ece).mean()
    print(f"\n>> dLL medio {dll:+.4f} (dyn melhora {int((R.dyn_ll<R.prod_ll).sum())}/{len(R)}) | "
          f"dECE {dece*100:+.2f}% | dBrier {(R.dyn_brier-R.prod_brier).mean():+.4f}")
    verdict = "APROVADO" if (dll < 0 and int((R.dyn_ll < R.prod_ll).sum()) >= len(R) - 1 and dece <= 0.002) else "REPROVADO"
    print(f">> VEREDITO (ratings dinâmicos PUROS): {verdict}")

    # === Variante: ratings dinâmicos como FEATURES no DC-NB (base vs base+dyn) ===
    dyn_feats = ["dyn_att_h", "dyn_def_h", "dyn_att_a", "dyn_def_a", "dyn_sup"]
    rows2 = []
    for c in cuts:
        n = int(len(df) * c); m = int(len(df) * min(c + 0.15, 1.0))
        tr, te = out.iloc[:n], out.iloc[n:m]
        if len(te) < 40: continue
        yh = tr.home_score.astype(int).values; ya = tr.away_score.astype(int).values; yte = te["result"].values
        db = DixonColesNBRegressor(); db.fit(tr[base_in], yh, ya)
        Pb = db.predict_proba_markets(te[base_in])["result"]; Pb = Pb / Pb.sum(1, keepdims=True)
        dx = DixonColesNBRegressor(); dx.fit(tr[base_in + dyn_feats], yh, ya)
        Px = dx.predict_proba_markets(te[base_in + dyn_feats])["result"]; Px = Px / Px.sum(1, keepdims=True)
        rows2.append(dict(fold=round(c, 2), base_ll=log_loss(yte, Pb, labels=CLASSES), x_ll=log_loss(yte, Px, labels=CLASSES),
                          base_ece=ece_mc(yte, Pb), x_ece=ece_mc(yte, Px)))
    R2 = pd.DataFrame(rows2)
    print("\n=== Variante: dyn como FEATURES no DC (base vs base+dyn) ===")
    print(R2.to_string(index=False))
    d2 = (R2.x_ll - R2.base_ll).mean(); e2 = (R2.x_ece - R2.base_ece).mean()
    v2 = "APROVADO" if (d2 < 0 and int((R2.x_ll < R2.base_ll).sum()) >= len(R2) - 1 and e2 <= 0.002) else "REPROVADO"
    print(f">> dLL {d2:+.4f} (melhora {int((R2.x_ll<R2.base_ll).sum())}/{len(R2)}) | dECE {e2*100:+.2f}% | VEREDITO (dyn como feature): {v2}")
    (ROOT / "data" / "reports").mkdir(parents=True, exist_ok=True)
    R.to_csv(ROOT / "data" / "reports" / "exp6_dynamic_ratings.csv", index=False)
    R2.to_csv(ROOT / "data" / "reports" / "exp6_dynamic_features.csv", index=False)


if __name__ == "__main__":
    main()
