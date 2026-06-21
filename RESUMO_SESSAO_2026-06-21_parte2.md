# Resumo da Sessão — 2026-06-21 (parte 2: UX, Passo 4 e campanha de modelos)

> Continuação da sessão do backend. Passo a passo do que foi feito: UX completo (Passo 3),
> harness de value vs mercado (Passo 4, coletando ao vivo) e a campanha de melhoria de
> modelos (calibração, rating, xG) — toda com resultado honestamente negativo. Mapa de
> estado em `ESTADO_E_PROXIMOS_PASSOS.md`.

---

## 1. Passo 3 — UX/UI completo (commit `095b170`)

Front Next migrado de "expõe metade do backend" para feature-completo, em 5 blocos
validados (tsc limpo + paridade com o backend, sem tocar nos modelos):

- **Fundação:** tipos TS estendidos (`CountPrediction`/`distribuicao`/`linhas`; mercado de
  `cartoes`; `odds.linhas_numericas.cartoes`). Mercado de **cartões exposto pela 1ª vez** +
  **grades O/U completas** da CDF (antes só 1 linha por mercado) + recorte "total" em escanteios.
- **Explorador prob-alvo ↔ linha:** deriva a prob de QUALQUER linha .5 da PMF real (fórmula
  conferida contra a grade do backend, 0 divergência em 35 linhas). Entrada por odd.
- **Value betting:** edge/EV/de-vig espelhando `api/value_betting.py` (paridade exata em 7
  casos, incl. clamp e de-vig). Cobre resultado/gols/BTTS + todas as linhas de contagem.
- **Edição controlada das 10 features:** sliders bounded substituem a edição livre; novo
  override de `h2h_home_gd_mean` (payload ganhou `h2h_overrides`/`context_overrides`).
  Validado end-to-end: overrides movem a previsão na direção certa (elo_pre, h2h).
- **Combinada "teto otimista"** (prob combinada + ressalva de correlação), **confiabilidade
  do confronto** (volume de h2h) e **avisos de risco** consolidados.

## 2. Passo 4 — Harness de value vs mercado, coletando ao vivo (commits `1f26437`, `678ffce`)

Contorna a limitação da api-football (odds só 1–14 dias antes, 7 dias de histórico →
sem backtest retroativo; coleta forward-only):

- `collect_odds_forward.py` — enumera jogos de seleções dos próximos N dias, coleta odds de
  consenso (mediana entre casas) E **snapshota a previsão do modelo** no momento (pré-jogo,
  sem PMFs). Série temporal em `data/odds/snapshots/<id>.jsonl` + `registry.json`.
- `resolve_results.py` — placar de 90min + escanteios/cartões/chutes reais (extração validada
  contra Senegal 0-2 Netherlands).
- `value_report.py` — divergência modelo×mercado (EV, de-vig, `--max-odd`).
- `value_backtest.py` — junta snapshot + resultado, LIQUIDA cada aposta, reporta ROI geral,
  ROI das apostas +EV (teste central), por mercado e calibração (liquidação validada, 15 casos
  + smoke-test de integração).
- **Agendamento:** tarefa Windows **`PrevisaoJogos\CollectOdds` (3/3h)** via
  `collect_odds_task.cmd` (coleta + resolve). **34 jogos da Copa 2026 semeados.**
- **Achado inicial:** EV bruto dominado por zebras miscalibradas; edges líquidos concentram
  em cartões-Over e gols-Under (viés a confirmar com resultados).

## 3. Campanha de melhoria de modelos — toda NEGATIVA (commits `a488189`, `5f59209`, xG-audit)

Disciplina de gate (melhorar log-loss E ECE OOS, sem regressão) barrou tudo:

- **Calibração post-hoc** (resultado/over2.5/escanteios-vis.): modelos já calibrados OOS
  (resultado ECE 1.78%, BTTS 2.42%, over2.5 3.71%). Temperature/isotônica melhoram uma métrica
  e regridem a outra. A folga de escanteios-vis. (6.31%) era artefato de linha única (1.82%
  agrupado). **Nada passa.**
- **Confiabilidade de rating:** o "+EV espúrio" em zebras (Curaçao 22.5% modelo vs 5% mercado)
  é **inflação de Elo por força de tabela** (Curaçao Elo 1573 inflado; modelo dá Costa do
  Marfim 50.7% vs 83% do mercado), NÃO flagável por nº de jogos ou Elo (ambos bem calibrados).
  Sharpening condicional a mismatch conserta o viés direcionalmente, mas o ganho é minúsculo
  e **não robusto** (alterna entre limiares G vizinhos = ruído).
- **xG:** **muro de dados** — só 258/9.511 jogos (2.7%), concentrado em UEFA/CONMEBOL 2024 +
  Copa 2026. Esparso demais para uma feature de forma-xG. Inviável.

**Meta-conclusão:** os modelos estão no teto prático por ajuste in-sample. O ganho real só
virá do **backtest ao vivo** (árbitro empírico de edge) ou de dados/sinal novos no futuro.

## 4. Modelos em produção (referência rápida)

| Modelo (artefato) | Serve | Dados | Top impacto |
|---|---|---|---|
| **Dixon-Coles NB** (`dixon_coles_goals.joblib`) | vencedor, gols, BTTS, over2.5 | base_feats (135, sem `sb_`), **9.976 jogos** | **elo_diff** domina; h2h, forma, tournament_weight |
| **CornersNB** (`corners_nb.joblib`) | escanteios mand./vis./total | full_feats (243), **4.102 jogos** | **elo_home_winprob (0.52!)**; box-score fraco |
| **ShotsNB** (`shots_nb.joblib`, decay H=2) | chutes | full_feats, **4.102 jogos** | **sb_shots histórico**; depois Elo/torneio |
| **CardsNB** (`cards_nb.joblib`) | cartões | full_feats, **4.102 jogos** | **is_friendly** + Elo (contexto competitivo) |

## 5. Estado e próximos passos

- **Tudo commitado** na `main`. `data/odds/` é gitignored (dados locais).
- **Próximo:** deixar o backtest ao vivo acumular (jogos da Copa resolvem a partir de
  hoje 22h UTC) e, com volume, rodar `value_backtest.py` para o primeiro veredito de edge.
- Não há alavanca de melhoria in-sample pendente. Retorno ao front/UX é refino opcional.
