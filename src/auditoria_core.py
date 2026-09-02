"""
=============================================================================
PROJETO: Painel de Auditoria de Capacidades Datalink (PBCS) - FIR-AO
ARQUIVO: auditoria_core.py (Motor Lógico e Matemático)
=============================================================================
"""
import pandas as pd

def processar_dados(df):
    if df is None or df.empty:
        raise ValueError("O DataFrame recebido está vazio ou é inválido.")

    df.columns = [str(c).strip().replace('"', '').replace("'", "") for c in df.columns]

    colunas_texto = ['EQUIP', 'ADD_INFO', 'INDICATIVE', 'ROUTE', 'ADEP', 'ADES', 'EOBD', 'EOBT', 'STATE', 'AIRLINE', 'FINISH_REASON']
    for col in colunas_texto:
        if col in df.columns:
            df[col] = df[col].fillna('').astype(str).str.strip().str.upper()

    if 'AIRLINE' in df.columns:
        df.loc[df['AIRLINE'] == '', 'AIRLINE'] = 'NAO_INFORMADA'
    
    cias_declaradas = set(df.loc[df['AIRLINE'] != 'NAO_INFORMADA', 'AIRLINE'].unique())
    mask_nao_informada = df['AIRLINE'] == 'NAO_INFORMADA'
    
    if 'INDICATIVE' in df.columns:
        prefixos = df['INDICATIVE'].str[:3]
        mask_match = mask_nao_informada & prefixos.isin(cias_declaradas)
        df.loc[mask_match, 'AIRLINE'] = prefixos[mask_match]
        
    df.loc[df['AIRLINE'] == 'NAO_INFORMADA', 'AIRLINE'] = 'GERAL/MILITAR'

    if 'STATE' not in df.columns:
        raise ValueError("Coluna obrigatória 'STATE' não encontrada nos dados enviados.")
        
    df_terminado_bruto = df[df['STATE'] == 'TERMINADO'].copy()
    
    if 'FINISH_REASON' in df.columns:
        df_terminado = df_terminado_bruto[df_terminado_bruto['FINISH_REASON'] == ''].copy()
    else:
        df_terminado = df_terminado_bruto.copy()
        
    total_terminado = len(df_terminado)

    if total_terminado == 0:
        raise ValueError("Nenhum voo efetivo (TERMINADO sem motivo de cancelamento) para auditoria.")

    if 'EOBD' in df_terminado.columns and 'EOBT' in df_terminado.columns:
        data_limpa = df_terminado['EOBD'].str.replace('/', '', regex=False)
        hora_limpa = df_terminado['EOBT'].str.replace(':', '', regex=False)
        df_terminado['ID_VOO'] = df_terminado['INDICATIVE'] + '_' + df_terminado['ADEP'] + '_' + df_terminado['ADES'] + '_' + data_limpa + hora_limpa
    else:
        df_terminado['ID_VOO'] = df_terminado.index.astype(str)

    # =========================================================================
    # 4. DIVISÃO EQUIP E CRIAÇÃO DAS MÁSCARAS
    # =========================================================================
    df_terminado[['EQUIP_COM', 'EQUIP_SUR']] = df_terminado['EQUIP'].str.split('/', n=1, expand=True).fillna('')

    cond_cpdlc = df_terminado['EQUIP_COM'].str.contains('J5|J7', regex=True)
    cond_adsc  = df_terminado['EQUIP_SUR'].str.contains('D1', regex=False)
    cond_adsb  = df_terminado['EQUIP_SUR'].str.contains('B1|B2', regex=True)
    cond_rcp   = df_terminado['EQUIP_COM'].str.contains('P2', regex=False)
    
    cond_rnp4  = df_terminado['ADD_INFO'].str.contains('L1', regex=False)
    cond_rnp10 = df_terminado['ADD_INFO'].str.contains('A1', regex=False)
    cond_rsp   = df_terminado['ADD_INFO'].str.contains(r'RSP\s*180', regex=True)
    
    # A nível de voo, a negação é direta: não tem RNP4 E não tem RNP10
    cond_nao_rnp = ~(cond_rnp4 | cond_rnp10)

    # SALVANDO CARIMBOS (Estatística de Voos Individuais)
    df_terminado['CAP_CPDLC'] = cond_cpdlc
    df_terminado['CAP_ADSC']  = cond_adsc
    df_terminado['CAP_ADSB']  = cond_adsb
    df_terminado['CAP_RCP']   = cond_rcp
    df_terminado['CAP_RSP']   = cond_rsp
    df_terminado['CAP_RNP4']  = cond_rnp4
    df_terminado['CAP_RNP10'] = cond_rnp10
    df_terminado['CAP_NAO_RNP'] = cond_nao_rnp 
    
    mask_pbcs = cond_rcp & cond_rsp
    df_terminado['CAP_PBCS'] = mask_pbcs & (cond_rnp4 | cond_rnp10)

    df_terminado['CATEGORIA_PBCS'] = 'NAO_CAPACITADO'
    df_terminado.loc[mask_pbcs & cond_rnp4 & cond_rnp10, 'CATEGORIA_PBCS'] = 'PBCS RNP4 RNP10'
    df_terminado.loc[mask_pbcs & cond_rnp4 & ~cond_rnp10, 'CATEGORIA_PBCS'] = 'PBCS RNP4'
    df_terminado.loc[mask_pbcs & ~cond_rnp4 & cond_rnp10, 'CATEGORIA_PBCS'] = 'PBCS RNP10'
    
    df_terminado['IS_CAPABLE'] = df_terminado['CATEGORIA_PBCS'] != 'NAO_CAPACITADO'

    total_capacitados = df_terminado['IS_CAPABLE'].sum()
    porcentagem_voos = (total_capacitados / total_terminado) * 100 if total_terminado > 0 else 0

    # =========================================================================
    # 5. EXTRAÇÃO DE MATRÍCULA E AGRUPAMENTO DE FROTA
    # =========================================================================
    df_terminado['REG_EXTRAIDO'] = df_terminado['ADD_INFO'].str.extract(r'REG/([^\s]+)')
    mask_comercial = df_terminado['INDICATIVE'].str.match(r'^[A-Z]{3}[0-9][A-Z0-9]*$')
    df_terminado['REGISTRO'] = df_terminado['REG_EXTRAIDO']
    mask_sem_reg = df_terminado['REGISTRO'].isna() | (df_terminado['REGISTRO'] == '')
    df_terminado.loc[mask_sem_reg & ~mask_comercial, 'REGISTRO'] = df_terminado.loc[mask_sem_reg & ~mask_comercial, 'INDICATIVE']
    mask_com_registro = df_terminado['REGISTRO'].notna() & (df_terminado['REGISTRO'] != '')
    df_terminado.loc[mask_com_registro, 'REGISTRO'] = df_terminado.loc[mask_com_registro, 'REGISTRO'].astype(str).str.replace(r'[^A-Z0-9]', '', regex=True)

    frota_agrupada = df_terminado.groupby('REGISTRO')['IS_CAPABLE'].any()
    total_frota = len(frota_agrupada)
    frota_capacitada = frota_agrupada.sum()
    pct_frota_cap = (frota_capacitada / total_frota) * 100 if total_frota > 0 else 0

    # --- [CORREÇÃO DA TABELA MESTRA DA FROTA (O PADRÃO OURO)] ---
    # 1. Agrupamos apenas as capacidades positivas, onde se declarou 1 vez no período, já conta.
    df_frota_capacidades = df_terminado.groupby('REGISTRO')[
        ['CAP_RNP10', 'CAP_RNP4', 'CAP_CPDLC', 'CAP_ADSC', 'CAP_ADSB', 'CAP_RCP', 'CAP_RSP', 'CAP_PBCS']
    ].any().reset_index()

    # 2. A aeronave SÓ entra no NÃO RNP da frota se não declarou RNP10 nem RNP4 no período inteiro.
    df_frota_capacidades['CAP_NAO_RNP'] = ~(df_frota_capacidades['CAP_RNP10'] | df_frota_capacidades['CAP_RNP4'])

    # =========================================================================
    # 6. ANÁLISE DE DESEMPENHO E FLUTUAÇÃO
    # =========================================================================
    voos_cia = df_terminado.groupby('AIRLINE').agg(TOTAL_VOOS=('ID_VOO', 'count'), VOOS_PBCS=('IS_CAPABLE', 'sum'))
    voos_cia['PCT_VOOS'] = (voos_cia['VOOS_PBCS'] / voos_cia['TOTAL_VOOS']) * 100

    frota_cia_reg = df_terminado.groupby(['AIRLINE', 'REGISTRO'])['IS_CAPABLE'].any().reset_index()
    frota_cia = frota_cia_reg.groupby('AIRLINE').agg(TOTAL_FROTA=('REGISTRO', 'nunique'), FROTA_PBCS=('IS_CAPABLE', 'sum'))
    frota_cia['PCT_FROTA'] = (frota_cia['FROTA_PBCS'] / frota_cia['TOTAL_FROTA']) * 100

    relatorio_cia = voos_cia.join(frota_cia).sort_values('TOTAL_VOOS', ascending=False).reset_index()

    df_nao_capacitados = df_terminado[~df_terminado['IS_CAPABLE']].copy()
    total_nao_capacitados_global = len(df_nao_capacitados)

    if total_nao_capacitados_global > 0:
        ofensores = df_nao_capacitados.groupby('AIRLINE').size().reset_index(name='VOOS_NAO_CAPACITADOS')
        ofensores['CONTRIBUICAO_PCT'] = (ofensores['VOOS_NAO_CAPACITADOS'] / total_nao_capacitados_global) * 100
        ranking_ofensores = ofensores.sort_values('VOOS_NAO_CAPACITADOS', ascending=False)
    else:
        ranking_ofensores = pd.DataFrame()

    agrup_cap = df_terminado.groupby('REGISTRO')['IS_CAPABLE'].nunique()
    registros_inconsistentes = agrup_cap[agrup_cap > 1].index
    df_inconsistentes = df_terminado[df_terminado['REGISTRO'].isin(registros_inconsistentes)].copy()
    
    if not df_inconsistentes.empty:
        resumo_inconsist = df_inconsistentes.groupby('REGISTRO').agg(
            VOOS_DECLARADOS=('IS_CAPABLE', 'sum'),
            VOOS_NAO_DECLARADOS=('IS_CAPABLE', lambda x: (~x).sum())
        ).reset_index()
        
        cia_map = df_inconsistentes.groupby('REGISTRO')['AIRLINE'].first().reset_index()
        ranking_inconsistentes = pd.merge(resumo_inconsist, cia_map, on='REGISTRO', how='left')
        
        def get_categorias(reg):
            cats = df_inconsistentes[df_inconsistentes['REGISTRO'] == reg]['CATEGORIA_PBCS'].unique()
            return " vs ".join(cats)
            
        ranking_inconsistentes['DISCREPANCIA'] = ranking_inconsistentes['REGISTRO'].apply(get_categorias)
        ranking_inconsistentes = ranking_inconsistentes.sort_values('VOOS_NAO_DECLARADOS', ascending=False)
        ranking_inconsistentes = ranking_inconsistentes[['REGISTRO', 'AIRLINE', 'VOOS_DECLARADOS', 'VOOS_NAO_DECLARADOS', 'DISCREPANCIA']]
    else:
        ranking_inconsistentes = pd.DataFrame()

    df_terminado['DATA_REF'] = pd.to_datetime(df_terminado['EOBD'], errors='coerce', dayfirst=True)
    df_terminado['MES_ANO_SORT'] = df_terminado['DATA_REF'].dt.strftime('%Y-%m').fillna('0000-00')
    
    mensal_list = []
    for mes, group in df_terminado.groupby('MES_ANO_SORT'):
        if mes == '0000-00':
            continue
        mes_str = f"{mes.split('-')[1]}/{mes.split('-')[0]}"
        tot = len(group)
        cap = group['IS_CAPABLE'].sum()
        pct_v = (cap / tot) * 100 if tot > 0 else 0
        
        frota_ag = group.groupby('REGISTRO')['IS_CAPABLE'].any()
        tot_f = len(frota_ag)
        cap_f = frota_ag.sum()
        pct_f = (cap_f / tot_f) * 100 if tot_f > 0 else 0
        
        mensal_list.append({
            'MES_SORT': mes, 'Mês': mes_str, 'Voos Efetivos': tot, 'Voos PBCS': cap, '% Voos PBCS': pct_v,
            'Frota Ativa': tot_f, 'Frota PBCS': cap_f, '% Frota PBCS': pct_f
        })
    
    if mensal_list:
        df_evolucao = pd.DataFrame(mensal_list).sort_values('MES_SORT').drop(columns=['MES_SORT'])
    else:
        df_evolucao = pd.DataFrame()

    return {
        'total_terminado': int(total_terminado),
        'total_capacitados': int(total_capacitados),
        'porcentagem_voos': float(porcentagem_voos),
        'frota_capacitada': int(frota_capacitada),
        'total_frota': int(total_frota),
        'pct_frota_cap': float(pct_frota_cap),
        'relatorio_cia': relatorio_cia,
        'ranking_ofensores': ranking_ofensores,
        'voos_inconsistentes': df_inconsistentes, 
        'ranking_inconsistentes': ranking_inconsistentes, 
        'evolucao_mensal': df_evolucao,
        'df_frota_capacidades': df_frota_capacidades,
        'df_processado': df_terminado
    }