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

## ✅ Sprint 2 — Persistência e Pipeline (CONCLUÍDO)

O sistema agora tem "memória". Ele guarda o hash e o snapshot completo de cada versão da documentação para não chamar a IA desnecessariamente.

### Arquivos criados

| Arquivo | O que faz |
|---|---|
| `database/database.py` | ✅ Engine SQLAlchemy, cria `sentinel.db` local e `SessionLocal` |
| `database/models.py` | ✅ 3 tabelas criadas: `MonitoredSource`, `DocumentSnapshot`, `ChangeAlert` |
| `database/repository.py` | ✅ Funções CRUD isoladas e limpas |
| `pipeline/workflow.py` | ✅ Orquestrador `run_pipeline()` com tratamento gracioso de erros |
| `tests/test_sprint2.py`| ✅ Suíte de validação do banco e workflow |

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

## ✅ Sprint 3 — Orquestração, Backend e Notificações (CONCLUÍDO)

A API REST agora funciona como o cérebro que interliga o banco, o agendador e o motor.

| Arquivo | O que faz |
|---|---|
| `notifications/email_sender.py` | ✅ Gmail SMTP, e-mail HTML com severidade destacada e badges |
| `scheduler/scheduler.py` | ✅ APScheduler: roda o `workflow.py` de hora em hora em background |
| `api/routes.py` | ✅ Rotas da API FastAPI para cadastrar fontes, disparar scans e ler alertas |
| `main.py` | ✅ Ponto de entrada (Entry point) com gerência do ciclo de vida |

---

## ✅ Sprint 4 — Painel Administrativo (Streamlit) (CONCLUÍDO)

A interface visual está pronta! Qualquer pessoa agora pode operar o sistema sem olhar código.

| Arquivo | O que faz |
|---|---|
| `app/streamlit_app.py` | ✅ 3 abas: Monitoramento (listar/status/check), Alertas (visualizar coloridos) e Cadastro. |
| `README.md` | ✅ Documentação completa de instalação, configuração e uso (2 terminais). |

---

## Estrutura atual vs. planejada

```
doc-auditor-agent/
├── core/           ✅ completo (extractor, hasher, agent)
├── database/       ✅ completo (database, models, repository)
├── pipeline/       ✅ completo (workflow)
├── notifications/  ✅ completo (email_sender)
├── scheduler/      ✅ completo (scheduler)
├── api/            ✅ completo (routes)
├── main.py         ✅ entry point configurado
├── app/            ✅ completo (streamlit_app)
├── tests/          ✅ completos (sprint1, sprint2 e sprint3)
├── .env            ✅ configurado
├── .env.example    ✅ atualizado
├── pyproject.toml  ✅ todas dependências declaradas
└── implementation_plan.md ✅
```

---

## Recomendação de próximo passo

**PROJETO 100% FINALIZADO! 🎉**
Todos os Sprints (1, 2, 3 e 4) foram entregues com sucesso.
O sistema agora possui desde o motor de IA até um frontend limpo.

**Como rodar em definitivo (2 terminais necessários):**
1. Backend: `uv run uvicorn main:app`
2. Frontend: `uv run streamlit run app/streamlit_app.py`
