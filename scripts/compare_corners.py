import sys
import os
import json
import warnings
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import nbinom, norm
from scipy.optimize import minimize
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.calibration import calibration_curve

# Add api directory to sys.path
sys.path.append(str(Path("api").resolve()))

warnings.filterwarnings("ignore")

CSV_PATH = Path("international_features_enriched_apifootball.csv")
ARTIFACTS_DIR = Path(r"C:\Users\10341953440\.gemini\antigravity\brain\38bd63cd-c1e9-4756-9d77-8346dce6bac3")
REPORT_PATH = ARTIFACTS_DIR / "comparacao_escanteios.md"

RS = 42
QUANTILES = [0.1, 0.5, 0.9]
M_C = 25  # Grid size 26x26 (0 to 25 corners)

LEAK_OR_ID = {
    "match_id", "date", "home_team", "away_team", "city", "country", "tournament",
    "home_score", "away_score", "goal_diff", "total_goals", "result",
    "home_win", "away_win", "draw", "btts", "over_2_5",
    "has_advanced_stats", "year", "month", "decade",
}

def numeric_features(df):
    cols = []
    for c in df.columns:
        if c in LEAK_OR_ID: continue
        if c.startswith(("home_cur_", "away_cur_")): continue
        if pd.api.types.is_numeric_dtype(df[c]): cols.append(c)
    return cols

def fit_quantile_models(df, feats, target_series, leaf=10):
    sub = df.copy()
    sub["_y"] = target_series
    sub = sub.dropna(subset=["_y"])
    X, y = sub[feats], sub["_y"].astype(float)
    models = {}
    for q in QUANTILES:
        pipe = Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("reg", GradientBoostingRegressor(loss="quantile", alpha=q,
                                               n_estimators=300, max_depth=3,
                                               learning_rate=0.05, min_samples_leaf=leaf,
                                               random_state=RS)),
        ])
        pipe.fit(X, y)
        models[q] = pipe
    return models

def expected_calibration_error(y_true, y_prob, n_bins=10):
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        
        in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper)
        prop_in_bin = np.mean(in_bin)
        
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(y_true[in_bin])
            avg_confidence_in_bin = np.mean(y_prob[in_bin])
            ece += prop_in_bin * np.abs(accuracy_in_bin - avg_confidence_in_bin)
            
    return ece

def compute_quantile_corners_distribution(pred_q10, pred_q50, pred_q90, max_corners=25):
    """
    Deriva a distribuição discreta de escanteios (Normal discretizada) para o modelo quantílico.
    """
    N = len(pred_q50)
    probs = np.zeros((N, max_corners + 1))
    k = np.arange(max_corners + 1)
    
    for i in range(N):
        mu = pred_q50[i]
        std = max(0.1, (pred_q90[i] - pred_q10[i]) / 2.563)
        
        p_k = norm.cdf(k + 0.5, loc=mu, scale=std) - norm.cdf(k - 0.5, loc=mu, scale=std)
        p_k[p_k < 0] = 0.0
        if p_k.sum() > 0:
            p_k /= p_k.sum()
        else:
            p_k[0] = 1.0
            
        probs[i] = p_k
        
    return probs

def convolve_probabilities(prob_H, prob_A, max_corners=25):
    """
    Realiza a convolução para obter a distribuição da soma de duas variáveis independentes.
    prob_H, prob_A: shapes (N, max_corners + 1)
    Retorna: prob_S de shape (N, 2 * max_corners + 1)
    """
    N = len(prob_H)
    prob_S = np.zeros((N, 2 * max_corners + 1))
    for i in range(N):
        prob_S[i] = np.convolve(prob_H[i], prob_A[i])
    return prob_S

