import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, date
from dotenv import load_dotenv
from supabase import create_client, Client

# 1. Carregar variáveis de ambiente
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# 2. Conectar ao Supabase
@st.cache_resource
def init_supabase() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = init_supabase()

st.set_page_config(page_title="Finanças Pessoais", page_icon="💶", layout="wide", initial_sidebar_state="collapsed")

# Função auxiliar para formatar moeda em Euro (€)
def fmt_euro(valor: float) -> str:
    return f"€ {valor:,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")

# Função para calcular os limites do ciclo salarial com base no dia do provento
def obter_intervalo_ciclo_salarial(dt_referencia: date, dia_provento: int):
    ano = dt_referencia.year
    mes = dt_referencia.month
    
    if dt_referencia.day >= dia_provento:
        # Estamos no ciclo que começou este mês
        dt_inicio = date(ano, mes, dia_provento)
        # Próximo mês
        if mes == 12:
            dt_fim = date(ano + 1, 1, dia_provento) - timedelta(days=1)
        else:
            dt_fim = date(ano, mes + 1, dia_provento) - timedelta(days=1)
    else:
        # Estamos no ciclo que começou no mês anterior
        if mes == 1:
            dt_inicio = date(ano - 1, 12, dia_provento)
        else:
            dt_inicio = date(ano, mes - 1, dia_provento)
        dt_fim = date(ano, mes, dia_provento) - timedelta(days=1)
        
    return dt_inicio, dt_fim

# Controle de navegação das páginas
if "pagina_atual" not in st.session_state:
    st.session_state.pagina_atual = "🏠 Início"

# 3. Funções de Busca com Paginação
@st.cache_data(ttl=60)
def carregar_tipos():
    response = supabase.table("tipos").select("id, nome").execute()
    return pd.DataFrame(response.data)

@st.cache_data(ttl=60)
def carregar_naturezas():
    response = supabase.table("naturezas").select("id, nome").order("nome").execute()
    return pd.DataFrame(response.data)

def carregar_transacoes():
    todas_transacoes = []
    tamanho_pagina = 1000
    inicio = 0
    
    while True:
        response = (
            supabase.table("transacoes")
            .select("id, data_transacao, valor, origem, descricao, tipo_id, natureza_id, tipos(nome), naturezas(nome)")
            .order("data_transacao", desc=True)
            .range(inicio, inicio + tamanho_pagina - 1)
            .execute()
        )
        dados = response.data
        if not dados:
            break
        todas_transacoes.extend(dados)
        if len(dados) < tamanho_pagina:
            break
        inicio += tamanho_pagina
    
    if not todas_transacoes:
        return pd.DataFrame()
    
    df = pd.DataFrame(todas_transacoes)
    df['tipo'] = df['tipos'].apply(lambda x: x['nome'] if isinstance(x, dict) else '')
    df['natureza'] = df['naturezas'].apply(lambda x: x['nome'] if isinstance(x, dict) else '')
    df['data_transacao'] = pd.to_datetime(df['data_transacao'])
    df['valor'] = df['valor'].astype(float)
    df['origem'] = df['origem'].fillna('Não Especificado')
    return df.drop(columns=['tipos', 'naturezas'])

def carregar_orcametos(ano_mes):
    response = supabase.table("orcametos").select("id, natureza_id, valor_limite, naturezas(nome)").eq("ano_mes", ano_mes).execute()
    if not response.data:
        return pd.DataFrame()
    df = pd.DataFrame(response.data)
    df['natureza'] = df['naturezas'].apply(lambda x: x['nome'] if isinstance(x, dict) else '')
    df['valor_limite'] = df['valor_limite'].astype(float)
    return df.drop(columns=['naturezas'])

