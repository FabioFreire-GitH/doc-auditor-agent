"""
core/hasher.py
==============
Calcula e compara hashes de conteúdo para detectar mudanças sem gastar tokens de IA.

POR QUE EXISTE:
    A IA (Gemini) custa dinheiro por token processado. Se mandarmos cada
    página para a IA toda vez que o scheduler rodar, o custo seria absurdo.
    
    A solução: calcular um "digital fingerprint" (SHA-256) do texto.
    Se o fingerprint mudou, o conteúdo mudou. Só aí chamamos a IA.
    
    Em 95%+ das execuções, a documentação NÃO mudou → zero custo de IA.

O QUE É SHA-256:
    SHA-256 é um algoritmo criptográfico que transforma qualquer texto
    em uma string de 64 caracteres hexadecimais. A propriedade fundamental:
    - Textos IGUAIS → hash SEMPRE igual
    - Textos DIFERENTES → hash SEMPRE diferente (praticamente impossível colisão)
    
    Exemplo:
    "POST /orders" → "a3f1c2d4e5..."
    "POST /orders (campo novo)" → "b9e2a1f3c4..." (completamente diferente!)
"""

import hashlib


def calcular_hash(conteudo: str) -> str:
    """
    Calcula o hash SHA-256 de um texto.

    Args:
        conteudo: O texto (Markdown da documentação) a ser "assinado".

    Returns:
        String hexadecimal de 64 caracteres representando o hash.
        
    Exemplo:
        >>> hash1 = calcular_hash("POST /orders - campos: id, total")
        >>> hash2 = calcular_hash("POST /orders - campos: id, total")
        >>> hash3 = calcular_hash("POST /orders - campos: id, total, tax_id (OBRIGATÓRIO)")
        >>> hash1 == hash2  # True: textos iguais, hash igual
        >>> hash1 == hash3  # False: texto diferente, hash diferente
    """
    # encode("utf-8"): converte texto Python (Unicode) para bytes
    # hashlib.sha256(...): cria o objeto de hash com os bytes
    # .hexdigest(): retorna o hash como string hexadecimal legível
    return hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


def conteudo_mudou(hash_anterior: str | None, conteudo_atual: str) -> tuple[bool, str]:
    """
    Compara o hash anterior com o conteúdo atual para decidir se houve mudança.

    Args:
        hash_anterior: Hash SHA-256 do último snapshot salvo no banco.
                       None se for a primeira vez que monitoramos essa URL.
        conteudo_atual: Texto Markdown extraído agora pela extractor.py

    Returns:
        Tupla com dois valores:
        - bool: True se o conteúdo mudou (ou é novo), False se igual
        - str: O hash do conteúdo atual (para salvar no banco)
        
    Exemplo de uso:
        mudou, novo_hash = conteudo_mudou(hash_salvo_no_banco, texto_novo)
        if mudou:
            # Chama a IA
        else:
            # Não faz nada, economiza tokens
    """
    hash_atual = calcular_hash(conteudo_atual)
    
    # Se não tem hash anterior, é o primeiro monitoramento dessa URL
    # Salvamos o snapshot mas não geramos alerta (não há "antes" para comparar)
    if hash_anterior is None:
        print("  → Primeiro snapshot desta URL. Salvando baseline sem análise.")
        return False, hash_atual
    
    # Comparação simples: strings iguais ou diferentes
    if hash_atual == hash_anterior:
        return False, hash_atual
    else:
        return True, hash_atual
