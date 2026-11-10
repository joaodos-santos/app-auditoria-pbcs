"""
=============================================================================
PROJETO: Painel de Auditoria de Capacidades Datalink (PBCS) - FIR-AO
ARQUIVO: main.py (Interface Gráfica e Orquestrador)
=============================================================================
"""
import streamlit as st
import pandas as pd
import io
import os
import plotly.express as px
from google.oauth2 import service_account
from googleapiclient.discovery import build

import src.auditoria_core as core

# ==========================================
# CONFIGURAÇÃO DE AMBIENTE
# ==========================================
MODO_LOCAL = True
PASTA_TESTE_LOCAL = "dados_teste"
ID_PASTA_DRIVE = "1crkkDka7Q0t5i6-TDMybk6eSB0MAdenX"

@st.cache_resource
def conectar_drive():
    credenciais = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=credenciais)

@st.cache_data(ttl=300)
def listar_arquivos():
    if MODO_LOCAL:
        if not os.path.exists(PASTA_TESTE_LOCAL):
            os.makedirs(PASTA_TESTE_LOCAL)
        arquivos = [f for f in os.listdir(PASTA_TESTE_LOCAL) if f.lower().endswith('.csv')]
        return [{'name': f, 'id': os.path.join(PASTA_TESTE_LOCAL, f)} for f in arquivos]
    else:
        try:
            drive_service = conectar_drive()
            query = f"'{ID_PASTA_DRIVE}' in parents and trashed=false and mimeType='text/csv'"
            resultados = drive_service.files().list(q=query, fields="files(id, name)").execute()
            return resultados.get('files', [])
        except Exception as e:
            st.error(f"Erro ao conectar com o Drive: {e}")
            return []

def obter_arquivo_memoria(file_id):
    if MODO_LOCAL:
        with open(file_id, 'rb') as f:
            return io.BytesIO(f.read())
    else:
        drive_service = conectar_drive()
        request = drive_service.files().get_media(fileId=file_id)
        return io.BytesIO(request.execute())

# ==========================================
# INTERFACE GRÁFICA - DASHBOARD
# ==========================================
st.set_page_config(page_title="Auditoria PBCS - FIRAO", page_icon="✈️", layout="wide")

st.title("✈️ Painel de Auditoria de Capacidades Datalink (PBCS) - FIR-AO")
st.divider()

arquivos_disponiveis = listar_arquivos()

if not arquivos_disponiveis:
    if MODO_LOCAL:
        st.warning(f"Nenhum arquivo CSV encontrado na pasta local '{PASTA_TESTE_LOCAL}'.")
    else:
        st.warning("Nenhum arquivo CSV encontrado no Google Drive.")
    st.stop()

mapa_arquivos = {arq['name']: arq['id'] for arq in arquivos_disponiveis}

with st.sidebar:
    st.header("📂 ARQUIVOS")
    if MODO_LOCAL:
        st.info("⚠️ MODO DE TESTE LOCAL")
        
    arquivos_selecionados = st.multiselect(
        "Selecione os extratos mensais:",
        options=list(mapa_arquivos.keys()),        
    )
    
    iniciar_analise = st.button("🚀 Processar Auditoria", width='stretch', type="primary")

# ==========================================
# MOTOR DE PROCESSAMENTO (SÓ RODA NO CLIQUE DO BOTÃO)
# ==========================================
if iniciar_analise and arquivos_selecionados:
    with st.spinner("Baixando e higienizando dados. Aguarde..."):
        lista_dfs = []
        for nome_arq in arquivos_selecionados:
            file_id = mapa_arquivos[nome_arq]
            arq_memoria = obter_arquivo_memoria(file_id)
            primeira_linha = arq_memoria.readline().decode('utf-8', errors='ignore')
            separador = ';' if ';' in primeira_linha else ','
            cabecalhos_limpos = [c.strip().replace('"', '').replace("'", "") for c in primeira_linha.split(separador)]
            
            nomes_seguros = [f"Extra_{i}" for i in range(100)]
            for i, cab in enumerate(cabecalhos_limpos):
                if i < 100:
                    nomes_seguros[i] = cab
                    
            arq_memoria.seek(0)
            df_temp = pd.read_csv(
                arq_memoria, sep=separador, names=nomes_seguros, 
                skiprows=1, dtype=str, engine='python', on_bad_lines='skip'
            )
            lista_dfs.append(df_temp)
            
        df_bruto = pd.concat(lista_dfs, ignore_index=True)
        
        try:
            # Salva na memória do navegador para não sumir!
            st.session_state['resultados'] = core.processar_dados(df_bruto)
        except Exception as e:
            st.error(f"Erro durante o processamento: {e}")
            st.stop()
            
        st.success("Análise concluída com sucesso!")

