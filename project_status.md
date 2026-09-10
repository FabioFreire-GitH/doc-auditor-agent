# API Doc Sentinel — Status do Projeto

## O que é este projeto

Um **serviço autônomo de auditoria de documentação técnica** para times de desenvolvimento de e-commerce e marketplaces.

**Fluxo completo previsto:**
```
Scheduler → Extrator (HTTP/HTML→Markdown) → Hasher (SHA-256) → 
  → [sem mudança: para aqui, zero custo] 
  → [com mudança: Agente IA (Agno + Gemini)] → 
  → Pydantic (JSON estruturado) → Banco (SQLite) → E-mail → UI (Streamlit)
```

**Stack:** Python 3.12 · Agno · Google Gemini · SQLite · SQLAlchemy · FastAPI · APScheduler · Streamlit

---

## ✅ Sprint 1 — Motor de Inteligência e Extração (CONCLUÍDO)

| Arquivo | Status | O que faz |
|---|---|---|
| [`core/__init__.py`](file:///c:/Users/Fabio/Documents/Projetos/projetos_agentes/doc-auditor-agent/core/__init__.py) | ✅ | Marca o pacote |
| [`core/extractor.py`](file:///c:/Users/Fabio/Documents/Projetos/projetos_agentes/doc-auditor-agent/core/extractor.py) | ✅ | httpx + BeautifulSoup4 + html2text → Markdown limpo |
| [`core/hasher.py`](file:///c:/Users/Fabio/Documents/Projetos/projetos_agentes/doc-auditor-agent/core/hasher.py) | ✅ | SHA-256 do texto, detecta mudança antes de chamar a IA |
| [`core/agent.py`](file:///c:/Users/Fabio/Documents/Projetos/projetos_agentes/doc-auditor-agent/core/agent.py) | ✅ | Agno Agent + Gemini + schema Pydantic `APIDocAnalysis` |
| [`tests/test_sprint1.py`](file:///c:/Users/Fabio/Documents/Projetos/projetos_agentes/doc-auditor-agent/tests/test_sprint1.py) | ✅ | 5 testes validados (hash, cosmético, técnico, breaking, URL real) |

### Ajustes feitos durante o Sprint 1
- `response_model` → `output_model` → `output_schema` (agno atualizou a API)
- Removido `output_schema` do Agent (validava internamente e quebrava em erros 503)
- Parsing JSON manual com `model_validate_json()` — controle total
- Retry com backoff exponencial (3 tentativas: 5s, 10s, 20s) para erros 503
- Modelo atualizado de `gemini-2.0-flash` → `gemini-2.5-flash` → `gemini-3.1-pro-preview`

> [!NOTE]
> O modelo `gemini-2.5-flash` gerava 503 frequentes em testes consecutivos.
> `gemini-2.5-pro` foi descontinuado para novos usuários.
> Atualmente configurado: `gemini-3.1-pro-preview` (sugerido pela API Google).

---

## ⬜ Sprint 2 — Persistência e Pipeline (PRÓXIMO)

O sistema precisa de "memória". Sem isso, toda execução é cega — não sabe o que já viu.

### Arquivos a criar

| Arquivo | O que faz |
|---|---|
| `database/database.py` | Engine SQLAlchemy, cria `sentinel.db` local |
| `database/models.py` | 3 tabelas: `MonitoredSources`, `DocumentSnapshots`, `ChangeAlerts` |
| `database/repository.py` | CRUD: buscar fontes, salvar snapshot, buscar último snapshot, salvar alerta |
| `pipeline/workflow.py` | Orquestra tudo: fontes → extrai → hash → compara → agente → salva |

### Esquema de dados

```
MonitoredSources       DocumentSnapshots          ChangeAlerts
─────────────────      ───────────────────────    ─────────────────────────
id (PK)                id (PK)                    id (PK)
url                    source_id (FK)             source_id (FK)
name                   content_hash               snapshot_id (FK)
check_interval_min     content_text               has_relevant_changes
is_active              scraped_at                 is_breaking_change
created_at             ─────────────────────────  severity
                                                   summary_ptbr
                                                   affected_endpoints
                                                   recommended_action
                                                   created_at
```

---

## ⬜ Sprint 3 — Orquestração, Backend e Notificações

| Arquivo | O que faz |
|---|---|
| `notifications/email_sender.py` | Gmail SMTP, e-mail HTML com severidade destacada |
| `scheduler/scheduler.py` | APScheduler: roda `workflow.py` em intervalos por URL |
| `api/routes.py` | FastAPI: CRUD de fontes, trigger manual, listagem de alertas |
| `main.py` | Entry point: FastAPI + Scheduler integrado |

---

## ⬜ Sprint 4 — Painel Administrativo (Streamlit)

| Arquivo | O que faz |
|---|---|
| `app/streamlit_app.py` | 3 abas: Monitoramento · Alertas · Cadastrar URL |
| `README.md` | Documentação completa de instalação e uso |

---

## Estrutura atual vs. planejada

```
doc-auditor-agent/
├── core/           ✅ completo (extractor, hasher, agent)
├── database/       ⬜ apenas __init__.py — Sprint 2
├── pipeline/       ⬜ apenas __init__.py — Sprint 2
├── notifications/  ⬜ apenas __init__.py — Sprint 3
├── scheduler/      ⬜ apenas __init__.py — Sprint 3
├── api/            ⬜ apenas __init__.py — Sprint 3
├── app/            ⬜ vazio              — Sprint 4
├── tests/          ✅ test_sprint1.py
├── .env            ✅ configurado
├── .env.example    ✅ atualizado
├── pyproject.toml  ✅ todas dependências declaradas
└── implementation_plan.md ✅
```

---

## Recomendação de próximo passo

**Iniciar Sprint 2** na seguinte ordem:
1. `database/database.py` + `database/models.py` (base de tudo)
2. `database/repository.py` (funções de acesso)
3. `pipeline/workflow.py` (orquestrador completo)
4. Validar com `python -c "from pipeline.workflow import run_pipeline; run_pipeline()"`
