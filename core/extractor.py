"""
core/extractor.py
=================
Responsável por baixar o conteúdo de uma URL e limpá-lo para análise.

POR QUE EXISTE:
    Documentações de marketplaces são páginas HTML completas com menus,
    rodapés, banners e scripts. Se compararmos o HTML bruto, qualquer
    mudança de layout (ex: novo link no menu) geraria um alerta falso.
    Esse módulo isola APENAS o conteúdo técnico da página.

ESTRATÉGIA:
    1. Baixa o HTML com httpx (rápido, moderno, substituto do requests)
    2. Usa BeautifulSoup para navegar na árvore HTML
    3. Tenta encontrar as tags semânticas de conteúdo principal:
       <main>, <article>, <div role="main"> etc.
    4. Remove elementos que geram ruído: scripts, estilos, nav, footer
    5. Converte o HTML limpo para Markdown com html2text
       (Markdown é mais limpo para comparar e enviar para a IA)
"""

import httpx
import html2text
from bs4 import BeautifulSoup


# =============================================================================
# CONFIGURAÇÃO DO CONVERSOR HTML → MARKDOWN
# =============================================================================

def _criar_conversor_markdown() -> html2text.HTML2Text:
    """
    Cria e configura o conversor HTML para Markdown.
    
    As configurações evitam ruído desnecessário no texto final:
    - ignore_links=True: não inclui URLs dos links (ex: [texto](https://...))
    - ignore_images=True: não inclui descrições de imagens
    - body_width=0: não quebra linhas artificialmente (preserva o texto original)
    """
    conversor = html2text.HTML2Text()
    conversor.ignore_links = True
    conversor.ignore_images = True
    conversor.body_width = 0  # sem quebra de linha artificial
    return conversor


# =============================================================================
# FUNÇÃO PRINCIPAL DE EXTRAÇÃO
# =============================================================================

def extrair_conteudo(url: str, timeout: int = 30) -> str:
    """
    Baixa uma página web e retorna apenas o conteúdo técnico em Markdown.

    Args:
        url: A URL da página de documentação a ser monitorada.
        timeout: Tempo máximo de espera pela resposta em segundos.

    Returns:
        String com o conteúdo principal da página em formato Markdown.
        Retorna string vazia em caso de erro.

    Raises:
        Não levanta exceções — erros são logados e retornam string vazia
        para não interromper o pipeline de outras URLs.
    """
    try:
        # --- 1. Baixar o HTML da página ---
        # httpx.get faz uma requisição HTTP GET simples
        # follow_redirects=True: segue redirecionamentos (301, 302) automaticamente
        # headers: nos identificamos como um navegador para evitar bloqueios
        resposta = httpx.get(
            url,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
        )
        
        # Garante que a resposta foi bem-sucedida (HTTP 200)
        # Lança exceção se for 404, 500, etc.
        resposta.raise_for_status()
        
        html_bruto = resposta.text

    except httpx.TimeoutException:
        print(f"[EXTRATOR] Timeout ao acessar: {url}")
        return ""
    except httpx.HTTPStatusError as e:
        print(f"[EXTRATOR] Erro HTTP {e.response.status_code} em: {url}")
        return ""
    except Exception as e:
        print(f"[EXTRATOR] Erro inesperado em {url}: {e}")
        return ""

    # --- 2. Parsear o HTML com BeautifulSoup ---
    # "html.parser" é o parser nativo do Python, sem dependências extras
    soup = BeautifulSoup(html_bruto, "html.parser")

    # --- 3. Remover elementos que geram ruído ---
    # Esses elementos nunca contêm documentação técnica relevante
    TAGS_RUIDO = [
        "script",   # JavaScript
        "style",    # CSS inline
        "nav",      # Menus de navegação
        "header",   # Cabeçalho do site
        "footer",   # Rodapé (copyright, links institucionais)
        "aside",    # Barras laterais
        "noscript", # Conteúdo alternativo para JS desabilitado
    ]
    for tag in TAGS_RUIDO:
        for elemento in soup.find_all(tag):
            elemento.decompose()  # Remove o elemento da árvore HTML

    # --- 4. Tentar encontrar o conteúdo principal ---
    # Cada site organiza seu HTML diferente. Tentamos na ordem de prioridade:
    SELETORES_CONTEUDO = [
        soup.find("main"),                          # Tag semântica <main>
        soup.find("article"),                       # Tag semântica <article>
        soup.find(attrs={"role": "main"}),          # Atributo ARIA role="main"
        soup.find("div", {"class": "content"}),     # Classe genérica "content"
        soup.find("div", {"id": "content"}),        # ID genérico "content"
        soup.find("div", {"class": "docs-content"}),# Padrão de sites de docs
        soup.find("div", {"class": "markdown-body"}),# GitHub/GitBook
        soup.body,                                  # Fallback: body inteiro
    ]

    # Usa o primeiro seletor que encontrou algo
    conteudo_html = next(
        (elemento for elemento in SELETORES_CONTEUDO if elemento is not None),
        soup  # Último fallback: documento inteiro
    )

    # --- 5. Converter HTML limpo para Markdown ---
    conversor = _criar_conversor_markdown()
    markdown = conversor.handle(str(conteudo_html))

    # --- 6. Limpeza final do texto ---
    # Remove linhas vazias excessivas (mais de 2 seguidas)
    linhas = markdown.split("\n")
    linhas_limpas = []
    linhas_vazias_consecutivas = 0
    
    for linha in linhas:
        if linha.strip() == "":
            linhas_vazias_consecutivas += 1
            if linhas_vazias_consecutivas <= 2:
                linhas_limpas.append(linha)
        else:
            linhas_vazias_consecutivas = 0
            linhas_limpas.append(linha)

    return "\n".join(linhas_limpas).strip()
