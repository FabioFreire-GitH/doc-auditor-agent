"""
tests/test_sprint2.py
=====================
Validação do Sprint 2: Persistência e Pipeline.

ESTRUTURA DOS TESTES:
    Teste 1: Banco de dados — tabelas e engine
    Teste 2: Repository — CRUD de MonitoredSource
    Teste 3: Repository — Snapshots e detecção de mudança
    Teste 4: Repository — Alertas e filtros
    Teste 5: Pipeline — primeira execução (cria baseline, sem IA)
    Teste 6: Pipeline — segunda execução (hash igual, IA não chamada)
    Teste 7: Pipeline — fonte com URL inválida (tratamento de erro)

BANCO DE TESTES:
    Usamos SQLite em memória (:memory:) para não poluir o sentinel.db.
    Cada teste recebe uma sessão limpa e isolada.
"""

import sys
import os

# Adiciona o diretório raiz ao path para importar os módulos do projeto
# Mesmo padrão usado em test_sprint1.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine

from sqlalchemy.orm import sessionmaker

# Banco em memória para testes — isolado do sentinel.db real
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Importa os models e cria as tabelas no banco de teste
from database.database import Base
from database import models  # registra os models na Base
from database import repository as repo
from database.models import MonitoredSource, DocumentSnapshot, ChangeAlert

Base.metadata.create_all(bind=test_engine)


# =============================================================================
# UTILITÁRIOS
# =============================================================================

def separador(titulo: str):
    print("\n" + "=" * 60)
    print(f"  {titulo}")
    print("=" * 60)


def ok(msg: str):
    print(f"  OK: {msg}")


def falhou(msg: str):
    print(f"  FALHOU: {msg}")
    sys.exit(1)


def nova_sessao():
    """Retorna uma sessão limpa para cada teste."""
    return TestSessionLocal()


# =============================================================================
# TESTE 1 — Banco de dados: tabelas e engine
# =============================================================================

def teste_banco_tabelas():
    separador("TESTE 1: Banco — tabelas criadas corretamente")

    tabelas = list(Base.metadata.tables.keys())

    for esperada in ["monitored_sources", "document_snapshots", "change_alerts"]:
        if esperada not in tabelas:
            falhou(f"Tabela '{esperada}' nao encontrada. Tabelas: {tabelas}")

    ok(f"3 tabelas encontradas: {', '.join(tabelas)}")

    with nova_sessao() as db:
        # Banco vazio no início
        total = db.query(MonitoredSource).count()
        assert total == 0, f"Esperava 0 fontes, encontrou {total}"
        ok("Banco iniciado vazio")


# =============================================================================
# TESTE 2 — Repository: CRUD de MonitoredSource
# =============================================================================

def teste_repository_sources():
    separador("TESTE 2: Repository — CRUD de MonitoredSource")

    with nova_sessao() as db:
        # Criar
        fonte = repo.create_source(
            db,
            name="Mercado Livre - Orders",
            url="https://api.mercadolivre.com/docs/orders",
            check_interval_minutes=720,
        )
        assert fonte.id is not None
        assert fonte.is_active is True
        assert fonte.check_interval_minutes == 720
        ok(f"Fonte criada: id={fonte.id}, name='{fonte.name}'")

        # Buscar por URL
        encontrada = repo.get_source_by_url(db, "https://api.mercadolivre.com/docs/orders")
        assert encontrada is not None
        assert encontrada.id == fonte.id
        ok("get_source_by_url() retornou a fonte correta")

        # Duplicata deve lançar ValueError
        try:
            repo.create_source(db, name="Duplicata", url="https://api.mercadolivre.com/docs/orders")
            falhou("Deveria ter lancado ValueError para URL duplicada")
        except ValueError as e:
            ok(f"URL duplicada bloqueada corretamente: {e}")

        # Listar fontes ativas
        ativas = repo.get_active_sources(db)
        assert len(ativas) == 1
        ok(f"get_active_sources() retornou {len(ativas)} fonte ativa")

        # Desativar
        repo.update_source_status(db, fonte.id, is_active=False)
        ativas = repo.get_active_sources(db)
        assert len(ativas) == 0
        ok("Fonte desativada — get_active_sources() retorna 0")

        # Reativar
        repo.update_source_status(db, fonte.id, is_active=True)
        ativas = repo.get_active_sources(db)
        assert len(ativas) == 1
        ok("Fonte reativada — get_active_sources() retorna 1")


# =============================================================================
# TESTE 3 — Repository: Snapshots e detecção de mudança
# =============================================================================