def carregar_recorrentes():
    response = supabase.table("recorrentes").select(
        "id, descricao, valor, dia_vencimento, origem, tipo_id, natureza_id, tipos(nome), naturezas(nome), ativo"
    ).eq("ativo", True).execute()
    if not response.data:
        return pd.DataFrame()
    df = pd.DataFrame(response.data)
    df['tipo'] = df['tipos'].apply(lambda x: x['nome'] if isinstance(x, dict) else '')
    df['natureza'] = df['naturezas'].apply(lambda x: x['nome'] if isinstance(x, dict) else '')
    df['valor'] = df['valor'].astype(float)
    return df.drop(columns=['tipos', 'naturezas'])

def recarregar_dados():
    st.cache_data.clear()

df_tipos = carregar_tipos()
df_naturezas = carregar_naturezas()
dict_tipos = dict(zip(df_tipos['nome'], df_tipos['id']))
dict_naturezas = dict(zip(df_naturezas['nome'], df_naturezas['id']))

# Lista das opções do menu
OPCOES_MENU = [
    "🏠 Início",
    "⚡ Lançamento Rápido",
    "📊 Dashboard",
    "➕ Novo Lançamento",
    "✏️ Editar/Eliminar",
    "🎯 Metas & Orçamentos",
    "🔄 Lançamentos Fixos",
    "🏷️ Categorias",
    "📁 Importar/Exportar"
]

st.session_state.pagina_atual = st.selectbox(
    "Navegação:",
    OPCOES_MENU,
    index=OPCOES_MENU.index(st.session_state.pagina_atual) if st.session_state.pagina_atual in OPCOES_MENU else 0
)

st.markdown("---")

# ---------------------------------------------------------
# PÁGINA: 🏠 INÍCIO (HOMEPAGE)
# ---------------------------------------------------------
if st.session_state.pagina_atual == "🏠 Início":
    st.title("💶 Controle Financeiro")
    
    df_transacoes = carregar_transacoes()
    
    # Configuração do dia do provento na Home
    dia_provento = st.number_input("📅 Dia habitual do Salário/Provento:", min_value=1, max_value=28, value=24, step=1)
    
    if not df_transacoes.empty:
        hoje = datetime.now().date()
        
        # 1. Saldo Acumulado Histórico (Tudo desde o início)
        tot_rec_total = df_transacoes[df_transacoes['tipo'] == 'Receita']['valor'].sum()
        tot_desp_total = df_transacoes[df_transacoes['tipo'] == 'Despesa']['valor'].sum()
        saldo_acumulado = tot_rec_total - tot_desp_total
        
        # 2. Ciclo Salarial Vigente
        dt_inicio_ciclo, dt_fim_ciclo = obter_intervalo_ciclo_salarial(hoje, dia_provento)
        
        mask_ciclo = (df_transacoes['data_transacao'].dt.date >= dt_inicio_ciclo) & (df_transacoes['data_transacao'].dt.date <= dt_fim_ciclo)
        df_ciclo = df_transacoes[mask_ciclo]
        
        tot_rec_ciclo = df_ciclo[df_ciclo['tipo'] == 'Receita']['valor'].sum()
        tot_desp_ciclo = df_ciclo[df_ciclo['tipo'] == 'Despesa']['valor'].sum()
        saldo_ciclo = tot_rec_ciclo - tot_desp_ciclo
        
        # Exibição dos KPIs
        st.markdown(f"### 🏦 Saldo Geral da Conta: **{fmt_euro(saldo_acumulado)}**")
        
        st.caption(f"📊 **Resumo do Ciclo Salarial Atual** ({dt_inicio_ciclo.strftime('%d/%m/%Y')} até {dt_fim_ciclo.strftime('%d/%m/%Y')}):")
        
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("💰 Saldo Bancário Total", fmt_euro(saldo_acumulado))
        kpi2.metric("🟢 Receitas do Ciclo", fmt_euro(tot_rec_ciclo))
        kpi3.metric("🔴 Despesas do Ciclo", fmt_euro(tot_desp_ciclo))
        kpi4.metric("💳 Saldo do Ciclo", fmt_euro(saldo_ciclo))
    
    st.markdown("---")
    st.markdown("### 🚀 Acesso Rápido")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("⚡ **Lançamento Rápido**\n\nRegistrar gasto pelo celular", use_container_width=True):
            st.session_state.pagina_atual = "⚡ Lançamento Rápido"
            st.rerun()
            
        if st.button("📊 **Dashboard & Gráficos**\n\nVisualizar saldo e análises", use_container_width=True):
            st.session_state.pagina_atual = "📊 Dashboard"
            st.rerun()

        if st.button("🎯 **Metas & Orçamentos**\n\nAcompanhar limites do mês", use_container_width=True):
            st.session_state.pagina_atual = "🎯 Metas & Orçamentos"
            st.rerun()

        if st.button("🏷️ **Gerenciar Categorias**\n\nCriar novas categorias", use_container_width=True):
            st.session_state.pagina_atual = "🏷️ Categorias"
            st.rerun()

    with col2:
        if st.button("➕ **Lançamento Completo**\n\nCom formulário detalhado", use_container_width=True):
            st.session_state.pagina_atual = "➕ Novo Lançamento"
            st.rerun()

        if st.button("✏️ **Editar / Eliminar**\n\nCorrigir lançamentos", use_container_width=True):
            st.session_state.pagina_atual = "✏️ Editar/Eliminar"
            st.rerun()

        if st.button("🔄 **Gastos/Receitas Fixas**\n\nContas recorrentes mensais", use_container_width=True):
            st.session_state.pagina_atual = "🔄 Lançamentos Fixos"
            st.rerun()

        if st.button("📁 **Importar / Exportar**\n\nSubir Excel ou gerar backup", use_container_width=True):
            st.session_state.pagina_atual = "📁 Importar/Exportar"
            st.rerun()

