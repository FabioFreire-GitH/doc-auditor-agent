"""
scheduler/scheduler.py
======================
Gerenciador de tarefas em segundo plano (Background Tasks).

POR QUE EXISTE:
    Um auditor de documentação não pode depender de cliques manuais.
    Ele precisa acordar sozinho, checar todas as URLs, salvar o que mudou,
    mandar e-mail se necessário, e voltar a dormir.
    O APScheduler faz isso rodando na mesma thread da aplicação (sem Redis).
"""

import atexit
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from database.database import SessionLocal
from database import repository as repo
from pipeline.workflow import run_pipeline
from notifications.email_sender import enviar_email_alerta

# Objeto global do scheduler
scheduler = BackgroundScheduler()

def job_auditoria():
    """
    Job principal que será executado periodicamente.
    1. Roda o pipeline (baixa, calcula hash, chama IA, salva no banco)
    2. Busca os alertas relevantes gerados que ainda não foram notificados
    3. Tenta enviar e-mail. Se sucesso, marca como notificado.
    """
    print("\n[Scheduler] Iniciando job_auditoria() automatico...")
    
    with SessionLocal() as db:
        # 1. Roda a verificação de todas as URLs ativas
        run_pipeline(db)
        
        # 2. Busca alertas relevantes que precisam de e-mail
        alertas_pendentes = repo.get_alerts(db, only_relevant=True, only_unnotified=True)
        
        if not alertas_pendentes:
            print("[Scheduler] Nenhum e-mail novo para enviar.")
            return
            
        print(f"[Scheduler] {len(alertas_pendentes)} alerta(s) pendente(s) de envio.")
        
        # 3. Envia os e-mails
        for alerta in alertas_pendentes:
            fonte = repo.get_source_by_id(db, alerta.source_id)
            if not fonte:
                continue
                
            sucesso = enviar_email_alerta(alerta, fonte)
            
            # 4. Só marca como notificado se o envio do e-mail não deu erro
            if sucesso:
                repo.mark_alert_as_notified(db, alerta.id)
                print(f"[Scheduler] Alerta {alerta.id} marcado como notificado.")
            else:
                print(f"[Scheduler] Alerta {alerta.id} continua pendente para tentar na proxima.")


def start_scheduler(interval_minutes: int = 60):
    """
    Inicializa e liga o scheduler.
    Garante que o scheduler será desligado corretamente quando a aplicação morrer.
    """
    if scheduler.running:
        print("[Scheduler] Ja esta rodando.")
        return

    # Adiciona o job
    scheduler.add_job(
        func=job_auditoria,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="auditor_job",
        name="Auditoria de Documentacao",
        replace_existing=True
    )
    
    # Inicia o motor em background
    scheduler.start()
    print(f"[Scheduler] Iniciado. Rodando a cada {interval_minutes} minuto(s).")
    
    # Desliga limpo ao sair
    atexit.register(lambda: scheduler.shutdown(wait=False) if scheduler.running else None)

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        print("[Scheduler] Desligado.")