def teste_repository_snapshots():
    separador("TESTE 3: Repository — Snapshots e detecção de mudança")

    with nova_sessao() as db:
        # Setup: criar uma fonte
        fonte = repo.create_source(db, name="Stripe Charges", url="https://stripe.com/docs/api/charges")

        # Sem snapshot anterior, get_latest_snapshot deve retornar None
        ultimo = repo.get_latest_snapshot(db, fonte.id)
        assert ultimo is None
        ok("Primeira execucao: get_latest_snapshot() retorna None (sem baseline)")

        # Salvar primeiro snapshot (baseline)
        snap1 = repo.save_snapshot(
            db,
            source_id=fonte.id,
            content_hash="hash_v1_aaabbbccc",
            content_text="# Charges API\nEndpoint: POST /v1/charges\n",
        )
        assert snap1.id is not None
        ok(f"Baseline salvo: snapshot id={snap1.id}, hash='{snap1.content_hash[:12]}...'")

        # get_latest_snapshot deve retornar o baseline
        ultimo = repo.get_latest_snapshot(db, fonte.id)
        assert ultimo.id == snap1.id
        ok("get_latest_snapshot() retornou o baseline correto")

        # Salvar segundo snapshot (mudança)
        snap2 = repo.save_snapshot(
            db,
            source_id=fonte.id,
            content_hash="hash_v2_xxxyyynnn",
            content_text="# Charges API\nEndpoint: POST /v1/charges\nNovo campo: tax_id (obrigatorio)\n",
        )

        # get_latest_snapshot deve retornar o mais RECENTE (snap2)
        ultimo = repo.get_latest_snapshot(db, fonte.id)
        assert ultimo.id == snap2.id
        ok(f"get_latest_snapshot() retorna sempre o mais recente (id={snap2.id})")

        # Verificar que temos 2 snapshots no banco para esta fonte
        total = db.query(DocumentSnapshot).filter(DocumentSnapshot.source_id == fonte.id).count()
        assert total == 2
        ok(f"2 snapshots salvos no banco para a fonte id={fonte.id}")


# =============================================================================
# TESTE 4 — Repository: Alertas e filtros
# =============================================================================

def teste_repository_alertas():
    separador("TESTE 4: Repository — Alertas e filtros")

    with nova_sessao() as db:
        fonte = repo.create_source(db, name="Shopify Orders", url="https://shopify.dev/api/admin-rest/orders")
        snap = repo.save_snapshot(db, source_id=fonte.id, content_hash="hash_shopify_v2", content_text="novo conteudo")

        # Salvar alerta relevante (breaking change)
        alerta1 = repo.save_alert(
            db,
            source_id=fonte.id,
            snapshot_id=snap.id,
            has_relevant_changes=True,
            is_breaking_change=True,
            severity="CRITICA",
            summary_ptbr="Endpoint /orders foi depreciado.",
            affected_endpoints=["/orders", "/orders/{id}"],
            recommended_action="Migrar para /orders/v2 antes de 01/12.",
        )
        assert alerta1.id is not None
        ok(f"Alerta CRITICA salvo: id={alerta1.id}")

        # Serialização de lista de endpoints
        assert "/orders, /orders/{id}" == alerta1.affected_endpoints
        ok(f"Endpoints serializados: '{alerta1.affected_endpoints}'")

        # Salvar alerta não relevante (cosmético)
        alerta2 = repo.save_alert(
            db,
            source_id=fonte.id,
            snapshot_id=snap.id,
            has_relevant_changes=False,
            is_breaking_change=False,
            severity="BAIXA",
            summary_ptbr="Atualizacao de copyright.",
            affected_endpoints=[],
            recommended_action="Nenhuma acao necessaria.",
        )
        ok(f"Alerta BAIXA salvo: id={alerta2.id}")

        # Filtro: apenas relevantes
        relevantes = repo.get_alerts(db, only_relevant=True)
        assert len(relevantes) == 1
        assert relevantes[0].severity == "CRITICA"
        ok(f"get_alerts(only_relevant=True): {len(relevantes)} alerta (correto)")

        # Filtro: não notificados
        nao_notificados = repo.get_alerts(db, only_unnotified=True)
        assert len(nao_notificados) == 2
        ok(f"get_alerts(only_unnotified=True): {len(nao_notificados)} alertas pendentes")

        # Marcar como notificado
        repo.mark_alert_as_notified(db, alerta1.id)
        nao_notificados = repo.get_alerts(db, only_unnotified=True)
        assert len(nao_notificados) == 1
        ok(f"Apos mark_alert_as_notified(): {len(nao_notificados)} pendente restante")


