import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import glob
from src.auditoria_core import processar_dados

# =============================================================================
# 1. CONFIGURAÇÃO DA PÁGINA
# =============================================================================
st.set_page_config(
    page_title="Painel de Auditoria PBCS",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização em CSS
st.markdown("""
    <style>
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 8px;
        padding: 15px;
        border-left: 5px solid #005088;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# =============================================================================
# 2. CABEÇALHO E SELEÇÃO DE ARQUIVOS LOCAIS
# =============================================================================
st.title("✈️ Auditoria Integrada Datalink (PBCS)")
st.markdown("Selecione os arquivos de extração do ATC armazenados na sua pasta local para gerar os relatórios.")

# Garante que a pasta existe para não dar erro
PASTA_INPUTS = os.path.join("data", "inputs")
os.makedirs(PASTA_INPUTS, exist_ok=True)

# Lista todos os arquivos CSV na pasta
arquivos_disponiveis = glob.glob(os.path.join(PASTA_INPUTS, "*.csv"))
nomes_arquivos = [os.path.basename(f) for f in arquivos_disponiveis]

if not nomes_arquivos:
    st.warning(f"⚠️ Nenhum arquivo CSV encontrado na pasta `{PASTA_INPUTS}`. Coloque os extratos lá para começar.")
else:
    # Menu de Múltipla Escolha
    arquivos_selecionados = st.multiselect(
        "Selecione um ou mais meses para analisar (O sistema unificará os dados automaticamente):",
        options=nomes_arquivos,
        default=nomes_arquivos if len(nomes_arquivos) == 1 else []
    )

    btn_processar = st.button("🚀 Processar Auditoria", type="primary")

    # =============================================================================
    # 3. NÚCLEO DA APLICAÇÃO (PROCESSAMENTO)
    # =============================================================================
    if btn_processar and arquivos_selecionados:
        
        # Reconstrói os caminhos completos dos arquivos escolhidos
        caminhos_completos = [os.path.join(PASTA_INPUTS, f) for f in arquivos_selecionados]
        
        try:
            with st.spinner('Processando malha fina e cruzando matrizes...'):
                resultados = processar_dados(caminhos_completos)
                
            metricas = resultados['metricas']
            dfs = resultados['dataframes']
            periodo = resultados['periodo']
            
            st.success(f"✅ Processamento concluído! Período analisado: **{periodo}** (Voos: {metricas['total_terminado']:,})")
            
            # =====================================================================
            # 4. CONSTRUÇÃO DA INTERFACE EM ABAS (TABS)
            # =====================================================================
            tab1, tab2, tab3, tab4, tab5 = st.tabs([
                "📊 Resumo Executivo", 
                "🏢 Desempenho por Cia", 
                "🚨 Ranking de Ofensores", 
                "🔎 Auditoria de Flutuação",
                "⬇️ Exportar Relatórios"
            ])

            # ---------------------------------------------------------------------
            # ABA 1: RESUMO EXECUTIVO (KPIs)
            # ---------------------------------------------------------------------
            with tab1:
                st.header("Visão Geral do Tráfego e Frota")
                
                # Linha 1: Métricas de Voo
                st.subheader("1. Análise de Voos (Efetivos)")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Lido nos Arquivos", f"{metricas['total_bruto']:,}")
                col2.metric("Falsos Voos (Descartados)", f"{metricas['total_falsos_voos']:,}")
                col3.metric("Voos Efetivos (Base)", f"{metricas['total_terminado']:,}")
                col4.metric("Homologação Datalink", f"{metricas['porcentagem_voos']:.2f}%")
                
                st.markdown("---")
                
                # Linha 2: Métricas de Frota e Preenchimento
                st.subheader("2. Análise de Frota e Qualidade")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Planos s/ Matrícula (REG/)", f"{metricas['qtd_sem_reg']:,}")
                col2.metric("Frota Única (Aeronaves)", f"{metricas['total_frota']:,}")
                col3.metric("Frota Capacitada (PBCS)", f"{metricas['frota_capacitada']:,}")
                col4.metric("Conformidade da Frota", f"{metricas['pct_frota_cap']:.2f}%")

                # Gráfico Rápido: Distribuição de Capacidade (Voos)
                st.markdown("<br>", unsafe_allow_html=True)
                labels = ['PBCS RNP4 RNP10', 'PBCS RNP4', 'PBCS RNP10', 'NÃO CAPACITADOS']
                valores = [metricas['voos_ambos'], metricas['voos_rnp4'], metricas['voos_rnp10'], metricas['voos_nao_cap']]
                
                fig_pizza = px.pie(
                    names=labels, 
                    values=valores, 
                    title="Distribuição das Categorias PBN/PBCS nos Voos Efetivos",
                    color_discrete_sequence=px.colors.qualitative.Prism,
                    hole=0.4
                )
                st.plotly_chart(fig_pizza, use_container_width=True)

            # ---------------------------------------------------------------------
            # ABA 2: DESEMPENHO POR COMPANHIA AÉREA
            # ---------------------------------------------------------------------
            with tab2:
                st.header("Desempenho Interno por Companhia")
                st.markdown("Cruza o volume total de operações e frota com o nível de conformidade aprovada.")
                
                df_cias = dfs['desempenho_cias']
                
                # Gráfico de Barras: Volume de voos
                top_cias = df_cias.head(15).copy()
                top_cias = top_cias.sort_values('TOTAL_VOOS', ascending=True)
                
                fig_barras_cias = px.bar(
                    top_cias, 
                    x='TOTAL_VOOS', 
                    y='AIRLINE', 
                    orientation='h',
                    title="Top 15 Companhias em Volume de Voos",
                    text='TOTAL_VOOS',
                    color='PCT_VOOS',
                    color_continuous_scale='Blues',
                    labels={'PCT_VOOS': 'Aprovação PBCS (%)', 'AIRLINE': 'Companhia', 'TOTAL_VOOS': 'Voos Totais'}
                )
                st.plotly_chart(fig_barras_cias, use_container_width=True)
                
                # Tabela Completa
                st.subheader("Tabela Consolidada (Todas as Operadoras)")
                st.dataframe(
                    df_cias.style.format({
                        'PCT_VOOS': '{:.2f}%',
                        'PCT_FROTA': '{:.2f}%'
                    }),
                    use_container_width=True,
                    height=400
                )

            # ---------------------------------------------------------------------
            # ABA 3: RANKING DE OFENSORES
            # ---------------------------------------------------------------------
            with tab3:
                st.header("Matriz de Impacto e Contribuição de Falha")
                st.markdown("Quais companhias aéreas injetaram o maior volume de voos irregulares na FIR oceânica.")
                
                df_ofensores = dfs['ranking_ofensores']
                
                if df_ofensores.empty:
                    st.success("EXCELENTE: Nenhum voo reprovado no período. 100% de conformidade global.")
                else:
                    col_of_1, col_of_2 = st.columns([2, 1])
                    
                    with col_of_2:
                        st.info(f"""
                        **Resumo do Problema:**
                        - Total de Voos Irregulares: **{metricas['voos_nao_cap']:,}**
                        - Isso representa **{(metricas['voos_nao_cap']/metricas['total_terminado'])*100:.2f}%** do tráfego total.
                        """)
                        st.dataframe(
                            df_ofensores[['AIRLINE', 'VOOS_FALHOS', 'CONTRIBUICAO_PCT', 'IMPACTO_ABSOLUTO_PCT']].style.format({
                                'CONTRIBUICAO_PCT': '{:.2f}%',
                                'IMPACTO_ABSOLUTO_PCT': '{:.2f}%'
                            }),
                            use_container_width=True,
                            height=400
                        )

                    with col_of_1:
                        top10_ofensores = df_ofensores.head(10).sort_values('VOOS_FALHOS', ascending=True)
                        fig_ofensores = px.bar(
                            top10_ofensores,
                            x='VOOS_FALHOS',
                            y='AIRLINE',
                            orientation='h',
                            title="Top 10 Ofensores (Volume de Erros Absoluto)",
                            text='VOOS_FALHOS',
                            color='CONTRIBUICAO_PCT',
                            color_continuous_scale='Reds',
                            labels={'CONTRIBUICAO_PCT': '% da Culpa Global', 'AIRLINE': 'Companhia', 'VOOS_FALHOS': 'Quantidade de Erros'}
                        )
                        st.plotly_chart(fig_ofensores, use_container_width=True)

            # ---------------------------------------------------------------------
            # ABA 4: AUDITORIA DE FLUTUAÇÃO
            # ---------------------------------------------------------------------
            with tab4:
                st.header("Malha Fina: Flutuação de Capacidade")
                st.markdown("Aeronaves que operaram na FIR com fitas preenchidas de forma conflitante (ora indicam PBCS, ora omitem).")
                
                if metricas['qtd_inconsistentes'] == 0:
                    st.success("Nenhuma aeronave declarou capacidades conflitantes neste período.")
                else:
                    st.warning(f"⚠️ ATENÇÃO: Identificadas **{metricas['qtd_inconsistentes']}** aeronaves com dupla personalidade de preenchimento.")
                    
                    df_inconsistentes = dfs['inconsistentes']
                    st.dataframe(df_inconsistentes, use_container_width=True, height=500)

            # ---------------------------------------------------------------------
            # ABA 5: DOWNLOADS
            # ---------------------------------------------------------------------
            with tab5:
                st.header("Exportação de Base de Dados")
                st.markdown("Baixe as tabelas completas geradas pelo motor no formato CSV para uso no Excel/Calc.")
                
                def convert_df(df):
                    return df.to_csv(index=False, sep=';', encoding='utf-8-sig')

                col_btn1, col_btn2 = st.columns(2)
                
                with col_btn1:
                    st.download_button(
                        label="📥 Baixar Voos Capacitados (Base Limpa)",
                        data=convert_df(dfs['voos_capacitados']),
                        file_name=f"{periodo}_voos_capacitados.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                    st.download_button(
                        label="📥 Baixar Desempenho por Companhia",
                        data=convert_df(dfs['desempenho_cias']),
                        file_name=f"{periodo}_desempenho_cias.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                with col_btn2:
                    if not df_ofensores.empty:
                        st.download_button(
                            label="🚨 Baixar Ranking de Ofensores",
                            data=convert_df(dfs['ranking_ofensores']),
                            file_name=f"{periodo}_ranking_ofensores.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                    
                    if metricas['qtd_inconsistentes'] > 0:
                        st.download_button(
                            label="🔎 Baixar Log de Flutuação (Malha Fina)",
                            data=convert_df(dfs['inconsistentes']),
                            file_name=f"{periodo}_auditoria_flutuacao_capacidade.csv",
                            mime="text/csv",
                            use_container_width=True
                        )

        except ValueError as e:
            st.error(f"⚠️ Erro nos dados: {e}")
        except Exception as e:
            st.error(f"⚠️ Ocorreu um erro inesperado no processamento: {e}")
    
    elif btn_processar and not arquivos_selecionados:
        st.error("⚠️ Você precisa selecionar pelo menos um arquivo na lista acima antes de processar.")