"""
notifications/email_sender.py
=============================
Módulo responsável por enviar e-mails de alerta formatados em HTML.

POR QUE EXISTE:
    Quando a IA detecta uma mudança técnica na documentação, precisamos avisar
    os engenheiros de forma clara, rápida e acionável.
    O e-mail é formatado em HTML com cores indicando a severidade.

CONFIGURAÇÃO:
    Exige as seguintes variáveis no .env:
    - EMAIL_SENDER
    - EMAIL_PASSWORD (Senha de App do Google)
    - EMAIL_RECIPIENT
    - SMTP_HOST (padrão: smtp.gmail.com)
    - SMTP_PORT (padrão: 587)
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from dotenv import load_dotenv

from database.models import ChangeAlert, MonitoredSource

# Carrega variáveis do .env (se já não estiverem carregadas)
load_dotenv()

# =============================================================================
# CORES DE SEVERIDADE
# =============================================================================

SEVERITY_COLORS = {
    "CRITICA": "#dc3545",  # Vermelho
    "ALTA": "#fd7e14",     # Laranja Escuro
    "MEDIA": "#ffc107",    # Amarelo/Laranja
    "BAIXA": "#17a2b8",    # Azul Claro
}


# =============================================================================
# TEMPLATE HTML
# =============================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            background-color: #f4f7f6;
            margin: 0;
            padding: 20px;
            color: #333;
        }}
        .container {{
            max-width: 600px;
            background: #ffffff;
            margin: 0 auto;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header {{
            background-color: {color};
            color: #ffffff;
            padding: 20px;
            text-align: center;
        }}
        .content {{
            padding: 20px;
        }}
        .badge {{
            display: inline-block;
            background-color: {color};
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
            margin-bottom: 10px;
        }}
        .breaking-badge {{
            display: inline-block;
            background-color: #000000;
            color: white;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
            margin-bottom: 10px;
            margin-left: 5px;
        }}
        .section-title {{
            font-size: 14px;
            color: #666;
            text-transform: uppercase;
            margin-top: 20px;
            margin-bottom: 5px;
            border-bottom: 1px solid #eee;
            padding-bottom: 5px;
        }}
        .btn {{
            display: inline-block;
            background-color: #0056b3;
            color: #ffffff !important;
            text-decoration: none;
            padding: 10px 20px;
            border-radius: 5px;
            margin-top: 20px;
            font-weight: bold;
        }}
        .footer {{
            background-color: #f1f1f1;
            padding: 15px;
            text-align: center;
            font-size: 12px;
            color: #777;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h2 style="margin: 0;">Alerta de Mudança em API</h2>
        </div>
        <div class="content">
            <div style="margin-bottom: 15px;">
                <span class="badge">{severity}</span>
                {breaking_html}
            </div>
            
            <h3 style="margin-top: 0; color: #2c3e50;">{source_name}</h3>
            
            <div class="section-title">Resumo da Mudança</div>
            <p style="font-size: 16px; line-height: 1.5;">{summary}</p>
            
            <div class="section-title">Endpoints ou Módulos Afetados</div>
            <p style="font-family: monospace; background: #f8f9fa; padding: 10px; border-radius: 4px; border: 1px solid #e9ecef;">
                {endpoints}
            </p>
            
            <div class="section-title">Ação Recomendada (Gerada por IA)</div>
            <p style="color: #d35400; font-weight: bold;">{action}</p>
            
            <center>
                <a href="{url}" class="btn">Acessar Documentação Original</a>
            </center>
        </div>
        <div class="footer">
            Enviado automaticamente pelo <b>API Doc Sentinel</b>.<br>
            Você está recebendo este e-mail porque é o responsável técnico configurado no sistema.
        </div>
    </div>
</body>
</html>
"""


# =============================================================================
# FUNÇÃO DE ENVIO
# =============================================================================

def enviar_email_alerta(alerta: ChangeAlert, fonte: MonitoredSource) -> bool:
    """
    Formata e envia o e-mail de notificação de um alerta específico.

    Args:
        alerta: O objeto ChangeAlert gerado pelo workflow
        fonte: O objeto MonitoredSource relacionado ao alerta

    Returns:
        True se enviado com sucesso, False em caso de erro.
    """
    sender = os.getenv("EMAIL_SENDER")
    password = os.getenv("EMAIL_PASSWORD")
    recipient = os.getenv("EMAIL_RECIPIENT")
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))

    # Se as credenciais não estiverem configuradas, falha graciosamente
    if not sender or not password or not recipient:
        print(f"[Email] IGNORADO: Credenciais de e-mail não configuradas no .env. Alerta ID: {alerta.id}")
        return False

    # Evita enviar o e-mail genérico do template
    if sender == "remetente@dominio.com" or recipient == "destinatario@dominio.com":
        print(f"[Email] IGNORADO: Usando e-mails padrão do .env. Configure e-mails reais. Alerta ID: {alerta.id}")
        return False

    try:
        # Prepara a cor da severidade
        color = SEVERITY_COLORS.get(alerta.severity.upper(), "#6c757d")  # Padrão: Cinza

        # Prepara a badge de Breaking Change (se for o caso)
        breaking_html = ""
        prefixo_assunto = ""
        if alerta.is_breaking_change:
            breaking_html = '<span class="breaking-badge">⚠️ BREAKING CHANGE</span>'
            prefixo_assunto = "[BREAKING] "

        # Monta o assunto
        assunto = f"{prefixo_assunto}[{alerta.severity}] Atualização na API: {fonte.name}"

        # Trata lista de endpoints vazia
        endpoints_texto = alerta.affected_endpoints if alerta.affected_endpoints else "Não especificado."

        # Preenche o HTML
        html_body = HTML_TEMPLATE.format(
            color=color,
            severity=alerta.severity.upper(),
            breaking_html=breaking_html,
            source_name=fonte.name,
            summary=alerta.summary_ptbr.replace('\n', '<br>'),
            endpoints=endpoints_texto,
            action=alerta.recommended_action.replace('\n', '<br>'),
            url=fonte.url
        )

        # Configura as partes do e-mail
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"] = sender
        msg["To"] = recipient

        part = MIMEText(html_body, "html", "utf-8")
        msg.attach(part)

        # Conecta no SMTP e envia
        print(f"[Email] Conectando ao servidor SMTP ({host}:{port})...")
        server = smtplib.SMTP(host, port)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, recipient, msg.as_string())
        server.quit()

        print(f"[Email] SUCCESSO: E-mail enviado para {recipient} (Alerta {alerta.id})")
        return True

    except Exception as e:
        print(f"[Email] ERRO ao enviar e-mail (Alerta {alerta.id}): {e}")
        return False
