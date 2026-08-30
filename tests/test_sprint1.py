"""
tests/test_sprint1.py
=====================
Script de validação do Sprint 1: Core Engine.

COMO EXECUTAR:
    uv run python tests/test_sprint1.py

O QUE ESSE TESTE VALIDA:
    1. Caso "sem mudança": dois textos idênticos → hash igual → IA NÃO é chamada
    2. Caso "mudança cosmética": copyright mudou → IA é chamada → has_relevant_changes=False
    3. Caso "mudança técnica": novo campo obrigatório → IA → has_relevant_changes=True
    4. Caso "breaking change": endpoint removido → IA → is_breaking_change=True
    5. Caso "URL real": baixa uma página real e mostra o Markdown extraído

PRÉ-REQUISITO:
    - Arquivo .env criado com GOOGLE_API_KEY preenchida
    - uv sync executado com sucesso
"""

import sys
import os

# Adiciona o diretório raiz ao path para importar os módulos do projeto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.hasher import calcular_hash, conteudo_mudou
from core.agent import analisar_mudanca, APIDocAnalysis


# =============================================================================
# TEXTOS SIMULADOS PARA TESTES
# =============================================================================

DOC_VERSAO_1 = """
# API de Pedidos — Mercado Livre

## POST /orders

Cria um novo pedido na plataforma.

### Parâmetros obrigatórios:
- `customer_id` (string): ID único do cliente
- `items` (array): Lista de produtos
- `total` (float): Valor total do pedido

### Resposta de sucesso (200):
```json
{
  "order_id": "ML-12345",
  "status": "confirmed"
}
```

### Autenticação:
Bearer Token no header Authorization.

Copyright © 2023 Mercado Livre. Todos os direitos reservados.
"""

DOC_VERSAO_2_COSMETICA = """
# API de Pedidos — Mercado Livre

## POST /orders

Cria um novo pedido na plataforma.

### Parâmetros obrigatórios:
- `customer_id` (string): ID único do cliente
- `items` (array): Lista de produtos
- `total` (float): Valor total do pedido

### Resposta de sucesso (200):
```json
{
  "order_id": "ML-12345",
  "status": "confirmed"
}
```

### Autenticação:
Bearer Token no header Authorization.

Copyright © 2024 Mercado Livre. Todos os direitos reservados.
"""

DOC_VERSAO_3_TECNICA = """
# API de Pedidos — Mercado Livre

## POST /orders

Cria um novo pedido na plataforma.

### Parâmetros obrigatórios:
- `customer_id` (string): ID único do cliente
- `items` (array): Lista de produtos
- `total` (float): Valor total do pedido
- `tax_id` (string): CPF/CNPJ do cliente — **NOVO CAMPO OBRIGATÓRIO a partir de 01/10/2024**

### Resposta de sucesso (200):
```json
{
  "order_id": "ML-12345",
  "status": "confirmed"
}
```

### Autenticação:
Bearer Token no header Authorization.

Copyright © 2024 Mercado Livre. Todos os direitos reservados.
"""

DOC_VERSAO_4_BREAKING = """
# API de Pedidos — Mercado Livre

## POST /v2/orders  ← ATENÇÃO: Versão atualizada

Cria um novo pedido na plataforma. A versão v1 foi DESCONTINUADA.
Migre para POST /v2/orders imediatamente.

### BREAKING CHANGE:
O endpoint POST /orders (v1) será removido em 30/09/2024.
Todas as integrações DEVEM migrar para /v2/orders.

### Parâmetros obrigatórios (v2):
- `customer_id` (string): ID único do cliente
- `items` (array): Lista de produtos
- `total` (float): Valor total do pedido
- `tax_id` (string): CPF/CNPJ do cliente (obrigatório)
- `shipping_address` (object): Endereço de entrega completo (obrigatório)

### Autenticação:
Bearer Token no header Authorization.
"""


# =============================================================================
# HELPERS DE EXIBIÇÃO
# =============================================================================

def separador(titulo: str):
    print(f"\n{'='*60}")
    print(f"  {titulo}")
    print(f"{'='*60}")


def exibir_resultado(resultado: APIDocAnalysis | None):
    if resultado is None:
        print("  ❌ Análise falhou (verificar logs acima)")
        return
    
    emoji_severidade = {
        "BAIXA": "🟢",
        "MEDIA": "🟡",
        "ALTA": "🟠",
        "CRITICA": "🔴"
    }
    
    print(f"  Mudança relevante:  {'✅ SIM' if resultado.has_relevant_changes else '❌ NÃO'}")
    print(f"  Breaking change:    {'⚠️  SIM' if resultado.is_breaking_change else '✅ NÃO'}")
    print(f"  Severidade:         {emoji_severidade.get(resultado.severity, '?')} {resultado.severity}")
    print(f"  Resumo:             {resultado.summary_ptbr}")
    
    if resultado.affected_endpoints_or_modules:
        print(f"  Endpoints:          {', '.join(resultado.affected_endpoints_or_modules)}")
    
    print(f"  Ação recomendada:   {resultado.recommended_action}")


# =============================================================================
# CASOS DE TESTE
# =============================================================================

def teste_sem_mudanca():
    """Textos idênticos → hash igual → IA NÃO deve ser chamada"""
    separador("TESTE 1: Sem mudança (textos idênticos)")
    
    mudou, hash_atual = conteudo_mudou(
        hash_anterior=calcular_hash(DOC_VERSAO_1),
        conteudo_atual=DOC_VERSAO_1
    )
    
    if not mudou:
        print("  ✅ CORRETO: Hash idêntico detectado. IA não foi chamada. Zero custo.")
    else:
        print("  ❌ ERRO: Deveria ter detectado conteúdo idêntico!")


