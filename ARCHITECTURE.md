# System Architecture

Este documento descreve a arquitetura técnica, a estratégia de infraestrutura e os fluxos de dados do projeto de Previsão de Jogos.

## 1. Visão Geral da Arquitetura (Monorepo)

O projeto está organizado em um **Monorepo**, dividindo claramente as responsabilidades de interface e processamento de dados. 

- **`/frontend`**: Desenvolvido em **Next.js (TypeScript)**. Responsável pela interface do usuário, consome a API do backend para exibir previsões, estatísticas e históricos.
- **`/backend`**: Desenvolvido em **Python (FastAPI)**. Lida com a coleta de dados de terceiros, execução de scripts de ETL, treinamento/inferência de modelos de Machine Learning e disponibiliza endpoints de API rápidos.

**Desenvolvimento Local**:
O repositório possui um `package.json` na raiz configurado com o `concurrently`. Para rodar todo o sistema (Frontend e Backend) simultaneamente em ambiente de desenvolvimento, basta executar:
```bash
npm run dev
```

## 2. Estratégia de Deploy

A infraestrutura foi desenhada para otimização de custos e performance, hospedando cada serviço em provedores especializados:

- **Frontend (Vercel)**:
  - Hospedado nativamente na Vercel para tirar proveito da CDN global do Next.js.
  - A comunicação com o backend é gerenciada pela variável de ambiente `NEXT_PUBLIC_API_URL` (ex: `https://api-previsao-jogos.onrender.com`).

- **Backend (Render / Railway)**:
  - Hospedado como um Web Service.
  - O diretório raiz no Render deve ser configurado como `/backend`.
  - **Porta Dinâmica**: O servidor `uvicorn` roda com `--host 0.0.0.0` e escuta a porta definida pelo ambiente (`process.env.PORT` ou configuração interna do Render/Railway).
  - **CORS**: O acesso ao backend é estritamente controlado via CORS, aceitando tráfego apenas da origem oficial do frontend através da variável `FRONTEND_URL`. (No ambiente local, `http://localhost:3000` é permitido por fallback).

## 3. Arquitetura de Banco de Dados (Neon Serverless PostgreSQL)

Anteriormente, o sistema utilizava armazenamento efêmero local (arquivos JSON, CSV e Parquet). Como provedores de hospedagem serverless/PaaS possuem discos temporários, a persistência de dados foi migrada para o **Neon PostgreSQL Serverless**.

### Gerenciamento de Conexão e Escalabilidade
O banco de dados é gerenciado via `SQLAlchemy`. Devido ao comportamento "Serverless" do Neon (que suspende a instância após inatividade para economizar custos), a Engine do SQLAlchemy é configurada com estratégias de mitigação:
- **`pool_pre_ping=True`**: Verifica passivamente a saúde da conexão TCP antes de enviar a consulta. Se a conexão for fechada por inatividade da Neon, o pool reestabelece uma nova automaticamente.
- **Dimensionamento de Pool**: Conexões limitadas (`pool_size=5`, `max_overflow=10`) para prevenir gargalos simultâneos pesados.

### Estratégias de Escrita (ETL)

O módulo de conexão ( `app.db.connection` ) exporta funções avançadas para garantir atualizações íntegras em produção:

1. **`upsert_df`**:
   - Utilizado para atualizações incrementais contínuas (ex: logs, telemetria).
   - Baseia-se em `on_conflict_do_update` (Upsert nativo do PostgreSQL), garantindo que dados duplicados não existam sem onerar a memória com deleções em lote.

2. **`truncate_and_append`** (Atomicidade Crítica):
   - Utilizado pelos pesados pipelines de ML que regeneram históricos inteiros (`build_history.py`, `build_final_dataset.py`).
   - Diferente do destrutivo `df.to_sql(if_exists='replace')`, esta função mantém a estrutura e os índices essenciais.
   - **Garantia Transacional**: O comando cru de `TRUNCATE TABLE` e o respectivo `append` ocorrem estritamente na *mesma transação SQL*. Se a inserção de dados falhar por formatação incorreta, o `TRUNCATE` sofre rollback, impedindo que a API do frontend quebre por consultar uma tabela acidentalmente vazia.

### Estratégia de Cache via JSONB (Raw Data Lake)
O script massivo de extração de fixtures (`fetch_apifootball.py`) consome milhares de retornos crus JSON das APIs de terceiros.
- Eles são armazenados no PostgreSQL em uma coluna `JSONB` no formato de "Raw Data Lake".
- **Performance**: A API em tempo real (`predictor_service.py`) **nunca** processa ou consulta essas tabelas JSONB. O Data Lake serve exclusivamente de repositório bruto para os pipelines noturnos e de ETL, que os mastigam e salvam de volta em tabelas estruturadas (ex: `matches`) onde a API principal performa leituras analíticas rápidas.

## 4. Referência de Variáveis de Ambiente

Ao clonar o projeto, devem ser criados os arquivos `.env` nas respectivas pastas.

### `/frontend/.env`
```env
# URL da API do backend de produção (sem / no final)
NEXT_PUBLIC_API_URL=https://sua-api.onrender.com
```

### `/backend/.env`
```env
# URL oficial de conexão do banco de dados (Neon PostgreSQL)
DATABASE_URL=postgresql://user:password@ep-cool-sun-1234.us-east-2.aws.neon.tech/dbname?sslmode=require

# Origem oficial permitida do Frontend (para bloqueio de segurança CORS)
FRONTEND_URL=https://seu-frontend-producao.vercel.app

# Porta de escuta do Uvicorn (Opcional, Render gerencia isso dinamicamente)
PORT=8000

# Chaves de API de Terceiros utilizadas nos coletores ETL
API_FOOTBALL_KEY=your_api_football_key
```
