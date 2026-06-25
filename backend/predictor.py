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

try:
    from cards_gp_model import CardsGP
except ImportError:
    from api.cards_gp_model import CardsGP

try:
    from ortho_sinais import apply_ortho_residuals
except ImportError:
    from api.ortho_sinais import apply_ortho_residuals

try:
    from shots_nb_model import ShotsNB
except ImportError:
    from api.shots_nb_model import ShotsNB

try:
    from corner_interactions import add_corner_interactions
except ImportError:
    from api.corner_interactions import add_corner_interactions

ART = "model_artifacts"
HOME_ADV_ELO = 65.0

# Aliases: nomes que a API-Football (e jogos futuros) podem trazer diferentes do
# nome canônico usado na nossa base. Mapeia variante -> nosso nome.
TEAM_ALIASES = {
    "Czechia": "Czech Republic",
    "Türkiye": "Turkey", "Turkiye": "Turkey",
    "Côte d'Ivoire": "Ivory Coast", "Cote d'Ivoire": "Ivory Coast",
    "Korea Republic": "South Korea", "South Korea Republic": "South Korea",
    "Korea DPR": "North Korea", "DPR Korea": "North Korea",
    "USA": "United States", "United States of America": "United States",
    "IR Iran": "Iran", "Iran IR": "Iran",
    "China PR": "China",
    "Congo DR": "DR Congo", "Congo-Brazzaville": "Congo",
    "Cape Verde Islands": "Cape Verde", "Cabo Verde": "Cape Verde",
    "Ireland": "Republic of Ireland",
    "The Gambia": "Gambia",
    "St. Kitts and Nevis": "Saint Kitts and Nevis",
    "St. Lucia": "Saint Lucia",
    "St. Vincent and the Grenadines": "Saint Vincent and the Grenadines",
    "Kyrgyz Republic": "Kyrgyzstan",
    "Eswatini (Swaziland)": "Eswatini", "Swaziland": "Eswatini",
    "Hong Kong, China": "Hong Kong",
    "North Macedonia FYR": "North Macedonia", "Macedonia": "North Macedonia",
    "Brunei Darussalam": "Brunei",
    "Curacao": "Curaçao",
    "Trinidad And Tobago": "Trinidad and Tobago",
    "Chinese Taipei": "Taiwan",
}

# Linhas over/under expostas (mandante, visitante e total). Saem todas da CDF da
# NB; a UI só escolhe qual exibir, sem recalcular nada. Cada mercado tem grade
# própria conforme a magnitude da contagem (cartões baixa, chutes alta).
CORNER_LINES = [5.5, 6.5, 7.5, 8.5, 9.5, 10.5]
CARDS_LINES = [1.5, 2.5, 3.5, 4.5, 5.5, 6.5]
SHOTS_LINES = [18.5, 20.5, 22.5, 24.5, 26.5]
SHOTS_TEAM_LINES = [6.5, 8.5, 10.5, 12.5, 14.5]   # chutes por equipe (contagem menor)
SOT_LINES = [5.5, 6.5, 7.5, 8.5, 9.5, 10.5]       # chutes a gol (total)
SOT_TEAM_LINES = [2.5, 3.5, 4.5, 5.5, 6.5]        # chutes a gol por equipe
GOALS_HALF_LINES = [0.5, 1.5, 2.5, 3.5]           # gols por tempo (total)
CARDS_HALF_LINES = [1.5, 2.5, 3.5, 4.5]           # cartões por tempo (total)
GOALS_LINES = [0.5, 1.5, 2.5, 3.5, 4.5]           # gols (equipe/total, partida)


def _clamp_p(p):
    return min(0.999, max(0.001, float(p)))


def _fair_odd(p):
    return round(1.0 / _clamp_p(p), 2)