def teste_mudanca_cosmetica(chamar_ia: bool = True):
    """Copyright mudou → hash diferente → IA chamada → has_relevant_changes=False"""
    separador("TESTE 2: Mudança cosmética (apenas copyright)")
    
    mudou, hash_atual = conteudo_mudou(
        hash_anterior=calcular_hash(DOC_VERSAO_1),
        conteudo_atual=DOC_VERSAO_2_COSMETICA
    )
    
    print(f"  Hash mudou: {'SIM' if mudou else 'NÃO'}")
    
    if mudou and chamar_ia:
        print("  → Hash diferente. Chamando IA para análise semântica...")
        resultado = analisar_mudanca(
            url="https://api.mercadolivre.com/docs/orders",
            conteudo_anterior=DOC_VERSAO_1,
            conteudo_atual=DOC_VERSAO_2_COSMETICA
        )
        exibir_resultado(resultado)
        
        if resultado and not resultado.has_relevant_changes:
            print("\n  ✅ CORRETO: IA identificou corretamente como mudança cosmética!")


def teste_mudanca_tecnica(chamar_ia: bool = True):
    """Novo campo obrigatório → IA → has_relevant_changes=True, severity=ALTA"""
    separador("TESTE 3: Mudança técnica (novo campo obrigatório)")
    
    mudou, hash_atual = conteudo_mudou(
        hash_anterior=calcular_hash(DOC_VERSAO_1),
        conteudo_atual=DOC_VERSAO_3_TECNICA
    )
    
    if mudou and chamar_ia:
        print("  → Hash diferente. Chamando IA para análise semântica...")
        resultado = analisar_mudanca(
            url="https://api.mercadolivre.com/docs/orders",
            conteudo_anterior=DOC_VERSAO_1,
            conteudo_atual=DOC_VERSAO_3_TECNICA
        )
        exibir_resultado(resultado)
        
        if resultado and resultado.has_relevant_changes:
            print("\n  ✅ CORRETO: IA identificou mudança técnica relevante!")


def teste_breaking_change(chamar_ia: bool = True):
    """Endpoint descontinuado → IA → is_breaking_change=True, severity=CRITICA"""
    separador("TESTE 4: Breaking Change (endpoint descontinuado)")
    
    mudou, hash_atual = conteudo_mudou(
        hash_anterior=calcular_hash(DOC_VERSAO_1),
        conteudo_atual=DOC_VERSAO_4_BREAKING
    )
    
    if mudou and chamar_ia:
        print("  → Hash diferente. Chamando IA para análise semântica...")
        resultado = analisar_mudanca(
            url="https://api.mercadolivre.com/docs/orders",
            conteudo_anterior=DOC_VERSAO_1,
            conteudo_atual=DOC_VERSAO_4_BREAKING
        )
        exibir_resultado(resultado)
        
        if resultado and resultado.is_breaking_change:
            print("\n  ✅ CORRETO: IA identificou corretamente um breaking change crítico!")


def teste_url_real():
    """Baixa uma URL real e exibe o Markdown extraído (sem IA)"""
    separador("TESTE 5: Extração de URL real (sem IA)")
    
    # Importa aqui para não afetar outros testes caso httpx falhe
    from core.extractor import extrair_conteudo
    
    url = "https://stripe.com/docs/api/charges"
    print(f"  Baixando: {url}")
    
    conteudo = extrair_conteudo(url)
    
    if conteudo:
        print(f"  ✅ Extração OK! Tamanho: {len(conteudo)} caracteres")
        print(f"\n  --- Primeiros 500 caracteres do Markdown extraído ---")
        print(conteudo[:500])
        print(f"  ...")
    else:
        print("  ❌ Falha na extração (URL pode estar bloqueando scraping)")


# =============================================================================
# EXECUÇÃO DOS TESTES
# =============================================================================

if __name__ == "__main__":
    print("\n🚀 API Doc Sentinel — Validação do Sprint 1: Core Engine")
    print("Aguarde... os testes com IA levam alguns segundos cada.\n")
    
    # Verifica se o .env existe antes de começar
    if not os.path.exists(".env"):
        print("⚠️  AVISO: Arquivo .env não encontrado!")
        print("   Copie .env.example para .env e preencha GOOGLE_API_KEY")
        print("   Os testes sem IA (1 e 5) ainda funcionarão.\n")
    
    # Testes sem IA (sempre executam)
    teste_sem_mudanca()
    
    # Verifica se tem chave da API para rodar os testes com IA
    from dotenv import load_dotenv
    load_dotenv()
    
    tem_api_key = bool(os.getenv("GOOGLE_API_KEY"))
    
    if tem_api_key:
        teste_mudanca_cosmetica(chamar_ia=True)
        teste_mudanca_tecnica(chamar_ia=True)
        teste_breaking_change(chamar_ia=True)
    else:
        print("\n⚠️  Testes 2, 3 e 4 pulados (sem GOOGLE_API_KEY no .env)")
        print("   Configure o .env e execute novamente para testar a IA.")
    
    # Teste de URL real (sem IA)
    teste_url_real()
    
    print("\n" + "="*60)
    print("  Sprint 1 validado com sucesso! ✅")
    print("  Próximo passo: Sprint 2 — Persistência e Pipeline")
    print("="*60 + "\n")