# ==========================================
# RENDERIZAÇÃO DAS ABAS (COLADO NA MARGEM ESQUERDA)
# ==========================================
# Isso garante que a tela nunca apague ao interagir com filtros
if 'resultados' in st.session_state:
    resultados = st.session_state['resultados']
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Visão Geral", 
        "🏢 Desempenho por Cia", 
        "📉 Ranking de Não Capacitadas", 
        "⚠️ Inconsistências de Declaração",
        "🛩️ Capacidades de Frota"
    ])
    
    # --- ABA 1 ---
    with tab1:
        st.subheader("Capacidades Globais (Período Selecionado)")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total de Voos Efetivos", f"{resultados['total_terminado']:,}".replace(',', '.'))
        with col2:
            voos_fmt = f"{resultados['total_capacitados']:,}".replace(',', '.')
            pct_voos = f"{resultados['porcentagem_voos']:.1f}%"
            st.metric("Voos PBCS Declarados", f"{voos_fmt} ({pct_voos})")
        with col3:
            frota_fmt = f"{resultados['frota_capacitada']:,}".replace(',', '.')
            pct_frota = f"{resultados['pct_frota_cap']:.1f}%"
            st.metric("Frota Capacitada", f"{frota_fmt} ({pct_frota})")
        
        st.divider()
        st.subheader("Progressão Mensal")
        df_evo = resultados['evolucao_mensal']
        if not df_evo.empty:
            formato_int = lambda x: f"{int(x):,}".replace(',', '.')
            formato_pct = lambda x: f"{x:.1f}%"
            st.dataframe(
                df_evo.style.format({
                    'Voos Efetivos': formato_int, 'Voos PBCS': formato_int, '% Voos PBCS': formato_pct,
                    'Frota Ativa': formato_int, 'Frota PBCS': formato_int, '% Frota PBCS': formato_pct
                }),
                width='stretch', hide_index=True
            )
            
    # --- ABA 2 ---
    with tab2:
        st.subheader("Análise Detalhada por Companhia Aérea")
        st.dataframe(resultados['relatorio_cia'].style.format(precision=1), width='stretch', height=500, hide_index=True)
        
    # --- ABA 3 ---
    with tab3:
        st.subheader("Contribuição para a Taxa de Erro Global")
        df_ofensores = resultados['ranking_ofensores']
        if df_ofensores.empty:
            st.success("Nenhum voo operou sem declarar a capacidade no período.")
        else:
            colA, colB = st.columns([2, 1])
            with colA:
                fig = px.bar(df_ofensores.head(10), x='AIRLINE', y='VOOS_NAO_CAPACITADOS', text='CONTRIBUICAO_PCT',
                             title="Top 10 Companhias com Maior Volume de Inconsistências",
                             color='VOOS_NAO_CAPACITADOS', color_continuous_scale='Reds')
                fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                st.plotly_chart(fig, width='stretch')
            with colB:
                st.dataframe(df_ofensores[['AIRLINE', 'VOOS_NAO_CAPACITADOS', 'CONTRIBUICAO_PCT']].head(20).style.format({'CONTRIBUICAO_PCT': "{:.2f}%"}), width='stretch', height=450, hide_index=True)
                
    # --- ABA 4 ---
    with tab4:
        st.subheader("Auditoria de Flutuação de Capacidades (Mesma Aeronave)")
        df_inconsistentes = resultados['voos_inconsistentes']
        ranking_inconsistentes = resultados['ranking_inconsistentes']
        
        if ranking_inconsistentes.empty:
            st.success("Nenhuma aeronave declarou capacidades conflitantes no período.")
        else:
            st.warning(f"⚠️ ALERTA: {len(ranking_inconsistentes)} aeronaves apresentaram flutuação de capacidade.")
            st.dataframe(ranking_inconsistentes, width='stretch', hide_index=True)
            st.divider()
            colunas_presentes = [c for c in ['REGISTRO', 'CATEGORIA_PBCS', 'AIRLINE', 'ID_VOO', 'INDICATIVE', 'EQUIP', 'ADD_INFO', 'ADEP', 'ADES', 'EOBD'] if c in df_inconsistentes.columns]
            st.dataframe(df_inconsistentes[colunas_presentes].sort_values(by=['REGISTRO', 'EOBD']), width='stretch', height=500, hide_index=True)

    # --- ABA 5 (CAPACIDADES) ---
    with tab5:
        st.subheader("Análise de Capacidades da Frota (Item 4.1)")
        
        # Puxa os totais e as duas tabelas (Frota e Voos)
        df_frota_cap = resultados['df_frota_capacidades']
        total_frota = resultados['total_frota']
        
        df_voos_cap = resultados['df_processado']
        total_voos = resultados['total_terminado']

        mapa_capacidades = {
            'RNP 10': 'CAP_RNP10', 
            'RNP 4': 'CAP_RNP4', 
            'NÃO RNP': 'CAP_NAO_RNP',  # <-- NOVO FILTRO INSERIDO AQUI
            'CPDLC (Satélite)': 'CAP_CPDLC',
            'ADS-C (FANS 1/A)': 'CAP_ADSC', 
            'ADS-B (1090 MHz)': 'CAP_ADSB',
            'RCP 240': 'CAP_RCP', 
            'RSP 180': 'CAP_RSP', 
            'Eligível PBCS': 'CAP_PBCS'
        }

        selecao = st.multiselect(
            "Selecione uma ou mais capacidades (A aeronave/voo deverá ter TODAS as selecionadas):",
            options=list(mapa_capacidades.keys()),
            default=['RNP 4', 'RCP 240']
        )

        if selecao:
            colunas_filtro = [mapa_capacidades[item] for item in selecao]
            
            # --- CÁLCULO DE FROTA ---
            frota_filtrada = df_frota_cap[df_frota_cap[colunas_filtro].all(axis=1)]
            qtd_frota = len(frota_filtrada)
            pct_frota = (qtd_frota / total_frota) * 100 if total_frota > 0 else 0

            # --- CÁLCULO DE VOOS ---
            voos_filtrados = df_voos_cap[df_voos_cap[colunas_filtro].all(axis=1)]
            qtd_voos = len(voos_filtrados)
            pct_voos = (qtd_voos / total_voos) * 100 if total_voos > 0 else 0

            # --- RENDERIZAÇÃO LADO A LADO ---
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric(
                    label=f"✈️ FROTA ÚNICA ({' + '.join(selecao)})", 
                    value=f"{qtd_frota} aeronaves exclusivas", 
                    delta=f"{pct_frota:.2f}% da Frota Total ({total_frota:,})",
                    delta_color="off"
                )
                
            with col2:
                st.metric(
                    label=f"🛫 VOOS EFETIVOS ({' + '.join(selecao)})", 
                    value=f"{qtd_voos} planos de voo", 
                    delta=f"{pct_voos:.2f}% do Total de Voos ({total_voos:,})",
                    delta_color="off"
                )

            st.divider()
            st.subheader("Relação de Matrículas Atendidas pelo Filtro")
            st.dataframe(frota_filtrada[['REGISTRO'] + colunas_filtro], use_container_width=True, hide_index=True)
        else:
            st.info("Selecione pelo menos uma capacidade acima para ver as estatísticas operacionais.")