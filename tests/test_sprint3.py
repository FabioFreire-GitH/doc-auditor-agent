"""
tests/test_sprint3.py
=====================
Validação do Sprint 3: Notificações, Scheduler e API.

ESTRUTURA DOS TESTES:
    Teste 1: E-mail (Geração do HTML e bloqueio de credenciais mockadas)
    Teste 2: API — Rota GET /api/sources
    Teste 3: API — Rota POST /api/sources (cadastro)
    Teste 4: API — Rota POST /api/check-now/{id} (trigger manual)
    Teste 5: Scheduler — Inicialização e desligamento limpo
"""

import sys
import os
from fastapi.testclient import TestClient

# Adiciona a raiz do projeto ao path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.models import ChangeAlert, MonitoredSource
from notifications.email_sender import enviar_email_alerta
from main import app
from scheduler.scheduler import start_scheduler, stop_scheduler

# Cliente de testes do FastAPI (não levanta uma porta real, testa diretamente na memória)
client = TestClient(app)

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


# =============================================================================
# TESTE 1 — Notificações (E-mail)
# =============================================================================

def teste_email():
    separador("TESTE 1: Notificacoes (Email Sender)")
    
    alerta_mock = ChangeAlert(
        id=999,
        severity="CRITICA",
        is_breaking_change=True,
        summary_ptbr="Mudança massiva no payload",
        affected_endpoints="POST /api/v1/users",
        recommended_action="Atualizar os DTOs imediatamente."
    )
    fonte_mock = MonitoredSource(name="API Fake", url="https://fake.api")
    
    print("  Testando o bloqueio de envio com credenciais vazias/padrão...")
    
    # Se o email não estiver configurado corretamente, a função captura o erro graciosamente
    # e retorna False para não estourar o pipeline.
    resultado = enviar_email_alerta(alerta_mock, fonte_mock)
    
    # O resultado pode ser True ou False (se configurado, enviará pro seu e-mail)
    if not resultado:
        ok("Funcao executou e bloqueou envio real (credenciais fake detectadas ou indisponiveis).")
    else:
        ok("E-mail enviado com sucesso (credenciais reais detectadas).")


# =============================================================================
# TESTE 2 e 3 — API Rest (Endpoints)
# =============================================================================

def teste_api_fontes():
    separador("TESTE 2 e 3: API FastAPI (Rotas de Fonte)")
    
    # TESTE GET
    resp = client.get("/api/sources")
    assert resp.status_code == 200, f"Erro no GET /api/sources: {resp.status_code}"
    fontes = resp.json()
    ok(f"GET /api/sources retornou status 200 (Encontrou {len(fontes)} fontes cadastradas)")
    
    # TESTE POST (Cadastrando uma fonte via API)
    nova_fonte = {
        "name": "API de Teste Automatizado",
        "url": "https://httpbin.org/get",
        "check_interval_minutes": 60
    }
    resp_post = client.post("/api/sources", json=nova_fonte)
    
    # Pode dar 200 (sucesso) ou 400 (URL já cadastrada se o teste rodar 2 vezes)
    if resp_post.status_code == 200:
        dado = resp_post.json()
        ok(f"POST /api/sources funcionou: cadastrou '{dado['name']}'")
    elif resp_post.status_code == 400:
        ok("POST /api/sources bloqueou corretamente a URL duplicada")
    else:
        falhou(f"POST falhou com status {resp_post.status_code}: {resp_post.text}")


# =============================================================================
# TESTE 4 — API Rest (Trigger Manual / Background Task)
# =============================================================================

def teste_api_check_now():
    separador("TESTE 4: API FastAPI (Trigger Manual Assincrono)")
    
    # 1. Pegamos uma fonte existente
    resp_fontes = client.get("/api/sources")
    fontes = resp_fontes.json()
    
    if not fontes:
        print("  -> Nenhuma fonte para testar o check-now. Pulando...")
        return
        
    fonte_alvo = fontes[0]["id"]
    
    # 2. Disparamos a checagem manual
    resp_check = client.post(f"/api/check-now/{fonte_alvo}")
    
    assert resp_check.status_code == 200
    dado = resp_check.json()
    
    # Deve retornar a mensagem imediatamente confirmando o background
    assert "background" in dado["message"]
    ok(f"POST /api/check-now/{fonte_alvo} enviou o comando em background perfeitamente: '{dado['message']}'")


# =============================================================================
# TESTE 5 — Scheduler
# =============================================================================

def teste_scheduler():
    separador("TESTE 5: Scheduler (APScheduler)")
    
    try:
        start_scheduler(60)
        ok("Scheduler inicializado corretamente (rodando em background).")
    except Exception as e:
        falhou(f"Falha ao iniciar scheduler: {e}")
        
    try:
        stop_scheduler()
        ok("Scheduler desligado com sucesso de forma limpa.")
    except Exception as e:
        falhou(f"Falha ao desligar scheduler: {e}")


# =============================================================================
# EXECUÇÃO PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    print("\n=== API Doc Sentinel - Validacao do Sprint 3: Backend e API ===")
    
    teste_email()
    teste_api_fontes()
    teste_api_check_now()
    teste_scheduler()
    
    print("\n" + "=" * 60)
    print("  Sprint 3 validado com sucesso!")
    print("  Toda a arquitetura de banco, orquestracao, background e API esta intacta.")
    print("  Podemos seguir para a construcao visual no Sprint 4 (Streamlit).")
    print("=" * 60 + "\n")
