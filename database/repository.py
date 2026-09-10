"""
database/repository.py
======================
Funções de acesso ao banco de dados (padrão Repository).

POR QUE EXISTE:
    Nenhum outro módulo do sistema deve escrever queries SQLAlchemy diretamente.
    Toda leitura e escrita passa por aqui. Isso garante:
    - Ponto único de mudança se trocarmos de banco (SQLite → PostgreSQL)
    - Funções testáveis de forma isolada (passamos uma session mock nos testes)
    - Código do pipeline e da API limpo, sem SQL misturado com lógica de negócio

PADRÃO DE USO:
    Cada função recebe uma `Session` como primeiro argumento.
    Quem chama é responsável por criar e fechar a sessão.

    Exemplo típico no workflow:
        with SessionLocal() as db:
            fonte = get_source_by_url(db, "https://...")
            snapshot = get_latest_snapshot(db, fonte.id)

NOTA SOBRE COMMIT:
    As funções de escrita (create_*, save_*) fazem commit internamente.
    Se precisar de transação composta (múltiplos saves em um só commit),
    passe commit=False e faça o commit manualmente depois.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from database.models import ChangeAlert, DocumentSnapshot, MonitoredSource


# =============================================================================
# FONTES MONITORADAS (MonitoredSource)
# =============================================================================

def get_active_sources(db: Session) -> List[MonitoredSource]:
    """
    Retorna todas as fontes com is_active=True.

    Usada pelo scheduler para saber quais URLs checar a cada ciclo.
    """
    return db.query(MonitoredSource).filter(MonitoredSource.is_active == True).all()


def get_source_by_id(db: Session, source_id: int) -> Optional[MonitoredSource]:
    """
    Busca uma fonte pelo ID primário.

    Retorna None se não encontrar (não lança exceção).
    """
    return db.query(MonitoredSource).filter(MonitoredSource.id == source_id).first()


def get_source_by_url(db: Session, url: str) -> Optional[MonitoredSource]:
    """
    Busca uma fonte pela URL exata.

    Usada para verificar duplicatas antes de cadastrar.
    """
    return db.query(MonitoredSource).filter(MonitoredSource.url == url).first()


def create_source(
    db: Session,
    name: str,
    url: str,
    check_interval_minutes: int = 1440,
) -> MonitoredSource:
    """
    Cadastra uma nova URL para monitorar.

    Args:
        db: Sessão do banco
        name: Nome amigável (ex: "Stripe - Charges API")
        url: URL completa da documentação
        check_interval_minutes: Frequência de checagem (padrão: 1440 = 1x/dia)

    Returns:
        O objeto MonitoredSource criado e persistido no banco.

    Raises:
        ValueError: Se a URL já estiver cadastrada.
    """
    existente = get_source_by_url(db, url)
    if existente:
        raise ValueError(f"URL ja cadastrada (id={existente.id}): {url}")

    fonte = MonitoredSource(
        name=name,
        url=url,
        check_interval_minutes=check_interval_minutes,
    )
    db.add(fonte)
    db.commit()
    db.refresh(fonte)  # Recarrega o objeto com o id gerado pelo banco
    return fonte


def update_source_status(db: Session, source_id: int, is_active: bool) -> Optional[MonitoredSource]:
    """
    Ativa ou desativa o monitoramento de uma fonte sem deletá-la.
    """
    fonte = get_source_by_id(db, source_id)
    if not fonte:
        return None
    fonte.is_active = is_active
    db.commit()
    db.refresh(fonte)
    return fonte


# =============================================================================
# SNAPSHOTS (DocumentSnapshot)
# =============================================================================

def get_latest_snapshot(db: Session, source_id: int) -> Optional[DocumentSnapshot]:
    """
    Retorna o snapshot mais recente de uma fonte.

    É a função central do mecanismo de detecção de mudança:
    o pipeline compara o hash deste snapshot com o hash do scrape atual.
    Se forem iguais, a documentação não mudou — nada a fazer.

    Retorna None se a fonte nunca foi capturada (primeira execução).
    """
    return (
        db.query(DocumentSnapshot)
        .filter(DocumentSnapshot.source_id == source_id)
        .order_by(DocumentSnapshot.scraped_at.desc())
        .first()
    )


def save_snapshot(
    db: Session,
    source_id: int,
    content_hash: str,
    content_text: str,
) -> DocumentSnapshot:
    """
    Salva uma nova versão capturada de uma documentação.

    Chamada pelo pipeline APENAS quando o hash mudou em relação
    ao último snapshot — nunca salva duplicatas.

    Returns:
        O objeto DocumentSnapshot criado e persistido.
    """
    snapshot = DocumentSnapshot(
        source_id=source_id,
        content_hash=content_hash,
        content_text=content_text,
        scraped_at=datetime.now(timezone.utc),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


# =============================================================================
# ALERTAS (ChangeAlert)
# =============================================================================

def save_alert(
    db: Session,
    source_id: int,
    snapshot_id: int,
    has_relevant_changes: bool,
    is_breaking_change: bool,
    severity: str,
    summary_ptbr: str,
    affected_endpoints: List[str],
    recommended_action: str,
) -> ChangeAlert:
    """
    Salva o resultado da análise do Agente de IA como um alerta.

    Os parâmetros espelham diretamente os campos do schema APIDocAnalysis
    (core/agent.py). A lista de endpoints é serializada como string CSV
    para compatibilidade com SQLite.

    Returns:
        O objeto ChangeAlert criado e persistido.
    """
    # Converte lista de endpoints para string CSV
    # Ex: ["POST /orders", "GET /items"] → "POST /orders, GET /items"
    endpoints_str = ", ".join(affected_endpoints) if affected_endpoints else ""

    alerta = ChangeAlert(
        source_id=source_id,
        snapshot_id=snapshot_id,
        has_relevant_changes=has_relevant_changes,
        is_breaking_change=is_breaking_change,
        severity=severity,
        summary_ptbr=summary_ptbr,
        affected_endpoints=endpoints_str,
        recommended_action=recommended_action,
        notified_by_email=False,
    )
    db.add(alerta)
    db.commit()
    db.refresh(alerta)
    return alerta


def get_alerts(
    db: Session,
    source_id: Optional[int] = None,
    only_relevant: bool = False,
    only_unnotified: bool = False,
    limit: int = 50,
) -> List[ChangeAlert]:
    """
    Lista alertas com filtros opcionais.

    Args:
        source_id: Se informado, filtra por fonte específica
        only_relevant: Se True, retorna apenas alertas com mudança relevante
        only_unnotified: Se True, retorna apenas alertas não notificados por e-mail
        limit: Máximo de resultados (padrão: 50)

    Returns:
        Lista de ChangeAlert ordenada do mais recente para o mais antigo.
    """
    query = db.query(ChangeAlert)

    if source_id is not None:
        query = query.filter(ChangeAlert.source_id == source_id)
    if only_relevant:
        query = query.filter(ChangeAlert.has_relevant_changes == True)
    if only_unnotified:
        query = query.filter(ChangeAlert.notified_by_email == False)

    return query.order_by(ChangeAlert.created_at.desc()).limit(limit).all()


def mark_alert_as_notified(db: Session, alert_id: int) -> Optional[ChangeAlert]:
    """
    Marca um alerta como notificado por e-mail.

    Chamada pelo email_sender.py após confirmação de envio bem-sucedido.
    Garante que o mesmo alerta não seja enviado duas vezes.
    """
    alerta = db.query(ChangeAlert).filter(ChangeAlert.id == alert_id).first()
    if not alerta:
        return None
    alerta.notified_by_email = True
    db.commit()
    db.refresh(alerta)
    return alerta
