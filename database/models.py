"""
database/models.py
==================
Define as tabelas do banco de dados como classes Python (ORM SQLAlchemy).

POR QUE EXISTE:
    Em vez de escrever SQL puro, usamos classes Python que o SQLAlchemy
    converte automaticamente em tabelas. Isso facilita:
    - Migrar de SQLite para PostgreSQL sem mudar nada aqui
    - Fazer queries com Python, sem strings SQL soltas
    - Ter type hints e autocompletar no IDE

CONCEITOS:
    - Mapped[tipo]: declara uma coluna com seu tipo Python (str, int, bool...)
    - mapped_column(): configurações da coluna (PK, FK, nullable, default...)
    - relationship(): define a ligação entre tabelas no nível Python.
      Ex: source.snapshots retorna todos os snapshots daquela fonte.
    - ForeignKey: garante integridade referencial (não existe snapshot
      sem uma fonte correspondente).
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.database import Base


# =============================================================================
# TABELA 1: MonitoredSources — URLs cadastradas para monitoramento
# =============================================================================

class MonitoredSource(Base):
    """
    Representa uma URL que o sistema deve monitorar periodicamente.

    Exemplo de registro:
        name: "Mercado Livre - Orders API"
        url:  "https://developers.mercadolivre.com.br/pt_br/gestao-de-pedidos"
        check_interval_minutes: 1440  # checar uma vez por dia
        is_active: True
    """
    __tablename__ = "monitored_sources"

    # Chave primária auto-incrementada
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Nome amigável para identificar a fonte (ex: "Stripe - Charges API")
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # URL completa da página de documentação a monitorar
    url: Mapped[str] = mapped_column(String(2048), unique=True, nullable=False)

    # Intervalo de checagem em minutos. Default: 1440 = uma vez por dia.
    # Cada fonte pode ter seu próprio intervalo (APIs críticas = mais frequente).
    check_interval_minutes: Mapped[int] = mapped_column(
        Integer, default=1440, nullable=False
    )

    # Flag para pausar o monitoramento sem deletar a fonte
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamp de cadastro (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # --- Relacionamentos ---
    # Uma fonte tem muitos snapshots (histórico de versões)
    snapshots: Mapped[List["DocumentSnapshot"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    # Uma fonte tem muitos alertas gerados pela IA
    alerts: Mapped[List["ChangeAlert"]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<MonitoredSource id={self.id} name='{self.name}'>"


# =============================================================================
# TABELA 2: DocumentSnapshots — Histórico de versões de cada fonte
# =============================================================================

class DocumentSnapshot(Base):
    """
    Armazena cada versão capturada de uma documentação.

    Cada vez que o extrator roda e detecta mudança de hash, um novo
    snapshot é salvo. Se o hash for igual ao anterior, nada é salvo —
    esse é o mecanismo de economia de tokens da IA.

    Exemplo de registro:
        source_id: 1
        content_hash: "a3f5c2..."   # SHA-256 do texto
        content_text: "# Orders API\n..."  # Texto em Markdown
        scraped_at: 2024-09-10T14:30:00Z
    """
    __tablename__ = "document_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # FK para MonitoredSource (a qual URL este snapshot pertence)
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("monitored_sources.id"), nullable=False, index=True
    )

    # SHA-256 do conteúdo Markdown limpo. Indexado para busca rápida.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Conteúdo completo em Markdown. Text = coluna sem limite de tamanho.
    content_text: Mapped[str] = mapped_column(Text, nullable=False)

    # Timestamp de quando o scraping foi feito (UTC)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # --- Relacionamentos ---
    source: Mapped["MonitoredSource"] = relationship(back_populates="snapshots")
    alerts: Mapped[List["ChangeAlert"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentSnapshot id={self.id} "
            f"source_id={self.source_id} "
            f"hash='{self.content_hash[:8]}...'>"
        )


# =============================================================================
# TABELA 3: ChangeAlerts — Alertas gerados pela IA
# =============================================================================

class ChangeAlert(Base):
    """
    Registra o resultado da análise do Agente de IA para uma mudança detectada.

    Campos espelham diretamente o schema Pydantic APIDocAnalysis do core/agent.py,
    garantindo que o que a IA retorna é exatamente o que o banco armazena.

    Exemplo de registro:
        has_relevant_changes: True
        is_breaking_change: True
        severity: "CRITICA"
        summary_ptbr: "O endpoint POST /orders agora exige tax_id obrigatório."
        affected_endpoints: "POST /orders"
        recommended_action: "Atualizar payload antes de 01/10/2024."
        notified_by_email: False  (ainda não enviamos o e-mail)
    """
    __tablename__ = "change_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # FK para a fonte monitorada
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("monitored_sources.id"), nullable=False, index=True
    )

    # FK para o snapshot que gerou este alerta (a versão NOVA que mudou)
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("document_snapshots.id"), nullable=False
    )

    # --- Campos do schema APIDocAnalysis ---
    has_relevant_changes: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_breaking_change: Mapped[bool] = mapped_column(Boolean, nullable=False)

    # BAIXA | MEDIA | ALTA | CRITICA
    severity: Mapped[str] = mapped_column(String(10), nullable=False)

    # Resumo em português gerado pela IA
    summary_ptbr: Mapped[str] = mapped_column(Text, nullable=False)

    # Endpoints afetados — lista serializada como string separada por vírgula.
    # Ex: "POST /orders, GET /shipments/{id}"
    # Simples e suficiente para SQLite. Em PostgreSQL usaríamos ARRAY.
    affected_endpoints: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Instrução de ação recomendada gerada pela IA
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)

    # Controle de notificação — False até o email_sender.py confirmar envio
    notified_by_email: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Timestamp de quando o alerta foi gerado (UTC)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # --- Relacionamentos ---
    source: Mapped["MonitoredSource"] = relationship(back_populates="alerts")
    snapshot: Mapped["DocumentSnapshot"] = relationship(back_populates="alerts")

    def __repr__(self) -> str:
        return (
            f"<ChangeAlert id={self.id} "
            f"severity='{self.severity}' "
            f"breaking={self.is_breaking_change}>"
        )
