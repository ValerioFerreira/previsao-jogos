# EXP 13 — Dependência cruzada: gols × contagens ofensivas (cópula) — 2026-07-07

## Hipótese
Gols (resultado/DC) e contagens ofensivas (finalizações, escanteios) partilham domínio
territorial: um time que domina gera contagens E marca mais do que os modelos, tratados como
INDEPENDENTES, preveem em conjunto. Afeta combos MISTOS do "Monte sua Aposta"
(ex.: "time vence" + "mais de X escanteios/finalizações").

## Método
Cópula gaussiana (método EXP7) sobre 3 famílias: gols totais (PMF do Dixon-Coles),
finalizações e escanteios (modelos NB). PIT → z → Σ no treino → NLL conjunto indep vs cópula,
CV temporal. Script: `scripts/exp13_goals_counts_copula.py`. 4.166 jogos.

## Resultado
Correlação dos resíduos (PIT):

| | gols | finalizações | escanteios |
|---|---|---|---|
| **gols** | 1.00 | **+0.22** | −0.05 |
| **finalizações** | +0.22 | 1.00 | +0.30 |
| **escanteios** | −0.05 | +0.30 | 1.00 |

**dNLL conjunto −0.092 (cópula melhora 4/4 folds).**

## Veredito: **APROVADO** (com nuance importante)
- **Gols ↔ finalizações: +0.22** — dependência cruzada real e estável. Combos que misturam
  "over gols / vitória" com "over finalizações" são **positivamente correlacionados** e hoje
  precificados como independentes → a odd combinada **superestima a dificuldade**.
- **Gols ↔ escanteios: ≈ −0.05** — praticamente independentes. Escanteio é **proxy fraco de
  gol** (muito escanteio pode indicar ataque estéril); combos gols+escanteios NÃO precisam de
  correção.
- Reforça EXP7: a estrutura de dependência entre mercados é o filão. A cópula de produção deve
  cobrir o **bloco {gols, finalizações, a-gol, escanteios}** (correlações +0.2 a +0.57), deixando
  cartões e impedimentos independentes.

**Tema geral da bateria:** os MARGINAIS estão saturados (Elo domina), mas a **dependência
multivariada entre mercados** é consistentemente ignorada e vale corrigir para apostas combinadas.