# =============================================================================
# TESTE 5 — Pipeline: primeira execução (cria baseline, sem IA)
# =============================================================================

def teste_pipeline_primeira_execucao():
    separador("TESTE 5: Pipeline — primeira execucao (baseline, sem IA)")
    print("  Cadastrando fonte real e rodando pipeline pela primeira vez...")
    print("  (Faz download da URL — aguarde alguns segundos)")

    from database.database import SessionLocal, Base, engine
    from database import models as _models
    from pipeline.workflow import check_source

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        # Limpa se já existir para garantir teste limpo
        existente = repo.get_source_by_url(db, "https://stripe.com/docs/api/charges/object")
        if not existente:
            fonte = repo.create_source(
                db,
                name="Stripe - Charge Object",
                url="https://stripe.com/docs/api/charges/object",
            )
        else:
            fonte = existente

        # Remove snapshots anteriores para simular primeira execução
        db.query(DocumentSnapshot).filter(DocumentSnapshot.source_id == fonte.id).delete()
        db.commit()

        resultado = check_source(db, fonte)

        assert resultado.error is None, f"Erro inesperado: {resultado.error}"
        assert resultado.changed is False, "Primeira execucao nao deve sinalizar 'changed'"

        # Deve ter salvo o baseline
        baseline = repo.get_latest_snapshot(db, fonte.id)
        assert baseline is not None
        ok(f"Baseline salvo: hash='{baseline.content_hash[:12]}...', {len(baseline.content_text)} chars")
        ok("IA nao foi chamada (primeira execucao = apenas baseline)")


# =============================================================================
# TESTE 6 — Pipeline: segunda execução (hash igual, IA não chamada)
# =============================================================================

def teste_pipeline_sem_mudanca():
    separador("TESTE 6: Pipeline — segunda execucao (hash igual, IA nao chamada)")
    print("  Rodando pipeline pela segunda vez na mesma URL...")
    print("  (Faz download da URL — aguarde alguns segundos)")

    from database.database import SessionLocal
    from pipeline.workflow import check_source

    with SessionLocal() as db:
        fonte = repo.get_source_by_url(db, "https://stripe.com/docs/api/charges/object")
        assert fonte is not None, "Fonte do Teste 5 nao encontrada — execute os testes em ordem"

        snap_antes = repo.get_latest_snapshot(db, fonte.id)
        resultado = check_source(db, fonte)

        assert resultado.error is None, f"Erro inesperado: {resultado.error}"
        assert resultado.changed is False
        assert resultado.relevant is None  # IA não foi chamada

        snap_depois = repo.get_latest_snapshot(db, fonte.id)
        assert snap_antes.id == snap_depois.id, "Novo snapshot foi salvo desnecessariamente!"

        ok("Hash identico — IA nao chamada, nenhum snapshot extra criado")
        ok(f"Resultado: {resultado}")


# =============================================================================
# TESTE 7 — Pipeline: URL inválida (tratamento de erro gracioso)
# =============================================================================

def teste_pipeline_url_invalida():
    separador("TESTE 7: Pipeline — URL invalida (erro gracioso)")

    from database.database import SessionLocal
    from pipeline.workflow import check_source

    with SessionLocal() as db:
        # Criar fonte com URL inválida
        existente = repo.get_source_by_url(db, "https://url-que-nao-existe-sentinel-test.invalid/docs")
        if not existente:
            fonte = repo.create_source(
                db,
                name="URL Invalida TEST",
                url="https://url-que-nao-existe-sentinel-test.invalid/docs",
            )
        else:
            fonte = existente

        resultado = check_source(db, fonte)

        # Deve retornar erro sem lançar exceção (pipeline continua para outras fontes)
        assert resultado.error is not None
        assert resultado.changed is False
        ok(f"Erro tratado graciosamente: '{resultado.error}'")
        ok("Pipeline nao travou — continuaria para proxima fonte")

        # Limpa a fonte de teste
        db.delete(fonte)
        db.commit()


# =============================================================================
# EXECUÇÃO PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    print("\n=== API Doc Sentinel - Validacao do Sprint 2: Persistencia e Pipeline ===")
    print("Aguarde... alguns testes fazem download de URLs reais.\n")

    teste_banco_tabelas()
    teste_repository_sources()
    teste_repository_snapshots()
    teste_repository_alertas()
    teste_pipeline_primeira_execucao()
    teste_pipeline_sem_mudanca()
    teste_pipeline_url_invalida()

    print("\n" + "=" * 60)
    print("  Sprint 2 validado com sucesso!")
    print("  Proximo passo: Sprint 3 — Notificacoes e Scheduler")
    print("=" * 60 + "\n")
