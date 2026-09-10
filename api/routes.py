"""
api/routes.py
=============
Rotas da API (FastAPI) para comunicação com o frontend (Streamlit).

POR QUE EXISTE:
    O Streamlit e o Scheduler são processos/lógicas distintas.
    A API centraliza o acesso ao banco de dados e permite que:
    - O Streamlit cadastre novas fontes sem mexer direto no banco.
    - O Streamlit exiba os alertas de forma segura.
    - O usuário consiga disparar uma verificação manual (Forçar Sincronização).
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, HttpUrl

from database.database import get_db
from database import repository as repo
from pipeline.workflow import check_source

router = APIRouter(prefix="/api", tags=["API Principal"])

# =============================================================================
# SCHEMAS DE ENTRADA/SAÍDA (PYDANTIC)
# =============================================================================

class SourceCreate(BaseModel):
    name: str
    url: HttpUrl
    check_interval_minutes: int = 1440

class SourceResponse(BaseModel):
    id: int
    name: str
    url: str
    is_active: bool
    check_interval_minutes: int

class AlertResponse(BaseModel):
    id: int
    source_id: int
    severity: str
    is_breaking_change: bool
    summary_ptbr: str
    affected_endpoints: str | None
    recommended_action: str
    notified_by_email: bool
    created_at: str

# =============================================================================
# ROTAS: FONTES (SOURCES)
# =============================================================================

@router.get("/sources", response_model=List[SourceResponse])
def listar_fontes(db: Session = Depends(get_db)):
    """Retorna todas as fontes cadastradas (ativas e inativas)."""
    fontes = db.query(repo.MonitoredSource).all()
    # Pydantic mapeia os objetos SQLAlchemy automaticamente
    return [{"id": f.id, "name": f.name, "url": f.url, 
             "is_active": f.is_active, "check_interval_minutes": f.check_interval_minutes} 
            for f in fontes]


@router.post("/sources", response_model=SourceResponse)
def cadastrar_fonte(fonte: SourceCreate, db: Session = Depends(get_db)):
    """Cadastra uma nova URL para monitoramento."""
    try:
        nova = repo.create_source(
            db, 
            name=fonte.name, 
            url=str(fonte.url), 
            check_interval_minutes=fonte.check_interval_minutes
        )
        return {"id": nova.id, "name": nova.name, "url": nova.url, 
                "is_active": nova.is_active, "check_interval_minutes": nova.check_interval_minutes}
    except ValueError as e:
        # Pega o erro de "URL já cadastrada" lançado pelo repository
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/sources/{source_id}/status", response_model=SourceResponse)
def alterar_status_fonte(source_id: int, is_active: bool, db: Session = Depends(get_db)):
    """Ativa ou desativa o monitoramento de uma fonte."""
    fonte = repo.update_source_status(db, source_id, is_active)
    if not fonte:
        raise HTTPException(status_code=404, detail="Fonte não encontrada")
    return {"id": fonte.id, "name": fonte.name, "url": fonte.url, 
            "is_active": fonte.is_active, "check_interval_minutes": fonte.check_interval_minutes}


# =============================================================================
# ROTAS: ALERTAS E EXECUÇÃO
# =============================================================================

@router.get("/alerts", response_model=List[AlertResponse])
def listar_alertas(
    only_relevant: bool = False, 
    limit: int = 50, 
    db: Session = Depends(get_db)
):
    """Lista os alertas mais recentes."""
    alertas = repo.get_alerts(db, only_relevant=only_relevant, limit=limit)
    return [{
        "id": a.id,
        "source_id": a.source_id,
        "severity": a.severity,
        "is_breaking_change": a.is_breaking_change,
        "summary_ptbr": a.summary_ptbr,
        "affected_endpoints": a.affected_endpoints,
        "recommended_action": a.recommended_action,
        "notified_by_email": a.notified_by_email,
        "created_at": a.created_at.isoformat()
    } for a in alertas]


@router.post("/check-now/{source_id}")
def forcar_verificacao(source_id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Força a verificação imediata de uma URL específica (Trigger Manual).
    Como o scraping e a IA demoram (5-20 segundos), rodamos em BackgroundTask
    para a API responder rápido à interface.
    """
    fonte = repo.get_source_by_id(db, source_id)
    if not fonte:
        raise HTTPException(status_code=404, detail="Fonte não encontrada")
    
    # Adiciona a tarefa em background para o FastAPI cuidar
    # OBS: idealmente criaríamos uma nova sessão no background, mas como
    # a check_source roda na mesma thread do background_tasks, passamos o db.
    # Porém, a forma mais correta no FastAPI é não passar o 'db' do Depends 
    # para a thread de fundo, e sim abrir um novo.
    
    def background_job(sid: int):
        from database.database import SessionLocal
        with SessionLocal() as db_bg:
            f = repo.get_source_by_id(db_bg, sid)
            check_source(db_bg, f)
            # Enviar e-mails para os gerados
            alertas_pendentes = repo.get_alerts(db_bg, source_id=sid, only_relevant=True, only_unnotified=True)
            for alerta in alertas_pendentes:
                from notifications.email_sender import enviar_email_alerta
                if enviar_email_alerta(alerta, f):
                    repo.mark_alert_as_notified(db_bg, alerta.id)

    background_tasks.add_task(background_job, source_id)
    
    return {"message": f"Verificação iniciada em background para '{fonte.name}'"}
