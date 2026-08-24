import streamlit as st
import pandas as pd
import io
import plotly.express as px
from google.oauth2 import service_account
from googleapiclient.discovery import build

# Importa o motor de auditoria (certifique-se de que a pasta 'src' possui um arquivo __init__.py vazio)
import src.auditoria_core as core

# ==========================================
# CONFIGURAÇÃO DO GOOGLE DRIVE
# ==========================================
ID_PASTA_DRIVE = "1crkkDka7Q0t5i6-TDMybk6eSB0MAdenX"

@st.cache_resource
def conectar_drive():
    """Lê as credenciais do cofre do Streamlit e conecta no Drive"""
    credenciais = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build('drive', 'v3', credentials=credenciais)

@st.cache_data(ttl=300)
def listar_arquivos_drive():
    """Busca os arquivos CSV na pasta do Google Drive"""
    try:
        drive_service = conectar_drive()
        query = f"'{ID_PASTA_DRIVE}' in parents and trashed=false and mimeType='text/csv'"
        resultados = drive_service.files().list(q=query, fields="files(id, name)").execute()
        return resultados.get('files', [])
    except Exception as e:
        st.error(f"Erro ao conectar com o Drive: {e}")
        return []

def baixar_arquivo_drive(file_id):
    """Baixa o arquivo para a memória temporária (BytesIO)"""
    drive_service = conectar_drive()
    request = drive_service.files().get_media(fileId=file_id)
    return io.BytesIO(request.execute())

# ==========================================
# INTERFACE GRÁFICA - DASHBOARD
# ==========================================
st.set_page_config(page_title="Auditoria PBCS - FIRAO", page_icon="✈️", layout="wide")

st.title("✈️ Painel de Auditoria de Capacidades Datalink (PBCS) - FIR-AO")
st.markdown("Plataforma automatizada para análise das capacidades e inconsistências de voos oceânicos.")
st.divider()

# 1. Busca lista de arquivos na nuvem
arquivos_disponiveis = listar_arquivos_drive()

if not arquivos_disponiveis:
    st.warning("Nenhum arquivo CSV encontrado na pasta do Google Drive conectada.")
    st.stop()

mapa_arquivos = {arq['name']: arq['id'] for arq in arquivos_disponiveis}

# 2. Configura a barra lateral
with st.sidebar:
    st.header("📂 ARQUIVOS")
    arquivos_selecionados = st.multiselect(
        "Selecione os extratos mensais:",
        options=list(mapa_arquivos.keys()),        
    )
    
    iniciar_analise = st.button("🚀 Processar Auditoria", use_container_width=True, type="primary")

