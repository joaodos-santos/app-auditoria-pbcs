import pandas as pd
import io

def processar_dados(arquivo_csv):
    """
    Motor principal da auditoria PBCS.
    Recebe um arquivo (do Streamlit ou disco) e retorna um dicionário com métricas e DataFrames.
    """
    # =========================================================================
    # 1. CARREGAMENTO E LIMPEZA ESTRUTURAL
    # =========================================================================
    try:
        # Se for um arquivo upado via Streamlit, ele vem como BytesIO
        if hasattr(arquivo_csv, 'read'):
            linha1 = arquivo_csv.readline().decode('utf-8', errors='ignore')
            arquivo_csv.seek(0) # Volta o ponteiro para o início para o pandas ler tudo
        else:
            # Fallback caso rode apontando um caminho no disco
            with open(arquivo_csv, 'r', encoding='utf-8', errors='ignore') as f:
                linha1 = f.readline()
                
        separador = ';' if ';' in linha1 else ','
        cabecalhos_limpos = [c.strip().replace('"', '').replace("'", "") for c in linha1.split(separador)]
        
        nomes_seguros = [f"Extra_{i}" for i in range(50)]
        for i, cab in enumerate(cabecalhos_limpos):
            nomes_seguros[i] = cab
            
        df = pd.read_csv(arquivo_csv, sep=separador, names=nomes_seguros, skiprows=1, dtype=str, engine='python')
    except Exception as e:
        raise ValueError(f"Falha ao ler o arquivo CSV. Verifique o formato. Detalhe: {e}")

    total_bruto_arquivo = len(df)
    
    colunas_para_remover = [
        'FILLED_BY', 'ANAC_FILLED_BY', 'ACTIVATION', 
        'PILOT_CMD', 'PILOT_ANAC', 'DAY_OF_WEEK', 'FLIGHT_RULE', 'ATS_TYPE'
    ]
    df = df.drop(columns=colunas_para_remover, errors='ignore')

    colunas_texto = ['EQUIP', 'ADD_INFO', 'INDICATIVE', 'ROUTE', 'ADEP', 'ADES', 'EOBD', 'EOBT', 'STATE', 'AIRLINE', 'FINISH_REASON']
    for col in colunas_texto:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str).str.strip().str.upper()

    if 'AIRLINE' in df.columns:
        df.loc[df['AIRLINE'] == '', 'AIRLINE'] = 'NAO_INFORMADA'

    # =========================================================================
    # 2. AUTO-CORREÇÃO DE COMPANHIAS AÉREAS
    # =========================================================================
    cias_declaradas = set(df.loc[df['AIRLINE'] != 'NAO_INFORMADA', 'AIRLINE'].unique())
    mask_nao_informada = df['AIRLINE'] == 'NAO_INFORMADA'
    prefixos = df['INDICATIVE'].str[:3]
    
    mask_match = mask_nao_informada & prefixos.isin(cias_declaradas)
    df.loc[mask_match, 'AIRLINE'] = prefixos[mask_match]
    df.loc[df['AIRLINE'] == 'NAO_INFORMADA', 'AIRLINE'] = 'GERAL/MILITAR'

    # =========================================================================
    # 3. FILTRAGEM REAL DE TRÁFEGO
    # =========================================================================
    df_terminado_bruto = df[df['STATE'] == 'TERMINADO'].copy()
    total_terminado_sistema = len(df_terminado_bruto)

    if total_terminado_sistema == 0:
        raise ValueError("Nenhum voo com estado 'TERMINADO' encontrado no arquivo.")

    df_falsos_voos = df_terminado_bruto[df_terminado_bruto['FINISH_REASON'] != ''].copy()
    total_falsos_voos = len(df_falsos_voos)

    df_terminado = df_terminado_bruto[df_terminado_bruto['FINISH_REASON'] == ''].copy()
    total_terminado = len(df_terminado)

    if total_terminado == 0:
        raise ValueError("Todos os voos terminados possuem motivo de término. Nenhum voo efetivo para auditoria.")

    # =========================================================================
    # 4. IDENTIFICAÇÃO DO PERÍODO
    # =========================================================================
    meses_pt = {
        1: 'JAN', 2: 'FEV', 3: 'MAR', 4: 'ABR', 5: 'MAI', 6: 'JUN',
        7: 'JUL', 8: 'AGO', 9: 'SET', 10: 'OUT', 11: 'NOV', 12: 'DEZ'
    }
    datas = pd.to_datetime(df_terminado['EOBD'], dayfirst=True, errors='coerce')
    meses_unicos = sorted(datas.dt.month.dropna().unique().astype(int))
    prefixo_periodo = "_".join([meses_pt[m] for m in meses_unicos]) if meses_unicos else "PERIODO_DESCONHECIDO"

    # =========================================================================
    # 5. GERAÇÃO DE ID DO VOO E CLASSIFICAÇÃO PBCS
    # =========================================================================
    if 'EOBD' in df.columns and 'EOBT' in df.columns:
        data_limpa = df_terminado['EOBD'].str.replace('/', '', regex=False)
        hora_limpa = df_terminado['EOBT'].str.replace(':', '', regex=False)
        df_terminado['ID_VOO'] = df_terminado['INDICATIVE'] + '_' + df_terminado['ADEP'] + '_' + df_terminado['ADES'] + '_' + data_limpa + hora_limpa
    else:
        df_terminado['ID_VOO'] = "ID_DESCONHECIDO"

    cond_p2 = df_terminado['EQUIP'].str.contains('P2', regex=False)
    cond_rsp = df_terminado['ADD_INFO'].str.contains(r'RSP\s*180', regex=True)
    cond_l1 = df_terminado['ADD_INFO'].str.contains('L1', regex=False)
    cond_a1 = df_terminado['ADD_INFO'].str.contains('A1', regex=False)
    
    mask_pbcs = cond_p2 & cond_rsp
    
    df_terminado['CATEGORIA_PBCS'] = 'NAO_CAPACITADO'
    df_terminado.loc[mask_pbcs & cond_l1 & cond_a1, 'CATEGORIA_PBCS'] = 'PBCS RNP4 RNP10'
    df_terminado.loc[mask_pbcs & cond_l1 & ~cond_a1, 'CATEGORIA_PBCS'] = 'PBCS RNP4'
    df_terminado.loc[mask_pbcs & ~cond_l1 & cond_a1, 'CATEGORIA_PBCS'] = 'PBCS RNP10'
    df_terminado['IS_CAPABLE'] = df_terminado['CATEGORIA_PBCS'] != 'NAO_CAPACITADO'

    # Teste de Integridade
    contagem_cat = df_terminado['CATEGORIA_PBCS'].value_counts()
    voos_ambos = contagem_cat.get('PBCS RNP4 RNP10', 0)
    voos_rnp4 = contagem_cat.get('PBCS RNP4', 0)
    voos_rnp10 = contagem_cat.get('PBCS RNP10', 0)
    voos_nao_cap = contagem_cat.get('NAO_CAPACITADO', 0)
    
    soma_teste = voos_ambos + voos_rnp4 + voos_rnp10 + voos_nao_cap
    if soma_teste != total_terminado:
        raise ValueError(f"Erro de integridade: Soma de capacidades ({soma_teste}) difere do total de voos reais ({total_terminado}).")

    total_capacitados = df_terminado['IS_CAPABLE'].sum()
    porcentagem_voos = (total_capacitados / total_terminado) * 100 if total_terminado > 0 else 0

    df_homologados = df_terminado[df_terminado['IS_CAPABLE']].copy()
    colunas_validas = [col for col in cabecalhos_limpos if col in df_homologados.columns] + ['CATEGORIA_PBCS']
    df_homologados = df_homologados[colunas_validas]

    # =========================================================================
    # 6. ANÁLISE DE FROTA INTEGRADA
    # =========================================================================
    df_terminado['REG_EXTRAIDO'] = df_terminado['ADD_INFO'].str.extract(r'REG/([^\s]+)')
    
    mask_sem_reg = df_terminado['REG_EXTRAIDO'].isna()
    df_sem_reg = df_terminado[mask_sem_reg].copy()
    qtd_sem_reg = len(df_sem_reg)
    sem_reg_cap = len(df_sem_reg[df_sem_reg['CATEGORIA_PBCS'] != 'NAO_CAPACITADO'])
    sem_reg_ncap = len(df_sem_reg[df_sem_reg['CATEGORIA_PBCS'] == 'NAO_CAPACITADO'])

    df_terminado['REGISTRO'] = df_terminado['REG_EXTRAIDO'].fillna(df_terminado['INDICATIVE'])
    df_terminado['REGISTRO'] = df_terminado['REGISTRO'].str.replace(r'[^A-Z0-9]', '', regex=True)

    frota_agrupada = df_terminado.groupby('REGISTRO')['IS_CAPABLE'].any()
    total_frota = len(frota_agrupada)
    frota_capacitada = frota_agrupada.sum()
    pct_frota_cap = (frota_capacitada / total_frota) * 100 if total_frota > 0 else 0

    # =========================================================================
    # 7. ANÁLISE DE DESEMPENHO E RANKING
    # =========================================================================
    voos_cia = df_terminado.groupby('AIRLINE').agg(TOTAL_VOOS=('ID_VOO', 'count'), VOOS_PBCS=('IS_CAPABLE', 'sum'))
    voos_cia['PCT_VOOS'] = (voos_cia['VOOS_PBCS'] / voos_cia['TOTAL_VOOS']) * 100

    frota_cia_reg = df_terminado.groupby(['AIRLINE', 'REGISTRO'])['IS_CAPABLE'].any().reset_index()
    frota_cia = frota_cia_reg.groupby('AIRLINE').agg(TOTAL_FROTA=('REGISTRO', 'nunique'), FROTA_PBCS=('IS_CAPABLE', 'sum'))
    frota_cia['PCT_FROTA'] = (frota_cia['FROTA_PBCS'] / frota_cia['TOTAL_FROTA']) * 100

    # Reseta o index para que 'AIRLINE' vire uma coluna normal para ser plotada no Streamlit
    relatorio_cia = voos_cia.join(frota_cia).sort_values('TOTAL_VOOS', ascending=False).reset_index()

    df_nao_capacitados = df_terminado[~df_terminado['IS_CAPABLE']].copy()
    total_nao_capacitados_global = len(df_nao_capacitados)

    if total_nao_capacitados_global > 0:
        ofensores = df_nao_capacitados.groupby('AIRLINE').size().reset_index(name='VOOS_FALHOS')
        ofensores['CONTRIBUICAO_PCT'] = (ofensores['VOOS_FALHOS'] / total_nao_capacitados_global) * 100
        ofensores['IMPACTO_ABSOLUTO_PCT'] = (ofensores['VOOS_FALHOS'] / total_terminado) * 100
        ranking_ofensores = ofensores.sort_values('VOOS_FALHOS', ascending=False)
    else:
        ranking_ofensores = pd.DataFrame()

    # =========================================================================
    # 8. AUDITORIA DE FLUTUAÇÃO DE CAPACIDADE
    # =========================================================================
    flutuacao_reg = df_terminado.groupby('REGISTRO')['CATEGORIA_PBCS'].nunique()
    regs_inconsistentes = flutuacao_reg[flutuacao_reg > 1].index.tolist()
    
    df_inconsistentes = df_terminado[df_terminado['REGISTRO'].isin(regs_inconsistentes)].copy()
    qtd_inconsistentes = len(regs_inconsistentes)

    df_export_inconsistentes = pd.DataFrame()
    if qtd_inconsistentes > 0:
        colunas_auditoria = ['REGISTRO', 'AIRLINE', 'ID_VOO', 'CATEGORIA_PBCS', 'EQUIP', 'ADD_INFO']
        df_export_inconsistentes = df_inconsistentes[colunas_auditoria].sort_values(by=['REGISTRO', 'CATEGORIA_PBCS'])

    # =========================================================================
    # 9. EMPACOTAMENTO DOS DADOS PARA A INTERFACE GRÁFICA
    # =========================================================================
    return {
        "periodo": prefixo_periodo,
        "metricas": {
            "total_bruto": total_bruto_arquivo,
            "total_falsos_voos": total_falsos_voos,
            "total_terminado": total_terminado,
            "voos_ambos": voos_ambos,
            "voos_rnp4": voos_rnp4,
            "voos_rnp10": voos_rnp10,
            "voos_nao_cap": voos_nao_cap,
            "total_capacitados": total_capacitados,
            "porcentagem_voos": porcentagem_voos,
            "qtd_sem_reg": qtd_sem_reg,
            "sem_reg_cap": sem_reg_cap,
            "sem_reg_ncap": sem_reg_ncap,
            "total_frota": total_frota,
            "frota_capacitada": frota_capacitada,
            "pct_frota_cap": pct_frota_cap,
            "qtd_inconsistentes": qtd_inconsistentes,
            "falsos_voos_top": df_falsos_voos['FINISH_REASON'].value_counts().head(3).to_dict() if total_falsos_voos > 0 else {}
        },
        "dataframes": {
            "voos_capacitados": df_homologados,
            "desempenho_cias": relatorio_cia,
            "ranking_ofensores": ranking_ofensores,
            "inconsistentes": df_export_inconsistentes
        }
    }