# ---------------------------------------------------------
# PÁGINA: ⚡ LANÇAMENTO RÁPIDO
# ---------------------------------------------------------
elif st.session_state.pagina_atual == "⚡ Lançamento Rápido":
    st.subheader("⚡ Registro Rápido")
    st.caption("Ideal para adicionar lançamentos direto do telemóvel.")
    
    with st.form("form_rapido_mobile", clear_on_submit=True):
        tipo_r = st.radio("Tipo", ["Despesa", "Receita"], horizontal=True)
        valor_r = st.number_input("Valor (€)", min_value=0.01, step=1.0, format="%.2f")
        cat_r = st.selectbox("Categoria / Natureza", list(dict_naturezas.keys()), key="cat_r_m")
        origem_r = st.text_input("Local / Estabelecimento", placeholder="Ex: Café, Pingo Doce...")
        data_r = st.date_input("Data", value=datetime.now().date(), format="DD/MM/YYYY")
        desc_r = st.text_input("Descrição (Opcional)")
        
        btn_rapido = st.form_submit_button("🚀 Salvar Lançamento", use_container_width=True)
        
        if btn_rapido:
            payload = {
                "data_transacao": str(data_r),
                "tipo_id": dict_tipos[tipo_r],
                "natureza_id": dict_naturezas[cat_r],
                "origem": origem_r if origem_r.strip() else "Não Especificado",
                "descricao": desc_r,
                "valor": float(valor_r)
            }
            supabase.table("transacoes").insert(payload).execute()
            st.success(f"✅ {tipo_r} de {fmt_euro(valor_r)} cadastrada com sucesso!")
            recarregar_dados()

