"""
core/agent.py
=============
Define o Agente de IA (Agno + Google Gemini) e o schema de saída (Pydantic).

POR QUE EXISTE:
    Após detectar que o conteúdo mudou (via hash), precisamos saber SE
    a mudança é relevante para os desenvolvedores. Mudou o copyright?
    Ignoramos. Mudou um endpoint obrigatório? Alertamos.
    
    Essa inteligência vem do LLM (Gemini), mas com uma restrição crítica:
    a saída NUNCA é texto livre. É um objeto Python estruturado (Pydantic),
    garantindo que o sistema sempre receba dados no formato esperado.

CONCEITOS IMPORTANTES:
    - Pydantic: Biblioteca de validação de dados. Define "contratos" de dados.
      Se a IA tentar retornar algo fora do schema, Pydantic rejeita.
    - Agno Agent: Wrapper que gerencia a comunicação com o LLM, injeta
      as instruções (system prompt) e força o formato de saída.
    - response_model: O parâmetro que diz ao Agno "quero a resposta NESSE formato".
"""

import os
from typing import List, Literal

from agno.agent import Agent
from agno.models.google import Gemini
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Carrega as variáveis do arquivo .env para o ambiente Python
# Sem isso, os.getenv("GOOGLE_API_KEY") retornaria None
load_dotenv()


# =============================================================================
# SCHEMA DE SAÍDA (CONTRATO DE DADOS)
# Isso é o "formulário" que o Agente DEVE preencher.
# A IA não pode inventar campos ou formatos — o Pydantic garante isso.
# =============================================================================

class APIDocAnalysis(BaseModel):
    """
    Resultado estruturado da análise de uma mudança em documentação técnica.
    
    Cada campo tem um `Field` com `description` — essa descrição é enviada
    junto para o LLM como instrução sobre o que colocar em cada campo.
    """

    has_relevant_changes: bool = Field(
        description=(
            "True APENAS se houver alterações técnicas reais que impactam "
            "integrações: novos campos obrigatórios, endpoints depreciados, "
            "mudanças de autenticação, rate limits ou status codes alterados. "
            "False para mudanças cosméticas (CSS, copyright, links, menus)."
        )
    )

    is_breaking_change: bool = Field(
        description=(
            "True se a mudança QUEBRA código legado existente e exige "
            "refatoração obrigatória. False se é aditiva (novo campo opcional, "
            "novo endpoint sem remover o antigo)."
        )
    )

    severity: Literal["BAIXA", "MEDIA", "ALTA", "CRITICA"] = Field(
        description=(
            "Nível de urgência: "
            "BAIXA = documentação melhorada, sem impacto em código; "
            "MEDIA = novo campo opcional, boa prática atualizar; "
            "ALTA = novo campo obrigatório, prazo definido para migração; "
            "CRITICA = endpoint removido/alterado, sistema PODE QUEBRAR AGORA."
        )
    )

    summary_ptbr: str = Field(
        description=(
            "Resumo claro e direto em português brasileiro sobre O QUE mudou. "
            "Máximo 3 frases. Sem jargão desnecessário. "
            "Ex: 'O endpoint POST /orders agora exige o campo tax_id obrigatório.'"
        )
    )

    affected_endpoints_or_modules: List[str] = Field(
        default_factory=list,
        description=(
            "Lista dos endpoints, webhooks ou módulos impactados. "
            "Ex: ['POST /orders', 'GET /shipments/{id}', 'Auth Header']. "
            "Lista vazia se não houver mudança técnica relevante."
        )
    )

    recommended_action: str = Field(
        description=(
            "Instrução prática e específica para o desenvolvedor. "
            "Ex: 'Atualizar o payload no módulo integrations/mercadolivre/orders.py "
            "adicionando o campo tax_id obrigatório antes de 15/09.' "
            "Se não há ação necessária, escreva: 'Nenhuma ação necessária.'"
        )
    )


# =============================================================================
# CONFIGURAÇÃO DO AGENTE AGNO
# =============================================================================

def criar_agente() -> Agent:
    """
    Cria e retorna o Agente de auditoria configurado com Gemini.
    
    NOTA: Criamos via função (não como variável global) para que o .env
    já esteja carregado antes de instanciar o modelo Gemini.
    """
    modelo = Gemini(
        # id: qual versão do Gemini usar (configurável pelo .env)
        id=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
    )

    agente = Agent(
        model=modelo,
        
        # description: quem é o agente (vai para o system prompt)
        description=(
            "Você é um auditor sênior especializado em APIs de e-commerce e marketplaces. "
            "Sua única função é analisar diffs de documentação técnica e classificar "
            "o impacto para times de desenvolvimento de software."
        ),
        
        # instructions: regras de comportamento (também vão para o system prompt)
        instructions=[
            "Analise APENAS diferenças técnicas entre a versão anterior e a nova.",
            "IGNORE completamente: mudanças de copyright, datas, links de rodapé, "
            "CSS, banners, imagens, textos institucionais e ordem de menus.",
            "FOQUE em: novos campos (obrigatórios ou opcionais), endpoints "
            "adicionados ou removidos, mudanças em headers HTTP, autenticação, "
            "rate limits, formatos de data/hora e status codes.",
            "Se a mudança for apenas cosmética, defina has_relevant_changes=False "
            "e severity=BAIXA.",
            "Responda SEMPRE em português brasileiro.",
            "Seja objetivo e direto. Evite linguagem vaga como 'pode ser necessário'.",
        ],
        
        # response_model: FORÇA a saída a seguir o schema APIDocAnalysis
        # O Agno instrui o LLM a retornar JSON compatível e valida com Pydantic
        response_model=APIDocAnalysis,
        
        # markdown=False: não queremos formatação markdown na resposta,
        # pois estamos esperando JSON estruturado
        markdown=False,
    )

    return agente


# =============================================================================
# FUNÇÃO PRINCIPAL DE ANÁLISE
# =============================================================================

def analisar_mudanca(
    url: str,
    conteudo_anterior: str,
    conteudo_atual: str,
) -> APIDocAnalysis | None:
    """
    Envia o diff de documentação para o Agente e retorna a análise estruturada.

    Args:
        url: URL da documentação (para contexto do agente)
        conteudo_anterior: Texto Markdown do último snapshot salvo
        conteudo_atual: Texto Markdown extraído agora

    Returns:
        Objeto APIDocAnalysis com a análise completa, ou None em caso de erro.
    """
    agente = criar_agente()

    # Limitamos o tamanho do conteúdo para não explodir o contexto do LLM
    # e controlar custos. 4000 caracteres ≈ ~1000 tokens por versão
    MAX_CHARS = 4000

    # O prompt é o "pedido" que enviamos para o agente
    # Incluímos a URL para o agente ter contexto sobre qual sistema está analisando
    prompt = f"""
Analise as mudanças na documentação técnica abaixo e preencha o formulário de análise.

**URL Monitorada:** {url}

---
**VERSÃO ANTERIOR (último snapshot salvo):**
{conteudo_anterior[:MAX_CHARS]}

---
**NOVA VERSÃO (capturada agora):**
{conteudo_atual[:MAX_CHARS]}
---

Com base nas diferenças entre as duas versões, preencha todos os campos do formulário.
"""

    try:
        print(f"  → Enviando diff para análise do Gemini...")
        resposta = agente.run(prompt)
        
        # resposta.content contém o objeto Pydantic validado (APIDocAnalysis)
        return resposta.content

    except Exception as e:
        print(f"  → ERRO na análise do agente: {e}")
        return None
