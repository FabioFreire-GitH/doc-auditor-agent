"""
pipeline/workflow.py
====================
Orquestrador central do sistema. Conecta todos os módulos em sequência.

POR QUE EXISTE:
    Sem este arquivo, cada módulo precisaria conhecer os outros:
    o extrator chamaria o hasher, que chamaria o agente, etc.
    O workflow inverte isso: ele é o único que conhece a sequência.
    Os outros módulos permanecem "burros" e focados na sua tarefa.

FLUXO DE check_source():
    1. Extrair o conteúdo atual da URL (extractor.py)
    2. Calcular o hash SHA-256 (hasher.py)
    3. Buscar o último snapshot salvo (repository.py)
    4. Comparar hashes:
       - Iguais → retorna PipelineResult sem chamar a IA (zero custo)
       - Diferentes → continua
    5. Salvar o novo snapshot no banco (repository.py)
    6. Chamar o Agente de IA para análise semântica (agent.py)
    7. Salvar o alerta no banco (repository.py)
    8. Retornar o resultado estruturado

RESULTADO:
    A função retorna um PipelineResult (dataclass simples) que o scheduler,
    a API e o Streamlit podem consumir sem conhecer detalhes internos.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from sqlalchemy.orm import Session

from core.extractor import extrair_conteudo
from core.hasher import conteudo_mudou
from core.agent import analisar_mudanca, APIDocAnalysis
from database.models import MonitoredSource
from database import repository as repo


# =============================================================================
# RESULTADO DO PIPELINE
# =============================================================================

@dataclass
class PipelineResult:
    """
    Resultado estruturado de uma execução do pipeline para uma fonte.

    Usando dataclass em vez de dict para ter type hints e acesso por atributo
    (result.changed em vez de result["changed"]).
    """
    source_id: int
    source_name: str
    url: str

    # --- Status da execução ---
    # True se o conteúdo mudou desde o último snapshot
    changed: bool = False

    # True se a IA identificou mudança técnica relevante
    # None se a IA não foi chamada (sem mudança de hash)
    relevant: Optional[bool] = None

    # O objeto completo retornado pela IA (None se não houve mudança ou erro)
    analysis: Optional[APIDocAnalysis] = None

    # ID do alerta salvo no banco (None se não houve mudança relevante)
    alert_id: Optional[int] = None

    # Mensagem de erro se algo falhou (None se tudo correu bem)
    error: Optional[str] = None

    def __str__(self) -> str:
        if self.error:
            return f"[ERRO] {self.source_name}: {self.error}"
        if not self.changed:
            return f"[SEM MUDANCA] {self.source_name}: hash identico, IA nao chamada"
        if not self.relevant:
            return f"[COSMETICO] {self.source_name}: mudanca detectada mas irrelevante"
        severity = self.analysis.severity if self.analysis else "?"
        return f"[ALERTA {severity}] {self.source_name}: mudanca tecnica relevante!"


# =============================================================================
# PIPELINE DE UMA FONTE
# =============================================================================

def check_source(db: Session, source: MonitoredSource) -> PipelineResult:
    """
    Executa o pipeline completo para uma única fonte monitorada.

    Args:
        db: Sessão do banco de dados (aberta por quem chama)
        source: Objeto MonitoredSource com a URL a verificar

    Returns:
        PipelineResult com o resultado detalhado da execução.
    """
    resultado = PipelineResult(
        source_id=source.id,
        source_name=source.name,
        url=source.url,
    )

    # ------------------------------------------------------------------
    # PASSO 1: Extrair o conteúdo atual da URL
    # ------------------------------------------------------------------
    print(f"\n[{source.name}] Extraindo conteudo de: {source.url}")
    conteudo_atual = extrair_conteudo(source.url)

    if not conteudo_atual:
        resultado.error = "Falha ao extrair conteudo da URL"
        print(f"[{source.name}] ERRO: {resultado.error}")
        return resultado

    # ------------------------------------------------------------------
    # PASSOS 2, 3 e 4: Calcular hash, buscar último e comparar
    # conteudo_mudou() faz tudo isso: calcula o hash do conteúdo atual
    # e compara com o hash anterior. Retorna (mudou: bool, hash_atual: str).
    # ------------------------------------------------------------------
    ultimo_snapshot = repo.get_latest_snapshot(db, source.id)
    hash_anterior = ultimo_snapshot.content_hash if ultimo_snapshot else None

    mudou, hash_atual = conteudo_mudou(hash_anterior, conteudo_atual)

    if not mudou:
        # Conteúdo idêntico (ou primeira execução sem baseline) — para aqui.
        print(f"[{source.name}] Hash identico. Sem mudancas. IA nao chamada.")
        resultado.changed = False

        # Primeira execução: salva o snapshot baseline mesmo sem chamar a IA.
        # Sem baseline, na próxima execução não teríamos "anterior" para comparar.
        if ultimo_snapshot is None:
            repo.save_snapshot(db, source_id=source.id, content_hash=hash_atual, content_text=conteudo_atual)
            print(f"[{source.name}] Baseline salvo (primeiro snapshot).")

        return resultado

    # Hash diferente — há mudança real!
    resultado.changed = True
    conteudo_anterior = ultimo_snapshot.content_text if ultimo_snapshot else ""
    print(f"[{source.name}] Hash diferente. Conteudo mudou. Chamando IA...")

    # ------------------------------------------------------------------
    # PASSO 5: Salvar o novo snapshot no banco
    # ------------------------------------------------------------------
    novo_snapshot = repo.save_snapshot(
        db,
        source_id=source.id,
        content_hash=hash_atual,
        content_text=conteudo_atual,
    )
    print(f"[{source.name}] Snapshot salvo (id={novo_snapshot.id})")

    # ------------------------------------------------------------------
    # PASSO 6: Chamar o Agente de IA para análise semântica
    # ------------------------------------------------------------------
    analysis = analisar_mudanca(
        url=source.url,
        conteudo_anterior=conteudo_anterior,
        conteudo_atual=conteudo_atual,
    )

    if not analysis:
        # A IA falhou (erro de API, timeout, etc.)
        # O snapshot já foi salvo — na próxima execução, o hash será igual
        # e a IA não será chamada novamente para este conteúdo.
        resultado.error = "Agente de IA retornou None (verificar logs acima)"
        print(f"[{source.name}] AVISO: {resultado.error}")
        return resultado

    resultado.analysis = analysis
    resultado.relevant = analysis.has_relevant_changes

    # ------------------------------------------------------------------
    # PASSO 7: Salvar o alerta no banco (independente de ser relevante)
    # Salvamos SEMPRE para manter histórico completo de análises.
    # ------------------------------------------------------------------
    alerta = repo.save_alert(
        db,
        source_id=source.id,
        snapshot_id=novo_snapshot.id,
        has_relevant_changes=analysis.has_relevant_changes,
        is_breaking_change=analysis.is_breaking_change,
        severity=analysis.severity,
        summary_ptbr=analysis.summary_ptbr,
        affected_endpoints=analysis.affected_endpoints_or_modules,
        recommended_action=analysis.recommended_action,
    )
    resultado.alert_id = alerta.id
    print(f"[{source.name}] Alerta salvo (id={alerta.id}, severity={alerta.severity})")

    return resultado


# =============================================================================
# PIPELINE COMPLETO (TODAS AS FONTES ATIVAS)
# =============================================================================

def run_pipeline(db: Session) -> List[PipelineResult]:
    """
    Executa o pipeline para todas as fontes ativas no banco.

    Chamada pelo scheduler a cada ciclo. Também pode ser chamada
    manualmente pela API (POST /api/check-all) ou pelo Streamlit.

    Returns:
        Lista de PipelineResult, um por fonte processada.
    """
    fontes = repo.get_active_sources(db)

    if not fontes:
        print("[Pipeline] Nenhuma fonte ativa cadastrada.")
        return []

    print(f"[Pipeline] Iniciando verificacao de {len(fontes)} fonte(s)...")
    resultados: List[PipelineResult] = []

    for fonte in fontes:
        try:
            resultado = check_source(db, fonte)
            resultados.append(resultado)
            print(f"[Pipeline] {resultado}")
        except Exception as e:
            # Erro inesperado — registramos e continuamos para a próxima fonte.
            # Uma fonte com problema não deve travar o pipeline das outras.
            erro = PipelineResult(
                source_id=fonte.id,
                source_name=fonte.name,
                url=fonte.url,
                error=f"Excecao nao tratada: {e}",
            )
            resultados.append(erro)
            print(f"[Pipeline] ERRO em '{fonte.name}': {e}")

    relevantes = sum(1 for r in resultados if r.relevant)
    print(f"\n[Pipeline] Concluido. {len(resultados)} fonte(s) verificada(s), {relevantes} alerta(s) relevante(s).")
    return resultados