# ---------------------------------------------------------
# PÁGINA: 📊 DASHBOARD
# ---------------------------------------------------------
elif st.session_state.pagina_atual == "📊 Dashboard":
    df_transacoes = carregar_transacoes()
    
    if df_transacoes.empty:
        st.info("Nenhuma transação encontrada no banco de dados.")
    else:
        st.subheader("🔍 Filtros de Análise")
        c_f1, c_f2, c_f3 = st.columns([1, 1, 1])
        
        with c_f1:
            visao_temporal = st.selectbox("Período:", ["Ciclo Salarial Atual", "Mensal Civil", "Ano Atual (YTD)", "Últimos 12 Meses (L12M)", "Todo o Histórico"])
        
        hoje = datetime.now().date()
        df_filtrado = df_transacoes.copy()
        
        if visao_temporal == "Ciclo Salarial Atual":
            dia_p = st.number_input("Dia do Salário:", min_value=1, max_value=28, value=24, step=1, key="dash_dia_p")
            dt_i, dt_f = obter_intervalo_ciclo_salarial(hoje, dia_p)
            df_filtrado = df_filtrado[(df_filtrado['data_transacao'].dt.date >= dt_i) & (df_filtrado['data_transacao'].dt.date <= dt_f)]
            st.caption(f"Exibindo dados do ciclo: **{dt_i.strftime('%d/%m/%Y')}** até **{dt_f.strftime('%d/%m/%Y')}**")
        elif visao_temporal == "Mensal Civil":
            df_transacoes['ano_mes'] = df_transacoes['data_transacao'].dt.strftime('%Y-%m')
            meses_disponiveis = sorted(df_transacoes['ano_mes'].unique(), reverse=True)
            mes_selecionado = st.selectbox("Selecione o Mês:", meses_disponiveis)
            df_filtrado = df_filtrado[df_transacoes['ano_mes'] == mes_selecionado]
        elif visao_temporal == "Ano Atual (YTD)":
            df_filtrado = df_filtrado[df_filtrado['data_transacao'].dt.year == hoje.year]
        elif visao_temporal == "Últimos 12 Meses (L12M)":
            df_filtrado = df_filtrado[df_filtrado['data_transacao'].dt.date >= (hoje - timedelta(days=365))]

        with c_f2:
            naturezas_sel = st.multiselect("Natureza / Categoria:", sorted(df_transacoes['natureza'].unique()), default=[])
            if naturezas_sel:
                df_filtrado = df_filtrado[df_filtrado['natureza'].isin(naturezas_sel)]

        with c_f3:
            origens_sel = st.multiselect("Origem / Estabelecimento:", sorted(df_transacoes['origem'].unique()), default=[])
            if origens_sel:
                df_filtrado = df_filtrado[df_filtrado['origem'].isin(origens_sel)]

        st.markdown("---")

        total_receita_hist = df_transacoes[df_transacoes['tipo'] == 'Receita']['valor'].sum()
        total_despesa_hist = df_transacoes[df_transacoes['tipo'] == 'Despesa']['valor'].sum()
        saldo_total_banco = total_receita_hist - total_despesa_hist

        total_receita = df_filtrado[df_filtrado['tipo'] == 'Receita']['valor'].sum()
        total_despesa = df_filtrado[df_filtrado['tipo'] == 'Despesa']['valor'].sum()
        saldo_periodo = total_receita - total_despesa
        
        col_kpi0, col_kpi1, col_kpi2, col_kpi3 = st.columns(4)
        col_kpi0.metric("💰 Saldo Bancário Real", fmt_euro(saldo_total_banco))
        col_kpi1.metric("🟢 Receitas Período", fmt_euro(total_receita))
        col_kpi2.metric("🔴 Despesas Período", fmt_euro(total_despesa))
        col_kpi3.metric("💳 Saldo Período", fmt_euro(saldo_periodo))
        
        st.markdown("---")

        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            st.subheader("🥧 Despesas por Categoria")
            df_despesas = df_filtrado[df_filtrado['tipo'] == 'Despesa']
            if df_despesas.empty:
                st.info("Sem despesas no período selecionado.")
            else:
                df_cat = df_despesas.groupby('natureza')['valor'].sum().reset_index()
                fig_pie = px.pie(df_cat, values='valor', names='natureza', hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
                fig_pie.update_layout(margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig_pie, use_container_width=True)
                
        with col_graf2:
            st.subheader("📈 Evolução Mensal")
            df_evol = df_filtrado.copy()
            df_evol['ano_mes'] = df_evol['data_transacao'].dt.strftime('%Y-%m')
            df_grouped = df_evol.groupby(['ano_mes', 'tipo'])['valor'].sum().reset_index()
            if not df_grouped.empty:
                fig_bar = px.bar(df_grouped, x='ano_mes', y='valor', color='tipo', barmode='group', color_discrete_map={'Receita': '#2ecc71', 'Despesa': '#e74c3c'})
                fig_bar.update_layout(yaxis_title="Valor (€)", margin=dict(l=10, r=10, t=30, b=10))
                st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("---")

        st.subheader("📋 Histórico de Lançamentos Filtrados")
        df_exibicao = df_filtrado[['id', 'data_transacao', 'tipo', 'natureza', 'origem', 'valor', 'descricao']].copy()
        df_exibicao['data_transacao'] = df_exibicao['data_transacao'].dt.strftime('%d/%m/%Y')
        df_exibicao['valor'] = df_exibicao['valor'].apply(fmt_euro)
        df_exibicao.columns = ['ID', 'Data', 'Tipo', 'Natureza', 'Origem/Local', 'Valor (€)', 'Descrição']
        st.dataframe(df_exibicao, use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# PÁGINA: ➕ NOVO LANÇAMENTO
# ---------------------------------------------------------
elif st.session_state.pagina_atual == "➕ Novo Lançamento":
    st.subheader("➕ Novo Lançamento Completo")
    with st.form("form_transacao", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            data = st.date_input("Data", format="DD/MM/YYYY")
            tipo_sel = st.selectbox("Tipo", list(dict_tipos.keys()))
            valor = st.number_input("Valor (€)", min_value=0.01, step=0.50, format="%.2f")
        with c2:
            nat_sel = st.selectbox("Natureza / Categoria", list(dict_naturezas.keys()))
            origem = st.text_input("Origem / Estabelecimento", placeholder="Ex: Supermercado")
        descricao = st.text_area("Descrição (opcional)")
        
        if st.form_submit_button("Salvar Transação", use_container_width=True):
            res = supabase.table("transacoes").insert({
                "data_transacao": str(data), "tipo_id": dict_tipos[tipo_sel],
                "natureza_id": dict_naturezas[nat_sel], "origem": origem,
                "descricao": descricao, "valor": float(valor)
            }).execute()
            if res.data:
                st.success("Transação salva com sucesso!")
                recarregar_dados()

# ---------------------------------------------------------
# PÁGINA: ✏️ EDITAR/ELIMINAR
# ---------------------------------------------------------
elif st.session_state.pagina_atual == "✏️ Editar/Eliminar":
    st.subheader("✏️ Editar ou Eliminar Lançamento")
    df_gest = carregar_transacoes()
    if not df_gest.empty:
        df_gest['label'] = df_gest.apply(lambda r: f"ID {r['id']} | {r['data_transacao'].strftime('%d/%m/%Y')} | {r['tipo']} | {fmt_euro(r['valor'])} | {r['origem']}", axis=1)
        item_sel = st.selectbox("Selecione o lançamento:", df_gest['label'].tolist())
        reg = df_gest[df_gest['label'] == item_sel].iloc[0]
        
        with st.form("form_edicao"):
            c1, c2 = st.columns(2)
            with c1:
                e_data = st.date_input("Data", value=reg['data_transacao'], format="DD/MM/YYYY")
                e_tipo = st.selectbox("Tipo", list(dict_tipos.keys()), index=list(dict_tipos.keys()).index(reg['tipo']))
                e_valor = st.number_input("Valor (€)", value=float(reg['valor']), min_value=0.01, format="%.2f")
            with c2:
                e_nat = st.selectbox("Natureza", list(dict_naturezas.keys()), index=list(dict_naturezas.keys()).index(reg['natureza']))
                e_origem = st.text_input("Origem", value=reg['origem'])
            e_desc = st.text_area("Descrição", value=reg['descricao'] if reg['descricao'] else "")
            
            b_at, b_el = st.columns(2)
            if b_at.form_submit_button("💾 Salvar Alterações", use_container_width=True):
                supabase.table("transacoes").update({
                    "data_transacao": str(e_data), "tipo_id": dict_tipos[e_tipo],
                    "natureza_id": dict_naturezas[e_nat], "origem": e_origem,
                    "descricao": e_desc, "valor": float(e_valor)
                }).eq("id", int(reg['id'])).execute()
                recarregar_dados()
                st.rerun()
            if b_el.form_submit_button("🗑️ Eliminar Lançamento", use_container_width=True):
                supabase.table("transacoes").delete().eq("id", int(reg['id'])).execute()
                recarregar_dados()
                st.rerun()

# ---------------------------------------------------------
# PÁGINA: 🎯 METAS & ORÇAMENTOS
# ---------------------------------------------------------
elif st.session_state.pagina_atual == "🎯 Metas & Orçamentos":
    st.subheader("🎯 Definir Meta / Teto de Gastos por Categoria")
    col_m1, col_m2 = st.columns(2)
    
    with col_m1:
        ano_mes_meta = st.text_input("Mês/Ano do Orçamento (YYYY-MM)", value=datetime.now().strftime('%Y-%m'))
        cat_meta = st.selectbox("Categoria / Natureza", list(dict_naturezas.keys()), key="meta_cat")
        limite_meta = st.number_input("Limite de Gasto (€)", min_value=10.0, step=50.0, format="%.2f")
        
        c_btn1, c_btn2 = st.columns(2)
        if c_btn1.button("💾 Salvar Meta", use_container_width=True):
            data_meta = {
                "natureza_id": dict_naturezas[cat_meta],
                "ano_mes": ano_mes_meta,
                "valor_limite": float(limite_meta)
            }
            supabase.table("orcametos").upsert(data_meta, on_conflict="natureza_id, ano_mes").execute()
            st.success(f"Meta para '{cat_meta}' no mês {ano_mes_meta} salva!")
            recarregar_dados()
            st.rerun()

        if c_btn2.button("🗑️ Eliminar Meta", use_container_width=True):
            supabase.table("orcametos").delete().eq("natureza_id", dict_naturezas[cat_meta]).eq("ano_mes", ano_mes_meta).execute()
            st.success(f"Meta removida com sucesso!")
            recarregar_dados()
            st.rerun()
            
    with col_m2:
        st.write(f"**Metas Cadastradas para {ano_mes_meta}:**")
        df_m_exist = carregar_orcametos(ano_mes_meta)
        if not df_m_exist.empty:
            df_m_exist_exib = df_m_exist[['natureza', 'valor_limite']].copy()
            df_m_exist_exib['valor_limite'] = df_m_exist_exib['valor_limite'].apply(fmt_euro)
            df_m_exist_exib.columns = ['Categoria', 'Teto Máximo (€)']
            st.dataframe(df_m_exist_exib, use_container_width=True, hide_index=True)
        else:
            st.info(f"Nenhuma meta cadastrada para {ano_mes_meta}.")

# ---------------------------------------------------------
# PÁGINA: 🔄 LANÇAMENTOS FIXOS
# ---------------------------------------------------------
elif st.session_state.pagina_atual == "🔄 Lançamentos Fixos":
    st.subheader("🔄 Cadastro de Despesas e Receitas Fixas")
    col_r1, col_r2 = st.columns(2)
    with col_r1:
        st.markdown("**Cadastrar Novo Gasto/Receita Fixo:**")
        with st.form("form_rec"):
            r_desc = st.text_input("Descrição (Ex: Aluguel, Internet)")
            r_tipo = st.selectbox("Tipo", list(dict_tipos.keys()), key="rec_tipo")
            r_nat = st.selectbox("Natureza", list(dict_naturezas.keys()), key="rec_nat")
            r_val = st.number_input("Valor Fixo (€)", min_value=0.01, step=10.0, format="%.2f")
            r_dia = st.number_input("Dia do Vencimento", min_value=1, max_value=31, value=5)
            r_origem = st.text_input("Origem/Local", placeholder="Ex: Imobiliária X")
            
            if st.form_submit_button("Cadastrar Recorrente", use_container_width=True):
                supabase.table("recorrentes").insert({
                    "descricao": r_desc, "tipo_id": dict_tipos[r_tipo],
                    "natureza_id": dict_naturezas[r_nat], "valor": float(r_val),
                    "dia_vencimento": int(r_dia), "origem": r_origem
                }).execute()
                st.success("Lançamento fixo cadastrado!")
                recarregar_dados()
                
    with col_r2:
        st.markdown("**Lançamentos Fixos Ativos:**")
        df_rec_ativos = carregar_recorrentes()
        if not df_rec_ativos.empty:
            df_rec_exib = df_rec_ativos[['descricao', 'tipo', 'natureza', 'valor', 'dia_vencimento']].copy()
            df_rec_exib['valor'] = df_rec_exib['valor'].apply(fmt_euro)
            df_rec_exib.columns = ['Descrição', 'Tipo', 'Categoria', 'Valor (€)', 'Dia Venc.']
            st.dataframe(df_rec_exib, use_container_width=True, hide_index=True)
            
            st.markdown("---")
            st.markdown("**⚡ Processar Fixos no Mês Atual:**")
            mes_proc = st.text_input("Mês para Gerar Lançamentos (YYYY-MM)", value=datetime.now().strftime('%Y-%m'))
            
            if st.button("🚀 Gerar Lançamentos no Histórico", use_container_width=True):
                novos_inseridos = 0
                for _, row_r in df_rec_ativos.iterrows():
                    dia_str = str(row_r['dia_vencimento']).zfill(2)
                    data_lanc = f"{mes_proc}-{dia_str}"
                    
                    supabase.table("transacoes").insert({
                        "data_transacao": data_lanc,
                        "tipo_id": dict_tipos[row_r['tipo']],
                        "natureza_id": dict_naturezas[row_r['natureza']],
                        "origem": row_r['origem'],
                        "descricao": f"[FIXO] {row_r['descricao']}",
                        "valor": float(row_r['valor'])
                    }).execute()
                    novos_inseridos += 1
                
                st.success(f"Sucesso! {novos_inseridos} lançamentos fixos foram inseridos em {mes_proc}.")
                recarregar_dados()

# ---------------------------------------------------------
# PÁGINA: 🏷️ CATEGORIAS
# ---------------------------------------------------------
elif st.session_state.pagina_atual == "🏷️ Categorias":
    st.subheader("🏷️ Gerenciar Categorias (Naturezas)")
    c_cat1, c_cat2 = st.columns(2)
    with c_cat1:
        st.markdown("**Adicionar Nova Categoria:**")
        nova_cat_nome = st.text_input("Nome da Categoria (Ex: Pets, Assinaturas)")
        if st.button("Adicionar Categoria", use_container_width=True):
            if nova_cat_nome.strip():
                res = supabase.table("naturezas").insert({"nome": nova_cat_nome.strip()}).execute()
                if res.data:
                    st.success(f"Categoria '{nova_cat_nome}' adicionada!")
                    recarregar_dados()
                    st.rerun()
            else:
                st.warning("Digite um nome válido.")
                
    with c_cat2:
        st.markdown("**Categorias Existentes:**")
        st.dataframe(df_naturezas[['id', 'nome']].rename(columns={'id': 'ID', 'nome': 'Nome'}), use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# PÁGINA: 📁 IMPORTAR/EXPORTAR
# ---------------------------------------------------------
elif st.session_state.pagina_atual == "📁 Importar/Exportar":
    st.subheader("📁 Importação e Exportação de Histórico")
    col_imp, col_exp = st.columns(2)
    
    with col_imp:
        st.markdown("### 📥 Importar Lançamentos em Lote")
        st.markdown("""
        Suba seu arquivo Excel (`.xlsx` ou `.xls`) ou CSV contendo as colunas:
        * `data_transacao`
        * `tipo` *(Receita ou Despesa)*
        * `natureza`
        * `origem`
        * `descricao`
        * `valor`
        """)
        
        uploaded_file = st.file_uploader("Selecione o ficheiro Excel ou CSV", type=["xlsx", "csv"])
        
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df_up = pd.read_csv(uploaded_file)
                else:
                    df_up = pd.read_excel(uploaded_file)
                
                df_up.columns = df_up.columns.astype(str).str.strip()
                
                st.write("🔍 **Pré-visualização dos dados:**")
                st.dataframe(df_up.head(5), use_container_width=True)
                
                if st.button("🚀 Processar e Importar para o Supabase", use_container_width=True):
                    colunas_req = {'data_transacao', 'tipo', 'natureza', 'origem', 'valor'}
                    if not colunas_req.issubset(set(df_up.columns)):
                        st.error(f"Faltam colunas obrigatórias no arquivo! As colunas necessárias são: {list(colunas_req)}")
                    else:
                        progress_bar = st.progress(0)
                        total_rows = len(df_up)
                        inseridos = 0
                        dict_nat_local = dict_naturezas.copy()
                        
                        for idx, row in df_up.iterrows():
                            cat_nome = str(row['natureza']).strip()
                            if cat_nome not in dict_nat_local:
                                res_cat = supabase.table("naturezas").insert({"nome": cat_nome}).execute()
                                if res_cat.data:
                                    dict_nat_local[cat_nome] = res_cat.data[0]['id']
                            
                            data_val = pd.to_datetime(row['data_transacao']).strftime('%Y-%m-%d')
                            
                            payload = {
                                "data_transacao": data_val,
                                "tipo_id": dict_tipos.get(str(row['tipo']).strip(), 2),
                                "natureza_id": dict_nat_local.get(cat_nome),
                                "origem": str(row['origem']) if pd.notna(row['origem']) else "Não Especificado",
                                "descricao": str(row['descricao']) if 'descricao' in row and pd.notna(row['descricao']) else "",
                                "valor": float(row['valor'])
                            }
                            
                            supabase.table("transacoes").insert(payload).execute()
                            inseridos += 1
                            progress_bar.progress((idx + 1) / total_rows)
                        
                        st.success(f"🎉 Importação concluída! {inseridos} registros inseridos com sucesso.")
                        recarregar_dados()
            except Exception as e:
                st.error(f"Erro ao processar o arquivo: {e}")

    with col_exp:
        st.markdown("### 📤 Exportar Histórico Completo")
        st.markdown("Faça o download do seu banco de dados completo em formato CSV.")
        
        df_exp = carregar_transacoes()
        if not df_exp.empty:
            df_exp_clean = df_exp[['id', 'data_transacao', 'tipo', 'natureza', 'origem', 'valor', 'descricao']].copy()
            df_exp_clean['data_transacao'] = df_exp_clean['data_transacao'].dt.strftime('%Y-%m-%d')
            
            csv_data = df_exp_clean.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Baixar como CSV",
                data=csv_data,
                file_name=f"financas_export_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
            
            st.info(f"Total de {len(df_exp_clean)} lançamentos prontos para exportação.")
        else:
            st.warning("Nenhum dado disponível para exportação.")