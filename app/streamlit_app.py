"""
app/streamlit_app.py
====================
Painel Administrativo para o API Doc Sentinel.

POR QUE EXISTE:
    Permite que qualquer pessoa do time (não apenas devs) consiga
    cadastrar novas URLs, ver o status do monitoramento e ler o histórico
    de alertas gerados pela IA.

COMO FUNCIONA:
    Este app não acessa o banco de dados diretamente. Ele consome a
    nossa API (FastAPI) rodando em http://localhost:8000.
    Isso garante a separação limpa entre Frontend e Backend.
"""

import streamlit as st
import requests
import time
from datetime import datetime

# =============================================================================
# CONFIGURAÇÃO DA PÁGINA
# =============================================================================

st.set_page_config(
    page_title="API Doc Sentinel",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# URL base da nossa API Backend
API_URL = "http://127.0.0.1:8000/api"


# =============================================================================
# FUNÇÕES DE CHAMADA À API
# =============================================================================

@st.cache_data(ttl=5)  # Cache de 5 segundos para não spammar a API
def get_sources():
    try:
        r = requests.get(f"{API_URL}/sources")
        return r.json() if r.status_code == 200 else []
    except:
        return []

@st.cache_data(ttl=5)
def get_alerts():
    try:
        r = requests.get(f"{API_URL}/alerts")
        return r.json() if r.status_code == 200 else []
    except:
        return []

def forcar_sincronizacao(source_id: int):
    try:
        r = requests.post(f"{API_URL}/check-now/{source_id}")
        if r.status_code == 200:
            st.toast("Verificação iniciada em background!", icon="⏳")
        else:
            st.error(f"Erro ao forçar verificação: {r.text}")
    except Exception as e:
        st.error(f"Falha de conexão: {e}")

def toggle_status(source_id: int, current_status: bool):
    try:
        novo_status = not current_status
        r = requests.patch(f"{API_URL}/sources/{source_id}/status", params={"is_active": novo_status})
        if r.status_code == 200:
            st.toast("Status alterado com sucesso!", icon="✅")
            # Limpa o cache para atualizar a tela
            get_sources.clear()
            st.rerun()
        else:
            st.error(f"Erro ao alterar status: {r.text}")
    except Exception as e:
        st.error(f"Falha de conexão: {e}")


# =============================================================================
# LAYOUT PRINCIPAL
# =============================================================================

st.title("🛡️ API Doc Sentinel")
st.markdown("Serviço autônomo de auditoria técnica guiado por IA.")

# Verifica se o Backend está rodando
try:
    requests.get(f"{API_URL.replace('/api', '')}/", timeout=5)
except requests.exceptions.RequestException:
    st.error("🚨 ERRO: O Backend (FastAPI) não está rodando. Por favor, execute `uv run uvicorn main:app` em outro terminal.")
    st.stop()


# Abas do Painel
tab_monit, tab_alertas, tab_cadastro = st.tabs([
    "📊 Fontes Monitoradas", 
    "🔔 Histórico de Alertas", 
    "➕ Cadastrar URL"
])


# =============================================================================
# ABA 1: FONTES MONITORADAS
# =============================================================================

with tab_monit:
    st.header("URLs em Monitoramento")
    
    fontes = get_sources()
    
    if not fontes:
        st.info("Nenhuma fonte cadastrada ainda. Vá para a aba 'Cadastrar URL'.")
    else:
        # Pega estatísticas rápidas
        ativas = sum(1 for f in fontes if f["is_active"])
        st.caption(f"Total de fontes: **{len(fontes)}** | Ativas: **{ativas}**")
        
        # Cria as colunas do cabeçalho da tabela
        cols = st.columns([0.5, 3, 2, 1, 1, 1])
        cols[0].write("**ID**")
        cols[1].write("**Nome da API**")
        cols[2].write("**URL da Documentação**")
        cols[3].write("**Status**")
        cols[4].write("**Ação**")
        cols[5].write("**Manual**")
        st.divider()
        
        for f in fontes:
            c = st.columns([0.5, 3, 2, 1, 1, 1])
            c[0].write(f["id"])
            c[1].write(f["name"])
            
            # URL clicável encurtada
            display_url = f["url"][:40] + "..." if len(f["url"]) > 40 else f["url"]
            c[2].markdown(f"[{display_url}]({f['url']})")
            
            # Status Badge
            if f["is_active"]:
                c[3].markdown("🟢 **Ativa**")
            else:
                c[3].markdown("⏸️ **Pausada**")
            
            # Botão de Ativar/Pausar
            label = "Pausar" if f["is_active"] else "Ativar"
            if c[4].button(label, key=f"btn_status_{f['id']}"):
                toggle_status(f["id"], f["is_active"])
                
            # Botão de Sincronizar Agora
            if c[5].button("🔄 Check", key=f"btn_sync_{f['id']}", disabled=not f["is_active"]):
                forcar_sincronizacao(f["id"])


# =============================================================================
# ABA 2: HISTÓRICO DE ALERTAS
# =============================================================================

with tab_alertas:
    st.header("Alertas Detectados pela IA")
    
    # Filtro simples
    apenas_relevantes = st.toggle("Mostrar apenas mudanças relevantes de engenharia", value=True)
    
    alertas = get_alerts()
    
    if apenas_relevantes:
        alertas = [a for a in alertas if a["severity"] in ["MEDIA", "ALTA", "CRITICA"]]
        
    if not alertas:
        st.success("Nenhum alerta para exibir com o filtro atual. Tudo tranquilo! ✨")
    else:
        for alerta in alertas:
            # Seleciona cor baseada na severidade
            color = "gray"
            if alerta["severity"] == "CRITICA": color = "red"
            elif alerta["severity"] == "ALTA": color = "orange"
            elif alerta["severity"] == "MEDIA": color = "yellow"
            elif alerta["severity"] == "BAIXA": color = "blue"
            
            # Descobre o nome da fonte
            fonte_nome = next((f["name"] for f in fontes if f["id"] == alerta["source_id"]), f"Fonte ID {alerta['source_id']}")
            
            # Badge de Breaking Change
            breaking = " ⚠️ **[BREAKING CHANGE]**" if alerta["is_breaking_change"] else ""
            
            # Data formatada
            try:
                data_obj = datetime.fromisoformat(alerta["created_at"])
                data_str = data_obj.strftime("%d/%m/%Y %H:%M")
            except:
                data_str = alerta["created_at"]
                
            with st.expander(f":{color}[{alerta['severity']}] {fonte_nome} - {data_str}{breaking}", expanded=(alerta["severity"] == "CRITICA")):
                st.markdown(f"**Resumo:** {alerta['summary_ptbr']}")
                st.markdown(f"**Endpoints afetados:** `{alerta['affected_endpoints']}`")
                st.info(f"**Recomendação da IA:** {alerta['recommended_action']}")
                
                # Check se e-mail foi enviado
                if alerta["notified_by_email"]:
                    st.caption("📧 E-mail de notificação enviado com sucesso.")
                else:
                    st.caption("⏳ E-mail não enviado (Pendente ou Falha de credenciais).")


# =============================================================================
# ABA 3: CADASTRAR URL
# =============================================================================

with tab_cadastro:
    st.header("Adicionar Nova Documentação")
    
    with st.form("form_nova_fonte"):
        nome = st.text_input("Nome da API / Serviço", placeholder="Ex: Stripe - Payouts API")
        url = st.text_input("URL da Documentação", placeholder="https://stripe.com/docs/api/payouts")
        intervalo = st.selectbox("Frequência de Verificação", options=[
            (60, "A cada 1 Hora"),
            (360, "A cada 6 Horas"),
            (720, "A cada 12 Horas"),
            (1440, "Uma vez por Dia (Recomendado)"),
            (10080, "Uma vez por Semana")
        ], format_func=lambda x: x[1])
        
        submit = st.form_submit_button("Cadastrar API")
        
        if submit:
            if not nome or not url:
                st.error("Por favor, preencha o Nome e a URL.")
            else:
                payload = {
                    "name": nome,
                    "url": url,
                    "check_interval_minutes": intervalo[0]
                }
                try:
                    r = requests.post(f"{API_URL}/sources", json=payload)
                    if r.status_code == 200:
                        st.success(f"API '{nome}' cadastrada com sucesso! Ela já começará a ser monitorada no próximo ciclo.")
                        get_sources.clear()  # Limpa o cache para mostrar na Aba 1
                    else:
                        st.error(f"Falha ao cadastrar: {r.json().get('detail', r.text)}")
                except Exception as e:
                    st.error(f"Falha de conexão com o servidor: {e}")
