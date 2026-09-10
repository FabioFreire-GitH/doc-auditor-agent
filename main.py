"""
main.py
=======
Ponto de entrada (Entry point) da aplicação Backend.

POR QUE EXISTE:
    Aqui é onde tudo se junta. Este arquivo:
    1. Garante que o banco de dados (sentinel.db) e as tabelas existam.
    2. Inicia a API (FastAPI) para o frontend (Streamlit) consumir.
    3. Liga o Agendador (APScheduler) no ciclo de vida (lifespan) da API,
       garantindo que ele rode em segundo plano e desligue corretamente.

COMO RODAR:
    uv run uvicorn main:app --reload
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Importa a infraestrutura do banco
from database.database import Base, engine

# Importa as rotas e o scheduler
from api.routes import router as api_router
from scheduler.scheduler import start_scheduler, stop_scheduler

# =============================================================================
# INICIALIZAÇÃO DO BANCO DE DADOS
# =============================================================================

# Garante que as tabelas existem antes de qualquer coisa subir
Base.metadata.create_all(bind=engine)


# =============================================================================
# LIFESPAN (CICLO DE VIDA DA APLICAÇÃO)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o que acontece quando a API liga e desliga.
    Substitui os antigos @app.on_event("startup") e ("shutdown").
    """
    print("\n🚀 Iniciando API Doc Sentinel Backend...")
    
    # LIGA (Startup)
    # Lê do .env o intervalo padrão, ou assume 1440 (1 dia)
    import os
    intervalo = int(os.getenv("DEFAULT_CHECK_INTERVAL_MINUTES", "1440"))
    start_scheduler(interval_minutes=intervalo)
    
    yield  # Aqui a API fica rodando e recebendo requisições...
    
    # DESLIGA (Shutdown)
    print("\n🛑 Desligando API Doc Sentinel...")
    stop_scheduler()


# =============================================================================
# APLICAÇÃO FASTAPI
# =============================================================================

app = FastAPI(
    title="API Doc Sentinel",
    description="Serviço autônomo de auditoria de documentação técnica.",
    version="1.0.0",
    lifespan=lifespan
)

# Adiciona CORS para permitir chamadas do Streamlit no futuro
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar a URL do frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registra as rotas criadas em api/routes.py
app.include_router(api_router)


@app.get("/", tags=["Health"])
def health_check():
    """Rota raiz para verificar se a API está no ar."""
    return {
        "status": "online",
        "service": "API Doc Sentinel",
        "docs": "http://127.0.0.1:8000/docs"
    }

if __name__ == "__main__":
    import uvicorn
    # Isso permite rodar `python main.py` diretamente para debug
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