class Predictor:
    def __init__(self, art_dir=ART):
        # vencedor / BTTS / over_2_5 saem todos da matriz conjunta do Dixon-Coles
        # (ver predict()). Os classificadores legados clf_result/btts/over25 não são
        # mais servidos; os .joblib ficam em disco como legado, mas não carregamos.
        self.dc = DixonColesNBRegressor.load(f"{art_dir}/dixon_coles_goals.joblib")
        # Escanteios: modelo intermediário cascata + estilo, dispersão FIXA (r_H=10, r_A=8.5).
        # O DynamicCornersNB foi REPROVADO no gate OOS (regressão de log-loss/MAE + Tail ECE
        # Over 8.5 = 22.4% vs limite 4%) — ver POST_MORTEM_DYNAMIC_DISPERSION.md. Rollback.
        self.corners = CornersNB.load(f"{art_dir}/corners_cascade_rfixo.joblib")
        self.cards = CardsGP.load(f"{art_dir}/cards_gp.joblib")
        self.shots = ShotsNB.load(f"{art_dir}/shots_nb.joblib")
        self.shots_on_target = ShotsNB.load(f"{art_dir}/shots_on_target_nb.joblib")
        # Mercados por tempo (1º/2º) — gols e cartões (CornersNB sobre base_feats).
        self.gols_1t = CornersNB.load(f"{art_dir}/gols_1t_nb.joblib")
        self.gols_2t = CornersNB.load(f"{art_dir}/gols_2t_nb.joblib")
        self.cartoes_1t = CornersNB.load(f"{art_dir}/cartoes_1t_nb.joblib")
        self.cartoes_2t = CornersNB.load(f"{art_dir}/cartoes_2t_nb.joblib")
        self.ortho_weights = joblib.load(f"{art_dir}/style_ortho_weights.joblib")
        with open(f"{art_dir}/meta.json", encoding="utf-8") as f:
            self.meta = json.load(f)
        # Bases de box-score (sb_*): são o sinal "rico" que falta às seleções de
        # ligas/confederações com pouca cobertura. A fração presente vira o tier de
        # confiabilidade do jogo (ver _reliability).
        self._box_bases = [b for b in self.meta["bases"] if b.startswith("sb_")]
        # historico de confrontos (h2h)
        self.results = pd.read_csv(f"{art_dir}/results_slim.csv", parse_dates=["date"])
        self.anchor_date = self.results["date"].max()
        # estatísticas por jogo (placar+box-score) p/ médias do confronto direto
        try:
            self.h2h_stats = pd.read_csv(f"{art_dir}/h2h_stats.csv", parse_dates=["date"])
        except Exception:
            self.h2h_stats = None
        # base profunda de resultados (martj42 pré-2016 + api 2016+) só para o card H2H
        try:
            self.h2h_results = pd.read_csv(f"{art_dir}/h2h_results.csv", parse_dates=["date"])
        except Exception:
            self.h2h_results = None

    # ----------------------------------------------------------------- normalização de nome
    def norm_team(self, name):
        """Canoniza o nome da seleção: aplica alias e cai no nome conhecido se houver."""
        if name in self.meta["snapshot"]:
            return name
        return TEAM_ALIASES.get(name, name)

    # ----------------------------------------------------------------- helpers de UI
    def teams(self): return self.meta["teams"]
    def team_defaults(self, team): return self.meta["snapshot"].get(team, {})
    def bases(self): return self.meta["bases"]

    # ----------------------------------------------------------------- confronto direto
    def head_to_head(self, home_team, away_team):
        # usa a base profunda (martj42+api) p/ o card de confronto direto, se disponível
        r = self.h2h_results if self.h2h_results is not None else self.results
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
        
        # BTTS e Average Goals
        btts_count = sum(1 for _, x in m.iterrows() if x.home_score > 0 and x.away_score > 0)
        total_goals = sum(x.home_score + x.away_score for _, x in m.iterrows())
        btts_percentage = (btts_count / n * 100) if n > 0 else 0
        avg_total_goals = (total_goals / n) if n > 0 else 0
        
        # médias DO CONFRONTO DIRETO por equipe: gols pelo histórico completo (m);
        # chutes/chutes a gol/escanteios/cartões pelos jogos do confronto com box-score.
        hs = self.h2h_stats
        sub = None
        if hs is not None:
            sub = hs[((hs.home_team == home_team) & (hs.away_team == away_team)) |
                     ((hs.home_team == away_team) & (hs.away_team == home_team))]

        def _avgs(team):
            goals_vals = [(x.home_score if x.home_team == team else x.away_score) for _, x in m.iterrows()]
            out = {"goals": round(float(np.mean(goals_vals)), 1) if goals_vals else None,
                   "shots": None, "shots_on_target": None, "corners": None, "cards": None}
            if sub is not None and len(sub):
                for key, stat in [("shots", "shots"), ("shots_on_target", "sot"),
                                  ("corners", "corners"), ("cards", "cards")]:
                    vals = []
                    for _, x in sub.iterrows():
                        v = x[f"home_{stat}"] if x.home_team == team else x[f"away_{stat}"]
                        if pd.notna(v):
                            vals.append(float(v))
                    out[key] = round(float(np.mean(vals)), 1) if vals else None
            return out

        return {"h2h_played": n, "h2h_home_winrate": wins / n,
                "h2h_home_gd_mean": gds / n,
                "days_since_last_h2h": float((self.anchor_date - last).days),
                "btts_percentage": btts_percentage,
                "avg_total_goals": avg_total_goals,
                "home_wins": h, "draws": d, "away_wins": a,
                "last_date": str(pd.to_datetime(last).date()),
                "home_avgs": _avgs(home_team), "away_avgs": _avgs(away_team),
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

    # ----------------------------------------------------------------- confiabilidade (cobertura de dados)
    def _coverage(self, snap):
        """Fração das features de box-score (sb_*) presentes no snapshot do time."""
        if not self._box_bases:
            return 1.0
        present = sum(1 for b in self._box_bases
                      if snap.get(b) is not None
                      and not (isinstance(snap.get(b), float) and np.isnan(snap.get(b))))
        return present / len(self._box_bases)

    def _reliability(self, snap_h, snap_a):
        """Tier de confiabilidade do jogo a partir da cobertura de dados refinados.

        Um jogo é tão confiável quanto o lado com MENOS dados: seleções de ligas com
        pouca cobertura (sem box-score) caem para Baixa e dependem só de Elo+forma de
        resultado; jogos entre seleções ricas em dados ficam Alta e usam de fato as
        features refinadas (chutes, posse, estilo) que afinam escanteios/cartões/chutes.
        """
        ch, ca = self._coverage(snap_h), self._coverage(snap_a)
        score = min(ch, ca)
        tier = "Alta" if score >= 0.7 else ("Média" if score >= 0.3 else "Baixa")
        explica = {
            "Alta": "Temos bastante histórico detalhado das duas seleções, então a previsão "
                    "usa todas as informações de jogo (chutes, posse, estilo). É a nossa melhor estimativa.",
            "Média": "Temos histórico detalhado de uma das seleções, mas pouco da outra. A "
                     "previsão ainda é boa, mas com mais incerteza do que o normal.",
            "Baixa": "Uma das seleções tem pouco histórico detalhado disponível. A previsão se "
                     "apoia principalmente na força geral (ranking) e nos resultados recentes — "
                     "leia com cautela.",
        }[tier]
        return {
            "tier": tier,
            "score": round(score, 2),
            "cobertura_mandante": round(ch, 2),
            "cobertura_visitante": round(ca, 2),
            "_resumo": explica,
        }

    @staticmethod
    def _conf_label(point, lo, hi):
        if point <= 0: return "Baixa"
        rel = (hi - lo) / max(point, 1e-6)
        return "Alta" if rel < 0.55 else ("Média" if rel < 1.0 else "Baixa")

    def _corners_market(self, pmf, lines=CORNER_LINES):
        """Monta a saída de um mercado de contagem (escanteios/cartões) da PMF da NB.

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
        for L in lines:
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

    # ----------------------------------------------------------------- previsao completa
    def predict(self, home_team, away_team, neutral=False, tournament="Amistoso",
                home_vals=None, away_vals=None, context_overrides=None, h2h_overrides=None):
        home_team, away_team = self.norm_team(home_team), self.norm_team(away_team)
        X, h2h = self.build_row(home_team, away_team, neutral, tournament,
                                home_vals, away_vals, context_overrides, h2h_overrides)
        bf, ff = self.meta["base_feats"], self.meta["full_feats"]

        # confiabilidade do jogo pela cobertura de dados refinados (box-score)
        snap_h = {**self.team_defaults(home_team), **dict(home_vals or {})}
        snap_a = {**self.team_defaults(away_team), **dict(away_vals or {})}
        confiabilidade = self._reliability(snap_h, snap_a)

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
            "confianca": conf_label,
            "distribuicao": [round(float(x), 6) for x in prob_total_goals]
        }

        # Gols por equipe (marginais da matriz conjunta do Dixon-Coles)
        home_goals_pmf = np.asarray(P_joint_single).sum(axis=1)
        away_goals_pmf = np.asarray(P_joint_single).sum(axis=0)
        gols_equipe = {home_team: self._corners_market(home_goals_pmf, GOALS_LINES),
                       away_team: self._corners_market(away_goals_pmf, GOALS_LINES)}

        # Placar exato: 3 placares mais prováveis (top-3 da matriz conjunta) + um
        # alerta de POTENCIAL DE DESVIO (placar fora do padrão). O sinal é tirado do
        # próprio modelo: a "supremacia" (diferença de gols esperados entre as equipes)
        # já sintetiza Elo, forma recente e ataque-vs-defesa — tudo que alimenta os
        # lambdas do Dixon-Coles; somada à massa de cauda alta (P(4+ gols)), indica
        # quando o jogo tende a placares elásticos.
        J = np.asarray(P_joint_single, dtype=float)
        Jn = J / J.sum() if J.sum() > 0 else J
        cells = sorted(
            ((i, j, float(Jn[i, j])) for i in range(Jn.shape[0]) for j in range(Jn.shape[1])),
            key=lambda t: t[2], reverse=True,
        )
        top_placares = [{"mandante": int(i), "visitante": int(j), "prob": round(100 * p, 1)}
                        for i, j, p in cells[:3]]

        exp_home = float((np.arange(len(home_goals_pmf)) * home_goals_pmf).sum())
        exp_away = float((np.arange(len(away_goals_pmf)) * away_goals_pmf).sum())
        supremacia = abs(exp_home - exp_away)
        p4 = float(prob_total_goals[4:].sum()) if len(prob_total_goals) > 4 else 0.0
        p5 = float(prob_total_goals[5:].sum()) if len(prob_total_goals) > 5 else 0.0

        # Motivos estruturados (sem o nome cru do time): o front monta o texto em
        # PT-BR aplicando teamPt ao lado favorito (mandante/visitante).
        motivos = []
        if supremacia >= 1.3:
            motivos.append({
                "tipo": "favoritismo",
                "favorito_lado": "mandante" if exp_home >= exp_away else "visitante",
                "exp_alto": round(max(exp_home, exp_away), 1),
                "exp_baixo": round(min(exp_home, exp_away), 1),
            })
        if p4 >= 0.38:
            motivos.append({
                "tipo": "placar_alto",
                "exp_total": round(expected_goals, 1),
                "prob_4_mais": round(100 * p4),
            })
        if supremacia >= 1.8 or p5 >= 0.22 or (supremacia >= 1.3 and p4 >= 0.40):
            nivel = "alto"
        elif motivos:
            nivel = "moderado"
        else:
            nivel = "normal"

        placar_exato = {
            "top": top_placares,
            "alerta": {
                "nivel": nivel,
                "supremacia_gols": round(supremacia, 2),
                "prob_4_mais": round(100 * p4, 1),
                "exp_mandante": round(exp_home, 1),
                "exp_visitante": round(exp_away, 1),
                "motivos": motivos,
            },
        }

        # 1. Ortogonalizacao de estilo
        X_resid = apply_ortho_residuals(X, self.ortho_weights)
        
        # 2. Cascade: Predict shots first
        cs = self.shots.predict_distributions(X_resid)
        
        # 3. Inject shots prediction as active features for corners and cards
        X_resid["pred_home_shots"] = cs["lambdas"]
        X_resid["pred_away_shots"] = cs["mus"]
        
        # 4. Predict corners and cards
        X_corners = add_corner_interactions(X_resid)
        cd = self.corners.predict_distributions(X_corners)
        cc = self.cards.predict_distributions(X_resid)

        # 5. Chutes a gol (shots on target) — mesma cascata/estilo
        sot = self.shots_on_target.predict_distributions(X_resid)

        # 6. Mercados por tempo (1º/2º) — gols e cartões (mandante/visitante/total)
        def _half(model, lines):
            d = model.predict_distributions(X[bf])
            return {home_team: self._corners_market(d["home"][0], lines),
                    away_team: self._corners_market(d["away"][0], lines),
                    "total": self._corners_market(d["total"][0], lines)}
        tempos = {
            "gols_1t": _half(self.gols_1t, GOALS_HALF_LINES),
            "gols_2t": _half(self.gols_2t, GOALS_HALF_LINES),
            "cartoes_1t": _half(self.cartoes_1t, CARDS_HALF_LINES),
            "cartoes_2t": _half(self.cartoes_2t, CARDS_HALF_LINES),
        }

        return {
            "vencedor": winner,
            "gols": gols_res,
            "gols_equipe": gols_equipe,
            "chutes": self._corners_market(cs["total"][0], SHOTS_LINES),
            "chutes_equipe": {home_team: self._corners_market(cs["home"][0], SHOTS_TEAM_LINES),
                              away_team: self._corners_market(cs["away"][0], SHOTS_TEAM_LINES)},
            "chutes_a_gol": {home_team: self._corners_market(sot["home"][0], SOT_TEAM_LINES),
                             away_team: self._corners_market(sot["away"][0], SOT_TEAM_LINES),
                             "total": self._corners_market(sot["total"][0], SOT_LINES)},
            "escanteios": {home_team: self._corners_market(cd["home"][0]),
                           away_team: self._corners_market(cd["away"][0]),
                           "total": self._corners_market(cd["total"][0])},
            "cartoes": {home_team: self._corners_market(cc["home"][0], CARDS_LINES),
                        away_team: self._corners_market(cc["away"][0], CARDS_LINES),
                        "total": self._corners_market(cc["total"][0], CARDS_LINES)},
            "ambas_marcam": btts_res,
            "over_2_5": over_res,
            "placar_exato": placar_exato,
            "tempos": tempos,
            "confronto_direto": h2h["_resumo"],
            "confiabilidade": confiabilidade,
        }


if __name__ == "__main__":
    import pprint
    art_path = "api/model_artifacts" if os.path.exists("api/model_artifacts") else "model_artifacts"
    p = Predictor(art_path)
    print("Seleções:", len(p.teams()))
    pprint.pprint(p.predict("Brazil", "Argentina", neutral=True, tournament="Copa do Mundo"))
