import os
import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
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

# 3. Funções de Busca com Paginação para Superar Limite de 1000 Linhas
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

st.title("💶 Controle Financeiro")

df_tipos = carregar_tipos()
df_naturezas = carregar_naturezas()
dict_tipos = dict(zip(df_tipos['nome'], df_tipos['id']))
dict_naturezas = dict(zip(df_naturezas['nome'], df_naturezas['id']))

# Abas otimizadas para mobile (Lançamento Rápido em primeiro lugar)
tab_rapido, tab_dash, tab_novo, tab_gestao, tab_metas, tab_recorrentes, tab_cats, tab_import = st.tabs([
    "⚡ Lançamento Rápido", "📊 Dashboard", "➕ Completo", "✏️ Editar/Eliminar", 
    "🎯 Metas", "🔄 Fixos", "🏷️ Categorias", "📁 Importar/Exportar"
])

# ---------------------------------------------------------
# ABA 0: LANÇAMENTO RÁPIDO (MOBILE FIRST)
# ---------------------------------------------------------
with tab_rapido:
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
# ABA 1: DASHBOARD
# ---------------------------------------------------------
with tab_dash:
    df_transacoes = carregar_transacoes()
    
    if df_transacoes.empty:
        st.info("Nenhuma transação encontrada no banco de dados.")
    else:
        st.subheader("🔍 Filtros de Análise")
        c_f1, c_f2, c_f3 = st.columns([1, 1, 1])
        
        with c_f1:
            visao_temporal = st.selectbox("Período:", ["Mensal Específico", "Ano Atual (YTD)", "Últimos 12 Meses (L12M)", "Todo o Histórico"])
        
        hoje = datetime.now()
        df_filtrado = df_transacoes.copy()
        mes_selecionado = hoje.strftime('%Y-%m')
        
        if visao_temporal == "Mensal Específico":
            df_transacoes['ano_mes'] = df_transacoes['data_transacao'].dt.strftime('%Y-%m')
            meses_disponiveis = sorted(df_transacoes['ano_mes'].unique(), reverse=True)
            mes_selecionado = st.selectbox("Selecione o Mês:", meses_disponiveis)
            df_filtrado = df_filtrado[df_transacoes['ano_mes'] == mes_selecionado]
        elif visao_temporal == "Ano Atual (YTD)":
            df_filtrado = df_filtrado[df_filtrado['data_transacao'].dt.year == hoje.year]
        elif visao_temporal == "Últimos 12 Meses (L12M)":
            df_filtrado = df_filtrado[df_filtrado['data_transacao'] >= (hoje - timedelta(days=365))]

        with c_f2:
            naturezas_sel = st.multiselect("Natureza / Categoria:", sorted(df_transacoes['natureza'].unique()), default=[])
            if naturezas_sel:
                df_filtrado = df_filtrado[df_filtrado['natureza'].isin(naturezas_sel)]

        with c_f3:
            origens_sel = st.multiselect("Origem / Estabelecimento:", sorted(df_transacoes['origem'].unique()), default=[])
            if origens_sel:
                df_filtrado = df_filtrado[df_filtrado['origem'].isin(origens_sel)]

        st.markdown("---")

        total_receita = df_filtrado[df_filtrado['tipo'] == 'Receita']['valor'].sum()
        total_despesa = df_filtrado[df_filtrado['tipo'] == 'Despesa']['valor'].sum()
        saldo = total_receita - total_despesa
        
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        col_kpi1.metric("🟢 Receitas", fmt_euro(total_receita))
        col_kpi2.metric("🔴 Despesas", fmt_euro(total_despesa))
        col_kpi3.metric("💳 Saldo do Período", fmt_euro(saldo))
        
        st.markdown("---")
        
        if visao_temporal == "Mensal Específico":
            df_orc = carregar_orcametos(mes_selecionado)
            if not df_orc.empty:
                st.subheader(f"🎯 Acompanhamento de Orçamento ({mes_selecionado})")
                df_desp_mes = df_filtrado[df_filtrado['tipo'] == 'Despesa'].groupby('natureza')['valor'].sum().reset_index()
                
                df_meta_comp = pd.merge(df_orc, df_desp_mes, on='natureza', how='left').fillna(0)
                
                cols = st.columns(2)
                for i, row in df_meta_comp.iterrows():
                    gasto = row['valor']
                    limite = row['valor_limite']
                    pct = min(gasto / limite, 1.0) if limite > 0 else 0.0
                    
                    with cols[i % 2]:
                        if gasto > limite:
                            excesso = gasto - limite
                            st.error(f"❌ **{row['natureza']}**: {fmt_euro(gasto)} de {fmt_euro(limite)}")
                            st.progress(1.0)
                            st.caption(f"🚨 **Limite ultrapassado em {fmt_euro(excesso)}!**")
                        else:
                            restante = limite - gasto
                            st.success(f"✅ **{row['natureza']}**: {fmt_euro(gasto)} de {fmt_euro(limite)}")
                            st.progress(pct)
                            st.caption(f"💡 Disponível: **{fmt_euro(restante)}**")
                st.markdown("---")

        col_graf1, col_graf2 = st.columns(2)
        with col_graf1:
            st.subheader("🥧 Despesas por Categoria")
            df_despesas = df_filtrado[df_filtrado['tipo'] == 'Despesa']
            if df_despesas.empty:
                st.info("Sem despesas no período.")
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
# ABA 2: NOVO LANÇAMENTO COMPLETO
# ---------------------------------------------------------
with tab_novo:
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
# ABA 3: EDITAR OU ELIMINAR
# ---------------------------------------------------------
with tab_gestao:
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
# ABA 4: METAS E ORÇAMENTOS
# ---------------------------------------------------------
with tab_metas:
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
# ABA 5: DESPESAS RECORRENTES / FIXAS
# ---------------------------------------------------------
with tab_recorrentes:
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
# ABA 6: GESTÃO DE CATEGORIAS (NATUREZAS)
# ---------------------------------------------------------
with tab_cats:
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
# ABA 7: IMPORTAR E EXPORTAR DADOS
# ---------------------------------------------------------
with tab_import:
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