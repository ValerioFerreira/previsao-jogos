# EXP 7 — Modelagem conjunta multivariada das contagens (fim do cascade) — 2026-07-07

## Arquitetura / matemática
Hipótese: finalizações, escanteios e cartões partilham um fator latente ("intensidade
territorial"); o CASCADE (pred_shots → escanteios → cartões) captura só parte disso.
Testamos a dependência MULTIVARIADA COMPLETA com uma **cópula gaussiana** sobre os marginais
de PRODUÇÃO (NB/GP), sem mexer neles:

```
1. PMF do TOTAL de cada contagem (modelos deployados).
2. mid-PIT:  u_i = (F_i(k−1)+F_i(k))/2 no valor observado ;  z_i = Φ⁻¹(u_i).
3. TREINO: Σ = corr(z) (estrutura da cópula), point-in-time.
4. NLL conjunto:  indep = −Σ log pmf_i  ;  cópula = indep − log c_Σ(z),
   c_Σ(z) = |Σ|^{-1/2} · exp(−½ zᵀ(Σ⁻¹−I)z).
```
Script: `scripts/exp7_multivariate_counts.py`. Gate §6: CV temporal expanding (0.5→0.85);
métrica = **NLL conjunto** (log-loss multivariado das 3 contagens).

## Resultados (4.166 jogos com as 3 contagens)
Estrutura de correlação dos resíduos (PIT) dos modelos de produção:

| | finalizações | escanteios | cartões |
|---|---|---|---|
| **finalizações** | 1.00 | **+0.28** | +0.05 |
| **escanteios** | +0.28 | 1.00 | ≈0 |
| **cartões** | +0.05 | ≈0 | 1.00 |

| fold | NLL indep | NLL cópula | dNLL | corr(fin,esc) |
|---|---|---|---|---|
| 0.50 | 7.858 | 7.799 | **−0.058** | 0.267 |
| 0.62 | 7.796 | 7.736 | **−0.060** | 0.281 |
| 0.73 | 7.782 | 7.738 | **−0.044** | 0.292 |
| 0.85 | 7.694 | 7.633 | **−0.061** | 0.292 |

**dNLL médio −0.056 (cópula melhora 4/4 folds).**

## Veredito: **APROVADO** — como camada de correlação para mercados COMBINADOS
- Existe **dependência multivariada real e estável**: finalizações↔escanteios ≈ **+0.28**
  (o fator latente da hipótese), residual DEPOIS dos modelos de produção → o cascade **não a
  captura por completo** na distribuição conjunta. Cartões são **idiossincráticos** (corr ≈ 0
  com ambos), confirmando o histórico.
- A cópula reduz o **log-loss conjunto** de forma consistente (−0.056, 4/4). **Não altera os
  marginais** (a produção continua ótima marginal); o ganho é na **probabilidade CONJUNTA**.
- **Uso prático:** aplicar a correção da cópula em **apostas combinadas** que misturam
  finalizações + escanteios (ex.: "mais de X finalizações E mais de Y escanteios") — hoje o
  "Monte sua Aposta" multiplica as odds assumindo INDEPENDÊNCIA, o que **superestima** a
  dificuldade de combos positivamente correlacionados. A cópula corrige isso.
- **Não** é substituição do cascade nem dos marginais; é uma **camada nova** (Σ de 2 parâmetros
  úteis: fin↔esc) para combos. Baixo risco, ganho comprovado.

**Próximo passo de produção:** persistir Σ (por corte temporal recente) e aplicar na odd
combinada quando as seleções forem de contagens correlacionadas.

## Extensão a 5 contagens (finalizações, a-gol, escanteios, impedimentos, cartões)
Rodando com 5 mercados (3.969 jogos), a estrutura fica clara — **fator latente ofensivo forte**:

| | fin | a-gol | esc | imped | cart |
|---|---|---|---|---|---|
| **finalizações** | 1.00 | **+0.57** | +0.30 | −0.03 | +0.03 |
| **a-gol** | +0.57 | 1.00 | +0.18 | ≈0 | −0.02 |
| **escanteios** | +0.30 | +0.18 | 1.00 | ≈0 | ≈0 |
| **impedimentos** | −0.03 | ≈0 | ≈0 | 1.00 | +0.03 |
| **cartões** | +0.03 | −0.02 | ≈0 | +0.03 | 1.00 |

**dNLL conjunto −0.280 (4/4 folds)** — muito maior que no caso de 3 (−0.056), puxado pela
correlação finalizações↔a-gol (+0.57, em parte mecânica: a-gol ⊂ finalizações) e
finalizações↔escanteios (+0.30). **Impedimentos e cartões são idiossincráticos** (≈0 com tudo).

**Reforço do veredito:** combos entre contagens OFENSIVAS (ex.: "mais de X finalizações E mais
de Y a-gol", ou finalizações+escanteios) são **fortemente correlacionados** e hoje precificados
como independentes — a odd combinada do "Monte sua Aposta" **superestima muito** a dificuldade.
Aplicar a cópula (Σ 5×5, ou ao menos o bloco ofensivo 3×3) é a melhoria de produção mais clara
e de baixo risco desta bateria.