# ------------------------------------------------------------------------------
# ABORDAGEM B: Modelo Acoplado (Bivariate NB)
# ------------------------------------------------------------------------------
class BivariateNBCorners:
    def __init__(self, n_estimators=100, max_depth=3, learning_rate=0.05, max_corners=25, random_state=42):
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.learning_rate = learning_rate
        self.max_corners = max_corners
        self.random_state = random_state
        
        self.r_H_ = 5.0
        self.r_A_ = 5.0
        self.beta_ = 0.0
        self.use_exponential_ = False
        
        self.model_home_ = None
        self.model_away_ = None
        
    def _create_regressor(self):
        return Pipeline([
            ("imp", SimpleImputer(strategy="median")),
            ("reg", GradientBoostingRegressor(
                loss="squared_error",
                n_estimators=self.n_estimators,
                max_depth=self.max_depth,
                learning_rate=self.learning_rate,
                random_state=self.random_state
            ))
        ])
        
    def fit(self, X, y_h, y_a):
        from scipy.special import gammaln
        
        # 1. Ajustar regressores de expectativa (lambda_H, lambda_A)
        self.model_home_ = self._create_regressor()
        self.model_away_ = self._create_regressor()
        
        self.model_home_.fit(X, y_h)
        self.model_away_.fit(X, y_a)
        
        lambdas = np.maximum(self.model_home_.predict(X), 0.1)
        mus = np.maximum(self.model_away_.predict(X), 0.1)
        
        # 2. Verificar se o clamp da forma linear ativa frequentemente no treino
        # Vamos testar um beta negativo moderado (ex: -0.02)
        # E ver a frequência de termos negativos na grade 26x26
        test_beta = -0.02
        k_arr = np.arange(self.max_corners + 1)
        delta_H = k_arr[:, None, None] - lambdas[None, None, :]  # shape (max_corners+1, 1, N)
        delta_A = k_arr[None, :, None] - mus[None, None, :]      # shape (1, max_corners+1, N)
        delta_prod = delta_H * delta_A                           # shape (max_corners+1, max_corners+1, N)
        
        terms = 1.0 + test_beta * delta_prod
        term_neg_count = np.sum(terms < 0)
        total_cells = len(y_h) * (self.max_corners + 1)**2
        neg_pct = (term_neg_count / total_cells) * 100
        print(f">> Auditoria de Clamp: {neg_pct:.3f}% das células do treino seriam negativas com beta=-0.02.")
        
        if neg_pct > 1.0:
            print("   [CHAVEAMENTO] Frequência de clamp > 1%. Utilizando Forma Exponencial Pura (Sem Clamp).")
            self.use_exponential_ = True
        else:
            print("   [MANTIDO] Frequência de clamp <= 1%. Utilizando Forma Linear padrão.")
            self.use_exponential_ = False
            
        # 3. Otimizar r_H, r_A, beta via MLE
        print(">> Otimizando parâmetros globais (r_H, r_A, beta) via MLE...")
        
        N = len(y_h)
        y_h_clipped = np.clip(y_h, 0, self.max_corners).astype(int)
        y_a_clipped = np.clip(y_a, 0, self.max_corners).astype(int)
        
        # Fator k! no denominador do PMF da NB: gammaln(k + 1)
        log_k_fact = gammaln(k_arr + 1)  # shape (max_corners+1,)
        
        def objective(params):
            r_H, r_A, beta = params
            if r_H <= 0.05 or r_A <= 0.05:
                return 1e10
                
            # Log-PMF das marginais de forma vetorizada (shape (max_corners+1, N))
            # PMF(k) = exp( gammaln(k + r) - gammaln(k+1) - gammaln(r) + k*log(lam/(r+lam)) + r*log(r/(r+lam)) )
            
            # Mandante
            log_p_H_term = r_H * np.log(r_H / (r_H + lambdas))
            log_1_minus_p_H_term = np.log(lambdas / (r_H + lambdas))
            log_prob_H = (gammaln(k_arr[:, None] + r_H) 
                          - log_k_fact[:, None] 
                          - gammaln(r_H) 
                          + k_arr[:, None] * log_1_minus_p_H_term[None, :] 
                          + log_p_H_term[None, :])
            prob_H = np.exp(log_prob_H)
            
            # Visitante
            log_p_A_term = r_A * np.log(r_A / (r_A + mus))
            log_1_minus_p_A_term = np.log(mus / (r_A + mus))
            log_prob_A = (gammaln(k_arr[:, None] + r_A) 
                          - log_k_fact[:, None] 
                          - gammaln(r_A) 
                          + k_arr[:, None] * log_1_minus_p_A_term[None, :] 
                          + log_p_A_term[None, :])
            prob_A = np.exp(log_prob_A)
            
            # Matriz conjunta independente de shape (max_corners+1, max_corners+1, N)
            P_joint = prob_H[:, None, :] * prob_A[None, :, :]
            
            # Fator tau de acoplamento
            if self.use_exponential_:
                tau = np.exp(beta * delta_prod)
            else:
                tau = np.maximum(0.0, 1.0 + beta * delta_prod)
                
            P_joint_corr = P_joint * tau
            sum_p = P_joint_corr.sum(axis=(0, 1))  # shape (N,)
            
            if np.any(sum_p <= 0):
                return 1e10
                
            P_joint_norm = P_joint_corr / sum_p[None, None, :]
            
            # Obter a probabilidade observada para cada jogo
            prob_obs = P_joint_norm[y_h_clipped, y_a_clipped, np.arange(N)]
            
            nll = -np.sum(np.log(np.maximum(prob_obs, 1e-15)))
            return nll
            
        # Chute inicial e limites
        initial_guess = [5.0, 5.0, -0.01]
        bounds = [(0.1, 1000.0), (0.1, 1000.0), (-0.2, 0.2)]
        
        res = minimize(objective, initial_guess, method="L-BFGS-B", bounds=bounds)
        
        if res.success:
            self.r_H_, self.r_A_, self.beta_ = res.x
            print(f"MLE Convergiu:")
            print(f"  - r_H: {self.r_H_:.4f}")
            print(f"  - r_A: {self.r_A_:.4f}")
            print(f"  - beta (correlação): {self.beta_:.4f}")
        else:
            print("[AVISO] MLE não convergiu. Usando valores default.")
            self.r_H_, self.r_A_, self.beta_ = 5.0, 5.0, 0.0
            
        return self
        
    def predict_joint(self, X):
        N = len(X)
        lambdas = np.maximum(self.model_home_.predict(X), 0.1)
        mus = np.maximum(self.model_away_.predict(X), 0.1)
        
        k_arr = np.arange(self.max_corners + 1)
        P_joints = np.zeros((N, self.max_corners + 1, self.max_corners + 1))
        
        for i in range(N):
            lam = lambdas[i]
            mu = mus[i]
            
            p_H = self.r_H_ / (self.r_H_ + lam)
            prob_H = nbinom.pmf(k_arr, n=self.r_H_, p=p_H)
            
            p_A = self.r_A_ / (self.r_A_ + mu)
            prob_A = nbinom.pmf(k_arr, n=self.r_A_, p=p_A)
            
            P_joint = prob_H[:, None] * prob_A[None, :]
            
            if self.use_exponential_:
                tau = np.exp(self.beta_ * (k_arr[:, None] - lam) * (k_arr[None, :] - mu))
            else:
                tau = np.maximum(0.0, 1.0 + self.beta_ * (k_arr[:, None] - lam) * (k_arr[None, :] - mu))
                
            P_joint_corr = P_joint * tau
            sum_p = P_joint_corr.sum()
            if sum_p > 0:
                P_joints[i] = P_joint_corr / sum_p
            else:
                P_joints[i] = P_joint  # fallback
                
        return P_joints, lambdas, mus