# 3. Execução Principal
if iniciar_analise and arquivos_selecionados:
    with st.spinner("Baixando e higienizando dados. Aguarde..."):
        
        lista_dfs = []
        
        # =========================================================================
        # TRATAMENTO ANTI-FALHA DE CSV (HIGIENIZAÇÃO ESTRUTURAL)
        # =========================================================================
        for nome_arq in arquivos_selecionados:
            file_id = mapa_arquivos[nome_arq]
            arq_memoria = baixar_arquivo_drive(file_id)
            
            # Lê apenas a primeira linha do arquivo para descobrir o padrão
            primeira_linha = arq_memoria.readline().decode('utf-8', errors='ignore')
            
            # Identifica se o sistema gerou com ponto-e-vírgula ou vírgula
            separador = ';' if ';' in primeira_linha else ','
            
            # Limpa o cabeçalho arrancando aspas e espaços invisíveis
            cabecalhos_limpos = [c.strip().replace('"', '').replace("'", "") for c in primeira_linha.split(separador)]
            
            # Cria um "colchão" de 100 colunas para evitar que quebras de linha em observações
            # do despachante empurrem os dados para fora da tabela e quebrem o pandas
            nomes_seguros = [f"Extra_{i}" for i in range(100)]
            for i, cab in enumerate(cabecalhos_limpos):
                if i < 100:
                    nomes_seguros[i] = cab
                    
            # Retorna o "leitor" para o começo do arquivo (linha zero)
            arq_memoria.seek(0)
            
            # O Pandas agora lê o arquivo blindado, pulando a linha 1 original que era suja
            df_temp = pd.read_csv(
                arq_memoria, 
                sep=separador, 
                names=nomes_seguros, 
                skiprows=1, 
                dtype=str, 
                engine='python', 
                on_bad_lines='skip'
            )
            
            lista_dfs.append(df_temp)
            
        # Junta os meses selecionados em uma base única
        df_bruto = pd.concat(lista_dfs, ignore_index=True)
        
        # =========================================================================
        # EXECUÇÃO DA AUDITORIA
        # =========================================================================
        try:
            resultados = core.processar_dados(df_bruto)
        except Exception as e:
            st.error(f"Erro durante o processamento analítico: {e}")
            st.stop()
            
        st.success("Análise concluída com sucesso! Os dados foram validados e estruturados.")
        
        # =========================================================================
        # CONSTRUÇÃO DO PAINEL DE INDICADORES (TABS)
        # =========================================================================
        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 Visão Geral", 
            "🏢 Desempenho por Cia", 
            "📉 Ranking de Não Capacitadas", 
            "⚠️ Inconsistências de Declaração"
        ])
        
      # --- ABA 1: VISÃO GERAL ---
        with tab1:
            st.subheader("Capacidades Globais (Período Selecionado)")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total de Voos Efetivos", f"{resultados['total_terminado']:,}".replace(',', '.'))
            
            with col2:
                voos_fmt = f"{resultados['total_capacitados']:,}".replace(',', '.')
                pct_voos = f"{resultados['porcentagem_voos']:.1f}%"
                # Coloca a porcentagem ao lado do número, sem gerar a seta
                st.metric("Voos PBCS Declarados", f"{voos_fmt} ({pct_voos})")
                
            with col3:
                frota_fmt = f"{resultados['frota_capacitada']:,}".replace(',', '.')
                pct_frota = f"{resultados['pct_frota_cap']:.1f}%"
                # Coloca a porcentagem ao lado do número, sem gerar a seta
                st.metric("Frota Capacitada", f"{frota_fmt} ({pct_frota})")
            
            st.divider()
            
            # --- NOVA SESSÃO: PROGRESSÃO MENSAL ---
            st.subheader("Progressão Mensal")
            st.markdown("<span style='font-size: 0.9em; color: gray;'>Acompanhamento mês a mês da adesão das companhias aéreas ao Datalink (PBCS).</span>", unsafe_allow_html=True)
            
            df_evo = resultados['evolucao_mensal']
            
            if not df_evo.empty:
                # Criando máscaras de formatação no padrão brasileiro
                formato_int = lambda x: f"{int(x):,}".replace(',', '.')
                formato_pct = lambda x: f"{x:.1f}%"
                
                st.dataframe(
                    df_evo.style.format({
                        'Voos Efetivos': formato_int,
                        'Voos PBCS': formato_int,
                        '% Voos PBCS': formato_pct,
                        'Frota Ativa': formato_int,
                        'Frota PBCS': formato_int,
                        '% Frota PBCS': formato_pct
                    }),
                    use_container_width=True,
                    hide_index=True
                )
                
        # --- ABA 2: DESEMPENHO POR COMPANHIA ---
        with tab2:
            st.subheader("Análise Detalhada por Companhia Aérea")
            df_cia = resultados['relatorio_cia']
            st.dataframe(df_cia.style.format(precision=1), use_container_width=True, height=500, hide_index=True)
            
        # --- ABA 3: RANKING DE OFENSORES ---
        with tab3:
            st.subheader("Contribuição para a Taxa de Erro Global")
            df_ofensores = resultados['ranking_ofensores']
            
            if df_ofensores.empty:
                st.success("Excelente! Nenhum voo operou sem declarar a capacidade no período.")
            else:
                colA, colB = st.columns([2, 1])
                
                with colA:
                    # Gráfico atualizado com a nomenclatura diplomática
                    fig = px.bar(df_ofensores.head(10), 
                                 x='AIRLINE', y='VOOS_NAO_CAPACITADOS', 
                                 text='CONTRIBUICAO_PCT',
                                 title="Top 10 Companhias com Maior Volume de Inconsistências",
                                 labels={'VOOS_NAO_CAPACITADOS': 'Voos Não Capacitados', 'AIRLINE': 'Companhia'},
                                 color='VOOS_NAO_CAPACITADOS', color_continuous_scale='Reds')
                    
                    fig.update_traces(texttemplate='%{text:.1f}%', textposition='outside')
                    fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
                    st.plotly_chart(fig, use_container_width=True)
                    
                with colB:
                    # Tabela limpa (hide_index=True) escondendo a numeração lateral
                    st.dataframe(
                        df_ofensores[['AIRLINE', 'VOOS_NAO_CAPACITADOS', 'CONTRIBUICAO_PCT']].head(20).style.format({'CONTRIBUICAO_PCT': "{:.2f}%"}), 
                        use_container_width=True, 
                        height=450,
                        hide_index=True 
                    )
                    
        # --- ABA 4: AERONAVES COM INCONSISTÊNCIAS (DETALHAMENTO) ---
        with tab4:
            st.subheader("Auditoria de Flutuação de Capacidades (Mesma Aeronave)")
            st.markdown("Aeronaves que **alteraram sua declaração de capacidades entre voos**. Revela erros de preenchimento de plano de voo.")
            
            df_inconsistentes = resultados['voos_inconsistentes']
            ranking_inconsistentes = resultados['ranking_inconsistentes']
            
            if ranking_inconsistentes.empty:
                st.success("EXCELENTE: Nenhuma aeronave declarou capacidades conflitantes no período.")
            else:
                qtd_inconsistentes = len(ranking_inconsistentes)
                st.warning(f"⚠️ ALERTA: {qtd_inconsistentes} aeronaves apresentaram flutuação de capacidade entre seus voos.")
                
                st.markdown("#### Top Aeronaves com Declarações Conflitantes")
                # Tabela de Ranking
                st.dataframe(
                    ranking_inconsistentes,
                    use_container_width=True,
                    hide_index=True
                )
                
                st.divider()
                st.markdown("#### Detalhamento dos Voos (Rastreabilidade do Erro)")
                
                # Seleciona as colunas focando no cruzamento Registro vs Categoria
                colunas_auditoria = ['REGISTRO', 'CATEGORIA_PBCS', 'AIRLINE', 'ID_VOO', 'INDICATIVE', 'EQUIP', 'ADD_INFO', 'ADEP', 'ADES', 'EOBD']
                colunas_presentes = [c for c in colunas_auditoria if c in df_inconsistentes.columns]
                
                # ORDENA pela matrícula (Registro). Assim, os voos da mesma aeronave ficam agrupados
                # e o usuário vê a coluna CATEGORIA_PBCS mudando de valor nas linhas vizinhas.
                df_view = df_inconsistentes[colunas_presentes].sort_values(by=['REGISTRO', 'EOBD'])
                
                # Tabela de Detalhamento
                st.dataframe(
                    df_view,
                    use_container_width=True,
                    height=500,
                    hide_index=True
                )