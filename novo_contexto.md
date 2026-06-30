# Novo Contexto — sessão de testes (29/06/2026, branch `claude-testing`)

> Documento de handoff desta sessão de experimentação. Resume o estado do sistema, o que
> foi feito, os achados e o que fazer a seguir. Complementa `ARCHITECTURE.md` / `SISTEMA_COMPLETO.md`.

## 1. Estado do sistema hoje
- **Monorepo:** `backend/` (FastAPI, `backend/.venv`, porta 8000, deploy Railway) + `frontend/`
  (Next.js, Vercel). Rodar: `npm run dev` na raiz. Branch principal: `main`.
- **Modelos em produção** (`backend/model_artifacts/`): Dixon-Coles NB (gols/BTTS/over via conjunta),
  CornersNB cascata r-fixo (escanteios), CardsGP (cartões), ShotsNB (chutes), + mercados por
  equipe/tempo, tier de confiabilidade e cabeçalho de partida no front.
- **Dados:** `international_features_enriched_apifootball.csv` (≈4.102 jogos com box-score, 2016+),
  `halftime_targets.parquet` (gols/cartões por tempo), `pergame_form.parquet` (**forma-por-jogo
  COMPLETA**: 2.123 jogos, rating/minutos/fadiga/momentum/xG-clube/disponibilidade), `h2h_results.csv`
  (martj42 1872+ ∪ api), `referee_features.csv` (**novo**: árbitro+severidade por jogo).

## 2. O que foi feito nesta sessão
- **Relatório 1 (`relatorio1_29062026.md`):** bateria exaustiva (2.016 configs) da **forma-por-jogo
  no mercado de RESULTADO (H/D/A)**.
- **Relatório 2 (`relatorio2_29062026.md`):** modelos **do zero para os mercados de contagem**
  (gols, finalizações, finalizações a gol, escanteios, cartões; por equipe e por tempo) — rodada 1
  (split temporal, ~243 configs) + rodada 2 (CV temporal + árbitro).
- **Coleta nova:** árbitro por jogo + severidade (`build_referee_features.py`).
- **Scripts:** `forma_exhaustive_experiments.py`, `market_models_experiments.py`, `market_round2.py`,
  `build_referee_features.py` (todos resumíveis/reprodutíveis). CSVs de resultados em
  `backend/data/reports/`.

## 3. Achados-chave
1. **Mercados de contagem (foco): trocar Poisson→NB/Generalized-Poisson em FINALIZAÇÕES e
   ESCANTEIOS** dá ganho real e robusto (finalizações ~−0,09 log-loss; escanteios ~−0,018).
   A Poisson subestima a variância dessas contagens altas.
2. **Finalizações a gol:** NB/GP > Poisson, ganho pequeno (~−0,003).
3. **Gols e cartões:** o approach atual (Dixon-Coles/Poisson; CardsGP) já está perto do ótimo —
   nenhuma família testada superou de forma robusta sob CV.
4. **Regressor de média:** GBR ≈ ou melhor que HistGBM sob CV (HGB venceu só no split único, não confirmou).
5. **Forma-por-jogo no RESULTADO:** sinal pequeno mas consistente (rating-residual e momentum),
   maior em jogos equilibrados/alta cobertura — primeiro sinal ortogonal positivo, mas magnitude baixa.
6. **Árbitro nos cartões:** coletado, mas **não melhora** (amostra rasa por árbitro em seleções).

## 4. Próximos passos recomendados
- **[Alto retorno]** Implementar **NB ou Generalized-Poisson** em **finalizações** e revalidar
  **escanteios** com NB/GP, passando pelo gate de não-regressão antes de produção.
- Reavaliar **finalizações a gol** com NB/GP.
- **Manter** gols (DC/Poisson) e cartões (CardsGP).
- Próxima rodada de features para contagem: **faltas/posse/passes** (já temos) e **bivariada**
  (correlação mandante×visitante).
- Forma-por-jogo: usar só em recorte de alta cobertura, com gate, se for promover ao resultado.
- Nada foi promovido à produção nesta sessão — tudo é medição na branch `claude-testing`.

---

## Adendo — rodada de promoção sob gate (29/06/2026)
Validação rigorosa (CV temporal, point-in-time) das promoções propostas. **Resultado: nada
promovido** — ver `relatorio3_promocao_validacao_29062026.md`. Pontos-chave:
- **Premissa corrigida:** produção JÁ usa NB (finalizações/escanteios/a-gol), GP (cartões),
  DC-NB (gols). Os ganhos "Poisson→NB" dos relatórios anteriores eram vs baseline não-produção.
- **GP não bate a NB de produção** (empate/ruído, inconsistente por segmento) → manter NB.
- **Forma no resultado REPROVA** sob CV temporal (piora LogLoss/ECE) — o ganho do relatório 1
  era artefato de CV aleatória.
- **Calibração** pós-hoc não ajuda (produção já calibrada, ECE ~4%). **Posse/passes/faltas**
  não dão ganho consistente.
- Pipeline atual confirmado **robusto e bem calibrado**. Próximo: Exp 3/4/5 (multi-output,
  bivariada/cópula, ataque×defesa) + feature importance (SHAP/permutação).
Scripts: `promotion_validation.py`, `result_forma_validation.py`, `calibration_experiment.py`,
`possession_features_experiment.py` (todos reprodutíveis, seed=42, CV temporal).