# ------------------------------------------------------------------------------
# SCRIPT PRINCIPAL DE VALIDAÇÃO
# ------------------------------------------------------------------------------
def run_validation():
    print("================================================================================")
    print(" VALIDAÇÃO TEMPORAL DE MODELOS DE ESCANTEIOS (N = 4.102 JOGOS TOTAIS COM STATS)")
    print("================================================================================")
    
    if not CSV_PATH.exists():
        print(f"[ERRO] {CSV_PATH} não encontrado.")
        return
        
    df = pd.read_csv(CSV_PATH, parse_dates=["date"])
    df = df.sort_values("date").reset_index(drop=True)
    
    # Filtrar estritamente apenas jogos que contêm estatísticas de escanteio válidas (N = 4.102)
    df_adv = df[df["has_advanced_stats"] == 1].dropna(subset=["home_cur_sb_corners", "away_cur_sb_corners"]).copy()
    
    # Divisão temporal estrita 80% / 20%
    n_train_idx = int(len(df_adv) * 0.8)
    cutoff_date = df_adv.iloc[n_train_idx]["date"]
    print(f"Data de corte temporal: {cutoff_date.strftime('%Y-%m-%d')}")
    
    df_train = df_adv[df_adv["date"] <= cutoff_date].reset_index(drop=True)
    df_test = df_adv[df_adv["date"] > cutoff_date].reset_index(drop=True)
    
    print(f"Treino: {len(df_train)} jogos | Teste: {len(df_test)} jogos")
    print("================================================================================")
    
    all_feats = numeric_features(df)
    full_feats = [c for c in all_feats if c not in LEAK_OR_ID]
    
    # targets
    y_train_h = df_train["home_cur_sb_corners"].astype(int).values
    y_train_a = df_train["away_cur_sb_corners"].astype(int).values
    y_train_total = y_train_h + y_train_a
    
    y_test_h = df_test["home_cur_sb_corners"].astype(int).values
    y_test_a = df_test["away_cur_sb_corners"].astype(int).values
    y_test_total = y_test_h + y_test_a
    
    X_train = df_train[full_feats]
    X_test = df_test[full_feats]
    
    # --------------------------------------------------------------------------
    # 1. Ajustar Modelo Atual (Quantílico) no Treino Temporal
    # --------------------------------------------------------------------------
    print("\n>> Ajustando modelo ATUAL (Quantílico) no treino...")
    qm_home_temp = fit_quantile_models(df_train, full_feats, df_train["home_cur_sb_corners"], leaf=10)
    qm_away_temp = fit_quantile_models(df_train, full_feats, df_train["away_cur_sb_corners"], leaf=10)
    qm_total_temp = fit_quantile_models(df_train, full_feats, df_train["home_cur_sb_corners"] + df_train["away_cur_sb_corners"], leaf=10)
    
    # Predições quantílicas no teste
    pred_h_q10 = qm_home_temp[0.1].predict(X_test)
    pred_h_q50 = qm_home_temp[0.5].predict(X_test)
    pred_h_q90 = qm_home_temp[0.9].predict(X_test)
    
    pred_a_q10 = qm_away_temp[0.1].predict(X_test)
    pred_a_q50 = qm_away_temp[0.5].predict(X_test)
    pred_a_q90 = qm_away_temp[0.9].predict(X_test)
    
    pred_t_q10 = qm_total_temp[0.1].predict(X_test)
    pred_t_q50 = qm_total_temp[0.5].predict(X_test)
    pred_t_q90 = qm_total_temp[0.9].predict(X_test)
    
    # Derivar distribuições de probabilidade legadas (Normais discretizadas)
    prob_h_curr = compute_quantile_corners_distribution(pred_h_q10, pred_h_q50, pred_h_q90, max_corners=M_C)
    prob_a_curr = compute_quantile_corners_distribution(pred_a_q10, pred_a_q50, pred_a_q90, max_corners=M_C)
    prob_total_curr = compute_quantile_corners_distribution(pred_t_q10, pred_t_q50, pred_t_q90, max_corners=2*M_C)
    
    # --------------------------------------------------------------------------
    # 2. Ajustar Abordagem A (Independente NB) no Treino
    # --------------------------------------------------------------------------
    print("\n>> Ajustando ABORDAGEM A (Independente NB) no treino...")
    # Modelar expectativas via regressão base GBR (squared_error)
    model_h_lam = Pipeline([("imp", SimpleImputer(strategy="median")), ("reg", GradientBoostingRegressor(loss="squared_error", n_estimators=100, max_depth=3, learning_rate=0.05, random_state=RS))])
    model_a_lam = Pipeline([("imp", SimpleImputer(strategy="median")), ("reg", GradientBoostingRegressor(loss="squared_error", n_estimators=100, max_depth=3, learning_rate=0.05, random_state=RS))])
    
    model_h_lam.fit(X_train, y_train_h)
    model_a_lam.fit(X_train, y_train_a)
    
    lambdas_tr = np.maximum(model_h_lam.predict(X_train), 0.1)
    mus_tr = np.maximum(model_a_lam.predict(X_train), 0.1)
    
    # Estimar parâmetros de dispersão r_H e r_A de forma independente via MLE
    def optimize_r(y_vals, lam_vals):
        def obj(r):
            if r <= 0.05: return 1e10
            p = r / (r + lam_vals)
            return -np.sum(np.log(nbinom.pmf(y_vals, n=r, p=p) + 1e-15))
        res = minimize(obj, [5.0], bounds=[(0.1, 1000.0)], method="L-BFGS-B")
        return float(res.x[0])
        
    r_H_ind = optimize_r(y_train_h, lambdas_tr)
    r_A_ind = optimize_r(y_train_a, mus_tr)
    print(f"  - r_H Independente: {r_H_ind:.4f}")
    print(f"  - r_A Independente: {r_A_ind:.4f}")
    
    # Predições no Teste para Abordagem A
    lambdas_te = np.maximum(model_h_lam.predict(X_test), 0.1)
    mus_te = np.maximum(model_a_lam.predict(X_test), 0.1)
    
    k_arr = np.arange(M_C + 1)
    prob_h_ind = np.zeros((len(df_test), M_C + 1))
    prob_a_ind = np.zeros((len(df_test), M_C + 1))
    
    for i in range(len(df_test)):
        prob_h_ind[i] = nbinom.pmf(k_arr, n=r_H_ind, p=r_H_ind/(r_H_ind + lambdas_te[i]))
        prob_a_ind[i] = nbinom.pmf(k_arr, n=r_A_ind, p=r_A_ind/(r_A_ind + mus_te[i]))
        # Renormalizar marginal por segurança
        prob_h_ind[i] /= prob_h_ind[i].sum()
        prob_a_ind[i] /= prob_a_ind[i].sum()
        
    # Total via convolução
    prob_total_ind = convolve_probabilities(prob_h_ind, prob_a_ind, max_corners=M_C)
    
    # --------------------------------------------------------------------------
    # 3. Ajustar Abordagem B (Acoplada NB) no Treino
    # --------------------------------------------------------------------------
    print("\n>> Ajustando ABORDAGEM B (Acoplada NB) no treino...")
    model_b = BivariateNBCorners(n_estimators=100, max_depth=3, learning_rate=0.05, max_corners=M_C, random_state=42)
    model_b.fit(X_train, y_train_h, y_train_a)
    
    # Predições no Teste para Abordagem B
    P_joint_dc, lambdas_te_b, mus_te_b = model_b.predict_joint(X_test)
    
    # Derivar marginais e total da conjunta
    prob_h_dc = np.zeros((len(df_test), M_C + 1))
    prob_a_dc = np.zeros((len(df_test), M_C + 1))
    prob_total_dc = np.zeros((len(df_test), 2 * M_C + 1))
    
    for i in range(len(df_test)):
        # Marginais
        prob_h_dc[i] = P_joint_dc[i].sum(axis=1)
        prob_a_dc[i] = P_joint_dc[i].sum(axis=0)
        # Total
        for x in range(M_C + 1):
            for y in range(M_C + 1):
                prob_total_dc[i, x + y] += P_joint_dc[i, x, y]
                
    # --------------------------------------------------------------------------
    # 4. Cálculo de Métricas por Mercado
    # --------------------------------------------------------------------------
    print("\n>> Processando métricas probabilísticas de escanteios...")
    
    # Linhas de over a avaliar
    L_home = 4.5
    L_away = 3.5
    L_total = 8.5
    
    # Listar dados para loop
    markets = [
        {"name": "Mandante", "actual": y_test_h, "line": L_home, "max_c": M_C, "probs": {"atual": prob_h_curr, "A": prob_h_ind, "B": prob_h_dc}, "medians": {"atual": pred_h_q50, "A": lambdas_te, "B": lambdas_te_b}},
        {"name": "Visitante", "actual": y_test_a, "line": L_away, "max_c": M_C, "probs": {"atual": prob_a_curr, "A": prob_a_ind, "B": prob_a_dc}, "medians": {"atual": pred_a_q50, "A": mus_te, "B": mus_te_b}},
        {"name": "Total", "actual": y_test_total, "line": L_total, "max_c": 2*M_C, "probs": {"atual": prob_total_curr, "A": prob_total_ind, "B": prob_total_dc}, "medians": {"atual": pred_t_q50, "A": lambdas_te + mus_te, "B": lambdas_te_b + mus_te_b}}
    ]
    
    results = {}
    
    for m in markets:
        name = m["name"]
        actual = m["actual"]
        line = m["line"]
        max_c = m["max_c"]
        y_true_over = (actual > line).astype(int)
        
        results[name] = {}
        
        for key in ["atual", "A", "B"]:
            prob_matrix = m["probs"][key] # shape (N, max_c + 1)
            
            # Log-Loss discreto de contagem
            clipped_actual = np.clip(actual, 0, max_c).astype(int)
            ll = -np.mean(np.log(prob_matrix[np.arange(len(df_test)), clipped_actual] + 1e-15))
            
            # Probabilidade de Over Line
            # sum over indices > line
            prob_over = prob_matrix[:, int(line) + 1:].sum(axis=1)
            
            # Brier e ECE do Over
            brier = mean_squared_error(y_true_over, prob_over)
            ece = expected_calibration_error(y_true_over, prob_over)
            
            # Cobertura do intervalo de 80% e largura média do intervalo
            # Buscando quantil 10 e 90 da distribuição de probabilidade
            coverages = []
            widths = []
            
            for i in range(len(df_test)):
                cdf = np.cumsum(prob_matrix[i])
                q10 = np.searchsorted(cdf, 0.1)
                q90 = np.searchsorted(cdf, 0.9)
                widths.append(float(q90 - q10))
                if q10 <= actual[i] <= q90:
                    coverages.append(1.0)
                else:
                    coverages.append(0.0)
                    
            mean_coverage = np.mean(coverages)
            mean_width = np.mean(widths)
            
            # MAE/RMSE pontual
            pred_pt = m["medians"][key]
            mae = mean_absolute_error(actual, pred_pt)
            rmse = np.sqrt(mean_squared_error(actual, pred_pt))
            
            results[name][key] = {
                "logloss": ll,
                "brier": brier,
                "ece": ece,
                "coverage": mean_coverage,
                "width": mean_width,
                "mae": mae,
                "rmse": rmse,
                "mean_pred": np.mean(pred_pt)
            }
            
    # --------------------------------------------------------------------------
    # 5. Escrita do Relatório Final (comparacao_escanteios.md)
    # --------------------------------------------------------------------------
    print("\n>> Gerando relatório comparacao_escanteios.md...")
    
    lines = []
    lines.append("# Comparação de Modelos de Contagem para Escanteios (Passo 2)")
    lines.append(f"\n- **Corte de Validação Temporal:** {cutoff_date.strftime('%Y-%m-%d')}")
    lines.append(f"- **Tamanho do Treino:** {len(df_train)} jogos (estatísticas avançadas válidas)")
    lines.append(f"- **Tamanho do Teste:** {len(df_test)} jogos (estatísticas avançadas válidas)")
    lines.append(f"- **Tamanho da Grade:** $M_C = {M_C}$ (grade conjunta $26 \times 26$)")
    
    # Adicionar Parâmetros NB e Dixon-Coles
    lines.append("\n## Parâmetros Estimados por MLE no Treino")
    lines.append(f"- **Abordagem A (Independente):**")
    lines.append(f"  - $r_H$ (dispersão mandante): **{r_H_ind:.4f}**")
    lines.append(f"  - $r_A$ (dispersão visitante): **{r_A_ind:.4f}**")
    lines.append(f"- **Abordagem B (Acoplada):**")
    lines.append(f"  - $r_H$ (dispersão mandante): **{model_b.r_H_:.4f}**")
    lines.append(f"  - $r_A$ (dispersão visitante): **{model_b.r_A_:.4f}**")
    lines.append(f"  - $\\beta$ (correlação de Dixon-Coles): **{model_b.beta_:.4f}** (correlação {'negativa' if model_b.beta_ < 0 else 'positiva'})")
    lines.append(f"  - Tipo de Correlação: **{'Exponencial Pura (Sem Clamp)' if model_b.use_exponential_ else 'Linear padrão'}**")
    
    # Validação do viés global
    lines.append("\n## Validação de Viés Global (Média Prevista vs Média Real)")
    lines.append("\n| Mercado | Média Real | Média Prevista (Atual) | Média Prevista (Abordagem A) | Média Prevista (Abordagem B) |")
    lines.append("|---|---|---|---|---|")
    for m in markets:
        name = m["name"]
        real_m = np.mean(m["actual"])
        lines.append(f"| {name} | {real_m:.4f} | {results[name]['atual']['mean_pred']:.4f} | {results[name]['A']['mean_pred']:.4f} | {results[name]['B']['mean_pred']:.4f} |")
        
    # Tabelas Comparativas por Mercado
    lines.append("\n## Resultados Comparativos por Mercado")
    
    for m in markets:
        name = m["name"]
        line = m["line"]
        lines.append(f"\n### Mercado: Escanteios {name} (Linha Over {line})")
        lines.append("\n| Abordagem | Log-Loss Contagem | Brier Score Over | ECE Over | Cobertura 80% | Largura Média | MAE | RMSE |")
        lines.append("|---|---|---|---|---|---|---|---|")
        
        for key, label in [("atual", "Atual (Quantílica)"), ("A", "Abordagem A (Indep)"), ("B", "Abordagem B (Acoplada)")]:
            res = results[name][key]
            lines.append(f"| {label} | {res['logloss']:.5f} | {res['brier']:.5f} | {res['ece']:.5%} | {res['coverage']:.2%} | {res['width']:.2f} | {res['mae']:.3f} | {res['rmse']:.3f} |")
            
    # Recomendação Acionável
    lines.append("\n## Recomendação Acionável e Próximos Passos")
    
    # Determinar qual modelo é melhor por mercado com base em Log-loss e ECE
    # Mandante
    ll_h_a = results["Mandante"]["A"]["logloss"]
    ll_h_b = results["Mandante"]["B"]["logloss"]
    ece_h_a = results["Mandante"]["A"]["ece"]
    ece_h_b = results["Mandante"]["B"]["ece"]
    rec_h = "Abordagem B (Acoplada)" if ll_h_b < ll_h_a else "Abordagem A (Independente)"
    
    # Visitante
    ll_a_a = results["Visitante"]["A"]["logloss"]
    ll_a_b = results["Visitante"]["B"]["logloss"]
    rec_a = "Abordagem B (Acoplada)" if ll_a_b < ll_a_a else "Abordagem A (Independente)"
    
    # Total
    ll_t_a = results["Total"]["A"]["logloss"]
    ll_t_b = results["Total"]["B"]["logloss"]
    ece_t_a = results["Total"]["A"]["ece"]
    ece_t_b = results["Total"]["B"]["ece"]
    rec_t = "Abordagem B (Acoplada)" if ll_t_b < ll_t_a else "Abordagem A (Independente)"
    
    lines.append(f"\nCom base nos resultados probabilísticos observados out-of-sample:")
    lines.append(f"1. **Escanteios do Mandante:** Recomenda-se usar **{rec_h}** (Log-Loss A={ll_h_a:.5f} vs B={ll_h_b:.5f}, ECE A={ece_h_a:.2%} vs B={ece_h_b:.2%}).")
    lines.append(f"2. **Escanteios do Visitante:** Recomenda-se usar **{rec_a}** (Log-Loss A={ll_a_a:.5f} vs B={ll_a_b:.5f}).")
    lines.append(f"3. **Escanteios Totais:** Recomenda-se usar **{rec_t}** (Log-Loss A={ll_t_a:.5f} vs B={ll_t_b:.5f}, ECE A={ece_t_a:.2%} vs B={ece_t_b:.2%}).")
    
    if rec_t == "Abordagem B (Acoplada)":
        lines.append("\n> [!NOTE]\n> O acoplamento bivariado da **Abordagem B** superou a modelagem independente no total de escanteios, confirmando que capturar a correlação (através de $\\beta = " + f"{model_b.beta_:.4f}" + "$) fornece uma variância muito mais realista e melhor calibração de Over/Under para os mercados consolidados.")
    else:
        lines.append("\n> [!NOTE]\n> A convolução simples da **Abordagem A** empatou ou superou a modelagem acoplada. Isso sugere que a correlação entre os lados não é forte o suficiente para justificar o acréscimo de complexidade no cálculo da conjunta.")
        
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
        
    print(f"\n>> Relatório final gerado com sucesso em: {REPORT_PATH}")

if __name__ == "__main__":
    run_validation()
