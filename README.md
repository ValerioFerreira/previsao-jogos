# Previsão de Jogos - Monorepo (Next.js + FastAPI)

Bem-vindo ao repositório unificado. O projeto agora conta com a seguinte estrutura:
- `/frontend`: Aplicação Next.js (pronta para deploy na Vercel).
- `/backend`: API em FastAPI (pronta para deploy no Railway).

## Como Rodar Localmente

A raiz do projeto foi configurada com um script `concurrently` para subir simultaneamente o frontend e o backend no mesmo terminal.

1. Instale as dependências raiz (que inclui o `concurrently`):
   ```bash
   npm install
   ```
2. Caso ainda não tenha feito, instale as dependências de cada projeto (use o comando raiz que facilita isso):
   ```bash
   npm run install:all
   ```
3. Inicie os dois ambientes ao mesmo tempo:
   ```bash
   npm run dev
   ```

O frontend estará em `http://localhost:3000` e o backend em `http://localhost:8000`.

---


# Previsao de Jogos

Aplicacao web para previsao de partidas de selecoes. O projeto foi dividido em duas partes:

- `api/`: API REST em FastAPI para Railway, reaproveitando `predictor.py` e os artefatos scikit-learn.
- `web/`: front-end Next.js App Router, React, TypeScript e Tailwind CSS para Vercel.

## Arquitetura

O back-end carrega os modelos em `api/model_artifacts/` e chama o `Predictor` original. A API apenas valida entrada, expõe endpoints REST e adiciona um bloco de odds justas calculadas a partir das probabilidades/quantis retornados pelo modelo.

Endpoints:

- `GET /health`: status da API.
- `GET /teams`: selecoes e competicoes disponiveis.
- `GET /team/{nome}`: snapshot automatico de uma selecao.
- `GET /h2h?home=&away=`: resumo de confronto direto.
- `POST /predict`: previsao completa da partida.

## Rodar Localmente

API:

```bash
cd api
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Front:

```bash
cd web
npm install
copy .env.example .env.local
npm run dev
```

Configure `web/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Odds Justas

Para mercados com probabilidade direta, a odd justa e:

```text
odd_justa = 1 / probabilidade
```

A faixa de odd usa o intervalo analitico de probabilidade em 80%. Como os classificadores do `predictor.py` nao expõem quantis proprios de probabilidade, a API preserva a probabilidade do modelo e cria uma faixa conservadora usando tamanho de treino e forca da previsao. Quanto maior a confianca, mais estreita a faixa.

Para alvos numericos, como gols, finalizacoes e escanteios, o modelo entrega estimativa e quantis 10/50/90. A API deriva uma linha proxima da estimativa e aproxima a probabilidade de over/under com uma normal ajustada pelos quantis existentes. Se o intervalo quantilico nao permitir uma estimativa honesta, a API retorna o motivo em vez de forcar uma odd.

As odds exibidas nao incluem margem da casa. Elas servem como referencia analitica para comparar com odds de mercado, nao como recomendacao de aposta. Nenhuma previsao garante resultado.

## Fidelidade

O script abaixo compara a resposta do endpoint FastAPI com a chamada direta ao `predictor.py`, ignorando apenas o bloco adicional `odds`.

```bash
python scripts/validate_fidelity.py
```

Casos validados:

- Brazil x Argentina, campo neutro, Copa do Mundo
- France x England, campo neutro, Copa do Mundo

Resultado atual:

```text
[OK] Brazil x Argentina: respostas identicas
[OK] France x England: respostas identicas
```

## Deploy no Railway

1. Crie um novo projeto no Railway a partir do repositorio GitHub.
2. Configure o root directory como `api`.
3. O Railway usara o `Dockerfile` e `railway.json`.
4. Configure variaveis:

```env
CORS_ORIGINS=https://sua-url-vercel.vercel.app
```

5. Comando de start:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

6. Healthcheck: `/health`.

## Deploy na Vercel

1. Importe o mesmo repositorio na Vercel.
2. Configure o root directory como `web`.
3. Configure a variavel:

```env
NEXT_PUBLIC_API_URL=https://sua-api-railway.up.railway.app
```

4. Build command: `npm run build`.
5. Output/framework: Next.js.

## Publicar no GitHub

O repositorio remoto esperado e:

```bash
git remote add origin https://github.com/ValerioFerreira/previsao-jogos.git
git branch -M main
git add .
git commit -m "Transforma previsao em API FastAPI e front Next"
git push -u origin main
```

