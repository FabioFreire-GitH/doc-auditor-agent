"""
database/database.py
====================
Configura a conexão com o banco de dados SQLite via SQLAlchemy.

POR QUE EXISTE:
    Qualquer módulo que precise ler ou escrever no banco (repository.py,
    workflow.py, api/routes.py) importa daqui a `SessionLocal` e a `Base`.
    Centralizar aqui evita duplicação e garante que todos usam a mesma engine.

CONCEITOS:
    - Engine: a "conexão raiz" com o arquivo .db. Criada uma vez, reutilizada.
    - Session: o "canal" por onde executamos queries. Cada operação abre e
      fecha uma sessão (contexto isolado, com rollback automático em erros).
    - Base: classe pai de todos os Models (tabelas). O SQLAlchemy usa ela para
      saber quais tabelas criar quando chamamos Base.metadata.create_all().
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CONFIGURAÇÃO DA ENGINE
# =============================================================================

# Lê a URL do banco do .env. Padrão: SQLite local no arquivo sentinel.db
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sentinel.db")

# check_same_thread=False: necessário para SQLite quando múltiplas threads
# (ex: scheduler + FastAPI) acessam o banco simultaneamente.
# Não tem efeito em outros bancos (PostgreSQL, MySQL).
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

# =============================================================================
# FÁBRICA DE SESSÕES
# =============================================================================

# autocommit=False: mudanças só são salvas quando chamamos session.commit()
# autoflush=False:  evita writes automáticos inesperados antes do commit
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# =============================================================================
# BASE DECLARATIVA
# =============================================================================

class Base(DeclarativeBase):
    """
    Classe base para todos os modelos do projeto.
    Todos os arquivos de models.py herdam desta classe.
    """
    pass


# =============================================================================
# UTILITÁRIO: GERADOR DE SESSÃO
# =============================================================================

def get_db():
    """
    Gerador de sessão para uso com FastAPI (injeção de dependência).

    Uso típico em uma rota FastAPI:
        def minha_rota(db: Session = Depends(get_db)):
            ...

    Garante que a sessão é sempre fechada, mesmo em caso de erro.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
