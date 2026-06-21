#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Motor de inferencia. Carrega os modelos e expoe predict(...) -> dict."""
import os, json
import numpy as np, pandas as pd
import joblib

try:
    from dixon_coles_model import DixonColesNBRegressor
except ImportError:
    from api.dixon_coles_model import DixonColesNBRegressor

try:
    from corners_nb_model import CornersNB
except ImportError:
    from api.corners_nb_model import CornersNB

ART = "model_artifacts"
HOME_ADV_ELO = 65.0

# Linhas over/under expostas para escanteios (mandante, visitante e total).
# Saem todas da CDF da NB; a UI só escolhe qual exibir, sem recalcular nada.
CORNER_LINES = [5.5, 6.5, 7.5, 8.5, 9.5, 10.5]


def _clamp_p(p):
    return min(0.999, max(0.001, float(p)))


def _fair_odd(p):
    return round(1.0 / _clamp_p(p), 2)


class Predictor:
    def __init__(self, art_dir=ART):
        self.clf = joblib.load(f"{art_dir}/clf_result.joblib")
        self.clf_btts = joblib.load(f"{art_dir}/clf_btts.joblib")
        self.clf_over = joblib.load(f"{art_dir}/clf_over25.joblib")
        self.qm = joblib.load(f"{art_dir}/quantile_models.joblib")
        self.dc = DixonColesNBRegressor.load(f"{art_dir}/dixon_coles_goals.joblib")
        self.corners = CornersNB.load(f"{art_dir}/corners_nb.joblib")
        with open(f"{art_dir}/meta.json", encoding="utf-8") as f:
            self.meta = json.load(f)
        # historico de confrontos (h2h)
        self.results = pd.read_csv(f"{art_dir}/results_slim.csv", parse_dates=["date"])
        self.anchor_date = self.results["date"].max()

    # ----------------------------------------------------------------- helpers de UI
    def teams(self): return self.meta["teams"]
    def team_defaults(self, team): return self.meta["snapshot"].get(team, {})
    def bases(self): return self.meta["bases"]

    # ----------------------------------------------------------------- confronto direto
    def head_to_head(self, home_team, away_team):
        r = self.results
        m = r[((r.home_team == home_team) & (r.away_team == away_team)) |
              ((r.home_team == away_team) & (r.away_team == home_team))]
        if len(m) == 0:
            return {"h2h_played": 0, "h2h_home_winrate": np.nan,
                    "h2h_home_gd_mean": np.nan, "days_since_last_h2h": np.nan,
                    "_resumo": "Sem confrontos anteriores no histórico."}
        wins = gds = 0
        for _, x in m.iterrows():
            gd = (x.home_score - x.away_score) if x.home_team == home_team else (x.away_score - x.home_score)
            gds += gd; wins += 1 if gd > 0 else 0
        n = len(m)
        last = m["date"].max()
        # vitorias do mandante atual, empates, vitorias do visitante atual
        h = sum(1 for _, x in m.iterrows()
                if ((x.home_score - x.away_score) if x.home_team == home_team
                    else (x.away_score - x.home_score)) > 0)
        d = sum(1 for _, x in m.iterrows() if x.home_score == x.away_score)
        a = n - h - d
        return {"h2h_played": n, "h2h_home_winrate": wins / n,
                "h2h_home_gd_mean": gds / n,
                "days_since_last_h2h": float((self.anchor_date - last).days),
                "_resumo": f"{n} jogos · {home_team} {h}V · {d}E · {away_team} {a}V"}

    # ----------------------------------------------------------------- montagem da linha
    def build_row(self, home_team, away_team, neutral, tournament,
                  home_vals=None, away_vals=None, context_overrides=None, h2h_overrides=None):
        snap_h = {**self.team_defaults(home_team), **dict(home_vals or {})}
        snap_a = {**self.team_defaults(away_team), **dict(away_vals or {})}
        row = {c: np.nan for c in self.meta["full_feats"]}

        for b in self.meta["bases"]:
            hv, av = snap_h.get(b, np.nan), snap_a.get(b, np.nan)
            if f"home_{b}" in row: row[f"home_{b}"] = hv
            if f"away_{b}" in row: row[f"away_{b}"] = av
            if f"diff_{b}" in row and pd.notna(hv) and pd.notna(av):
                row[f"diff_{b}"] = hv - av

        he, ae = snap_h.get("elo_pre", np.nan), snap_a.get("elo_pre", np.nan)
        if "home_elo_pre" in row: row["home_elo_pre"] = he
        if "away_elo_pre" in row: row["away_elo_pre"] = ae
        if pd.notna(he) and pd.notna(ae):
            if "elo_diff" in row: row["elo_diff"] = he - ae
            adv = 0.0 if neutral else HOME_ADV_ELO
            if "elo_home_winprob" in row:
                row["elo_home_winprob"] = 1.0 / (1.0 + 10 ** ((ae - (he + adv)) / 400.0))

        # confronto direto (automatico, salvo override)
        h2h = self.head_to_head(home_team, away_team)
        h2h = {**h2h, **dict(h2h_overrides or {})}
        for k in ("h2h_played", "h2h_home_winrate", "h2h_home_gd_mean", "days_since_last_h2h"):
            if k in row and pd.notna(h2h.get(k, np.nan)): row[k] = h2h[k]

        w = self.meta["tournament_weights"].get(tournament, 0.40)
        ctx = {"neutral": int(bool(neutral)), "real_home_advantage": 0 if neutral else 1,
               "tournament_weight": w, "is_friendly": int(tournament == "Amistoso"),
               "is_qualification": int(tournament == "Eliminatórias"),
               "is_major_final": int(tournament in ("Copa América / Euro / Copa Africana", "Copa do Mundo")),
               "is_competitive": int(tournament != "Amistoso")}
        for k, v in ctx.items():
            if k in row: row[k] = v
        for k, v in (context_overrides or {}).items():
            if k in row: row[k] = v
        return pd.DataFrame([row]), h2h

    # ----------------------------------------------------------------- regressao quantilica
    def _quantile(self, target, X, feats):
        m = self.qm[target]
        lo = float(m[0.1].predict(X[feats])[0])
        mid = float(m[0.5].predict(X[feats])[0])
        hi = float(m[0.9].predict(X[feats])[0])
        lo, mid, hi = max(0.0, lo), max(0.0, mid), max(0.0, hi)
        lo, hi = min(lo, mid, hi), max(lo, mid, hi)   # evita cruzamento de quantis
        return mid, lo, hi

    @staticmethod
    def _conf_label(point, lo, hi):
        if point <= 0: return "Baixa"
        rel = (hi - lo) / max(point, 1e-6)
        return "Alta" if rel < 0.55 else ("Média" if rel < 1.0 else "Baixa")

    def _num(self, target, X, feats):
        p, lo, hi = self._quantile(target, X, feats)
        return {"estimativa": round(p, 1), "intervalo": [round(lo, 1), round(hi, 1)],
                "confianca": self._conf_label(p, lo, hi)}

    def _corners_market(self, pmf):
        """Monta a saída de um mercado de escanteios a partir da PMF da NB.

        Expõe: estimativa pontual + intervalo 80% (compat), a distribuição/CDF
        completa (fonte de verdade), e prob/odd-justa das linhas O/U (conveniência
        para a UI). Tudo derivado da mesma distribuição — cortes diferentes da CDF.
        """
        pmf = np.asarray(pmf, dtype=float)
        k = np.arange(len(pmf))
        est = float(np.sum(pmf * k))
        cdf = np.cumsum(pmf)
        q10 = float(np.searchsorted(cdf, 0.1))
        q90 = float(np.searchsorted(cdf, 0.9))
        linhas = {}
        for L in CORNER_LINES:
            over = float(pmf[int(L) + 1:].sum())   # P(contagem >= L+1), L é x.5
            under = 1.0 - over
            linhas[str(L)] = {
                "over":  {"prob": round(100 * over, 1),  "odd_justa": _fair_odd(over)},
                "under": {"prob": round(100 * under, 1), "odd_justa": _fair_odd(under)},
            }
        return {
            "estimativa": round(est, 1),
            "intervalo": [round(q10, 1), round(q90, 1)],
            "confianca": self._conf_label(est, q10, q90),
            "distribuicao": [round(float(x), 6) for x in pmf],
            "linhas": linhas,
        }

    @staticmethod
    def _binary(pipe, X, feats, pos_label, yes_txt, no_txt):
        proba = pipe.predict_proba(X[feats])[0]
        cls = list(pipe.classes_)
        p_yes = float(proba[cls.index(pos_label)]) if pos_label in cls else float(proba.max())
        resp = yes_txt if p_yes >= 0.5 else no_txt
        conf = round(100 * (p_yes if p_yes >= 0.5 else 1 - p_yes), 1)
        return {"resposta": resp, "confianca": conf, "prob_sim": round(100 * p_yes, 1)}

    # ----------------------------------------------------------------- previsao completa
    def predict(self, home_team, away_team, neutral=False, tournament="Amistoso",
                home_vals=None, away_vals=None, context_overrides=None, h2h_overrides=None):
        X, h2h = self.build_row(home_team, away_team, neutral, tournament,
                                home_vals, away_vals, context_overrides, h2h_overrides)
        bf, ff = self.meta["base_feats"], self.meta["full_feats"]

        # vencedor, gols, ambas_marcam, over_2_5 via Dixon-Coles
        dc_probs = self.dc.predict_proba_markets(X[bf])
        prob_res = dc_probs["result"][0]  # shape (3,) -> [A, D, H]
        pm = {"A": prob_res[0], "D": prob_res[1], "H": prob_res[2]}
        label_map = {"H": home_team, "A": away_team, "D": "Empate"}
        wk = max(pm, key=pm.get)
        winner = {"vencedor": label_map[wk], "confianca": float(round(100 * pm[wk], 1)),
                  "probabilidades": {home_team: float(round(100 * pm.get("H", 0), 1)),
                                     "Empate": float(round(100 * pm.get("D", 0), 1)),
                                     away_team: float(round(100 * pm.get("A", 0), 1))}}

        # BTTS
        p_btts = float(dc_probs["btts"][0])
        resp_btts = "Sim" if p_btts >= 0.5 else "Não"
        conf_btts = round(100 * (p_btts if p_btts >= 0.5 else 1 - p_btts), 1)
        btts_res = {"resposta": resp_btts, "confianca": conf_btts, "prob_sim": round(100 * p_btts, 1)}

        # Over 2.5
        p_over = float(dc_probs["over_2_5"][0])
        resp_over = "Mais de 2,5" if p_over >= 0.5 else "Menos de 2,5"
        conf_over = round(100 * (p_over if p_over >= 0.5 else 1 - p_over), 1)
        over_res = {"resposta": resp_over, "confianca": conf_over, "prob_sim": round(100 * p_over, 1)}

        # Gols (Total de Gols - Estimativa pontual, intervalo de 80%, confiança)
        P_joint_single = dc_probs["joint"][0]
        prob_total_goals = np.zeros(self.dc.max_goals + 1)
        for x in range(self.dc.max_goals + 1):
            for y in range(self.dc.max_goals + 1):
                if x + y <= self.dc.max_goals:
                    prob_total_goals[x + y] += P_joint_single[x, y]
        prob_total_goals /= prob_total_goals.sum()

        expected_goals = np.sum(prob_total_goals * np.arange(self.dc.max_goals + 1))
        cdf = np.cumsum(prob_total_goals)
        q10 = float(np.searchsorted(cdf, 0.1))
        q90 = float(np.searchsorted(cdf, 0.9))

        rel = (q90 - q10) / max(expected_goals, 1e-6)
        conf_label = "Alta" if rel < 0.55 else ("Média" if rel < 1.0 else "Baixa")
        gols_res = {
            "estimativa": round(expected_goals, 1),
            "intervalo": [round(q10, 1), round(q90, 1)],
            "confianca": conf_label
        }

        # Escanteios via NB independente (CDF real; total por convolução)
        cd = self.corners.predict_distributions(X)

        return {
            "vencedor": winner,
            "gols": gols_res,
            "chutes": self._num("total_shots", X, ff),
            "escanteios": {home_team: self._corners_market(cd["home"][0]),
                           away_team: self._corners_market(cd["away"][0]),
                           "total": self._corners_market(cd["total"][0])},
            "ambas_marcam": btts_res,
            "over_2_5": over_res,
            "confronto_direto": h2h["_resumo"],
        }


if __name__ == "__main__":
    import pprint
    art_path = "api/model_artifacts" if os.path.exists("api/model_artifacts") else "model_artifacts"
    p = Predictor(art_path)
    print("Seleções:", len(p.teams()))
    pprint.pprint(p.predict("Brazil", "Argentina", neutral=True, tournament="Copa do Mundo"))
