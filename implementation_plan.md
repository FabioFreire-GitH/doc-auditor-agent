# API Doc Sentinel — Plano de Implementação Completo

Um serviço híbrido (determinístico + agentes de IA com Agno) que monitora periodicamente
páginas de documentação técnica, filtra alterações cosméticas e notifica apenas impactos reais
de engenharia via e-mail.

**Stack**: Python + Agno + Google Gemini + SQLite + APScheduler + FastAPI + Streamlit

---

## Stack e Decisões Técnicas

| Decisão | Escolha | Motivo |
|---|---|---|
| LLM | Google Gemini (gemini-2.0-flash) | Chave disponível, custo baixo, bom suporte no Agno |
| Banco | SQLite (dev) | Sem servidor, zero configuração, arquivo local |
| Notificação | E-mail via Gmail SMTP | Formal, gratuito, conta já existente |
| Agendador | APScheduler | Roda no mesmo processo, sem Redis/Celery |
| Deploy | Local primeiro | Valida antes de gastar com servidor |
| Interface | Streamlit | Já conhecido, entrega valor rápido |
| ORM | SQLAlchemy | Padrão do mercado, fácil de migrar pra PostgreSQL |
| Scraping | httpx + BeautifulSoup4 | Leve, cobre 90% dos casos estáticos |

---

## Estrutura de Pastas Final

```
doc-auditor-agent/
│
├── core/
│   ├── __init__.py
│   ├── extractor.py        # Baixa e limpa HTML das páginas
│   ├── hasher.py           # Calcula SHA-256, detecta mudança
│   └── agent.py            # Agente Agno + Gemini + Pydantic
│
├── database/
│   ├── __init__.py
│   ├── models.py           # Tabelas SQLAlchemy
│   ├── database.py         # Conexão e engine
│   └── repository.py       # Funções de salvar/buscar dados
│
├── pipeline/
│   ├── __init__.py
│   └── workflow.py         # Orquestra tudo em sequência
│
├── notifications/
│   ├── __init__.py
│   └── email_sender.py     # Envia e-mail formatado com HTML
│
├── scheduler/
│   ├── __init__.py
│   └── scheduler.py        # APScheduler rodando periodicamente
│
├── api/
│   ├── __init__.py
│   └── routes.py           # FastAPI: trigger manual + consultas
│
├── app/
│   └── streamlit_app.py    # Painel de controle visual
│
├── tests/
│   └── test_sprint1.py     # Teste rápido do core engine
│
├── .env.example            # Template de variáveis de ambiente
├── .gitignore              # Protege .env e dados sensíveis
├── requirements.txt        # Dependências do projeto
├── main.py                 # Ponto de entrada (FastAPI + Scheduler)
└── README.md               # Documentação do projeto
```

---

## Sprint 1 — Motor de Inteligência e Extração

### Objetivo
Script funcional que: baixa HTML → limpa → calcula hash → compara →
chama Agno/Gemini apenas se mudou → retorna JSON estruturado.

### Arquivos

#### [NEW] `core/__init__.py`
#### [NEW] `core/extractor.py`
Usa httpx + BeautifulSoup4 para baixar a página, isolar o conteúdo principal
(`<main>`, `<article>`, `<div class="content">`) e converter para Markdown limpo.

#### [NEW] `core/hasher.py`
Calcula SHA-256 do texto limpo. Função pura, zero dependência externa.

#### [NEW] `core/agent.py`
Configura o Agent do Agno com:
- modelo Gemini (via `agno.models.google`)
- schema Pydantic `APIDocAnalysis`
- instruções estritas de auditoria técnica

#### [NEW] `tests/test_sprint1.py`
Script de teste com dois textos simulados: um idêntico (não chama IA)
e um com mudança de payload (chama IA e imprime resultado).

---

## Sprint 2 — Persistência e Pipeline de Dados

### Objetivo
O sistema tem "memória". Guarda snapshots no SQLite. Pipeline busca versão
anterior, compara com scrape atual, salva nova versão se mudou.

### Arquivos

#### [NEW] `database/__init__.py`
#### [NEW] `database/database.py`
Engine SQLAlchemy, criação do banco `sentinel.db` local.

#### [NEW] `database/models.py`
Três tabelas:
- `MonitoredSources` — URLs cadastradas para monitorar
- `DocumentSnapshots` — Histórico de versões (hash + conteúdo)
- `ChangeAlerts` — Alertas gerados pela IA

#### [NEW] `database/repository.py`
Funções de acesso ao banco: buscar fontes ativas, salvar snapshot,
buscar último snapshot, salvar alerta.

#### [NEW] `pipeline/workflow.py`
Orquestra: busca fontes → extrai → calcula hash → compara →
chama agente → salva alerta → retorna resultado.

---

## Sprint 3 — Orquestração, Backend e Notificações

### Objetivo
Sistema autônomo. Roda de hora em hora sem intervenção manual.
Quando detecta mudança técnica, envia e-mail formatado.

### Arquivos

#### [NEW] `notifications/email_sender.py`
Gmail SMTP via `smtplib`. E-mail HTML formatado com:
- Nível de severidade destacado (cores)
- Resumo da mudança
- Endpoints afetados
- Ação recomendada

#### [NEW] `scheduler/scheduler.py`
APScheduler com BackgroundScheduler. Roda `workflow.py` em intervalos
configuráveis por URL. Integra com FastAPI via lifespan.

#### [NEW] `api/routes.py`
FastAPI com rotas:
- `POST /api/sources` — Cadastrar nova URL
- `GET /api/sources` — Listar fontes monitoradas
- `POST /api/check-now/{source_id}` — Trigger manual
- `GET /api/alerts` — Listar alertas gerados

#### [NEW] `main.py`
Ponto de entrada: inicializa banco, sobe FastAPI com scheduler integrado.

#### [NEW] `.env.example`
Template com todas as variáveis necessárias.

#### [NEW] `requirements.txt`
Todas as dependências do projeto.

---

## Sprint 4 — Painel Administrativo (Streamlit)

### Objetivo
Interface visual para qualquer pessoa do time cadastrar URLs,
disparar verificações e acompanhar alertas.

### Arquivos

#### [NEW] `app/streamlit_app.py`
Painel com 3 abas:
1. **Monitoramento** — tabela de URLs cadastradas, status, última verificação
2. **Alertas** — feed de alertas com filtros de severidade
3. **Cadastrar** — formulário para adicionar nova URL

#### [MODIFY] `README.md`
Documentação completa: instalação, configuração, uso, deploy.

---

## Verification Plan

### Automated Tests
```bash
# Sprint 1: testa o core engine com textos simulados
python tests/test_sprint1.py

# Sprint 2: testa pipeline com URL real
python -c "from pipeline.workflow import run_pipeline; run_pipeline()"

# Sprint 3: testa envio de e-mail
python -c "from notifications.email_sender import send_test_email; send_test_email()"

# Sprint 4: sobe o Streamlit
streamlit run app/streamlit_app.py
```

### Manual Verification
- Cadastrar 2-3 URLs reais de documentação (Mercado Livre, Stripe, Shopify)
- Aguardar primeira execução automática do scheduler
- Verificar se snapshot foi salvo no banco
- Simular mudança manualmente e confirmar que e-mail é enviado
