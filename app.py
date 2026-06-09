# -*- coding: utf-8 -*-
import streamlit as st
import os
import tempfile
import logging
import time
import zipfile
import glob

# Importar funções dos módulos dos agentes
from data_ingestion import create_connection, create_tables, ingest_data, DB_FILE
from database_agent import query_database_agent
from output_formatter import format_response

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- REMOVIDO: Limpeza do Banco de Dados na Inicialização ---
# try:
#     if os.path.exists(DB_FILE):
#         os.remove(DB_FILE)
#         logging.info(f"Banco de dados anterior ({DB_FILE}) removido com sucesso na inicialização.")
#     else:
#         logging.info(f"Nenhum banco de dados anterior ({DB_FILE}) encontrado para remover na inicialização.")
# except Exception as e:
#     logging.error(f"Erro ao tentar remover o banco de dados {DB_FILE} na inicialização: {e}")

# --- Configuração da Página Streamlit ---
st.set_page_config(page_title="Chat com Notas Fiscais", page_icon="🧾", layout="wide")
st.title("📊 Chat com Notas Fiscais usando Gemini + SQLite")

# --- Estado da Sessão --- 
def initialize_session_state():
    if "history" not in st.session_state:
        st.session_state.history = []
    if "google_api_key" not in st.session_state:
        st.session_state.google_api_key = None
    # Verificar se o DB existe para definir o estado inicial de ingestão
    db_already_exists = os.path.exists(DB_FILE)
    if "ingestion_complete" not in st.session_state:
        st.session_state.ingestion_complete = db_already_exists 
        if db_already_exists:
            logging.info(f"Banco de dados {DB_FILE} já existe. Assumindo ingestão completa.")
    if "ingestion_in_progress" not in st.session_state:
        st.session_state.ingestion_in_progress = False
    if "processed_file_paths" not in st.session_state:
        st.session_state.processed_file_paths = {"cabecalho": None, "itens": None}
    if "files_ready_for_ingestion" not in st.session_state:
        st.session_state.files_ready_for_ingestion = False
    # Não precisamos mais de db_exists separado, usamos ingestion_complete

initialize_session_state()

# --- Função para limpar arquivos temporários processados ---
def cleanup_processed_files():
    cabecalho_path = st.session_state.processed_file_paths.get("cabecalho")
    itens_path = st.session_state.processed_file_paths.get("itens")
    if cabecalho_path and os.path.exists(cabecalho_path):
        try: os.remove(cabecalho_path); logging.info(f"Arquivo temp {cabecalho_path} removido.")
        except Exception as clean_e: logging.error(f"Erro ao limpar {cabecalho_path}: {clean_e}")
    if itens_path and os.path.exists(itens_path):
        try: os.remove(itens_path); logging.info(f"Arquivo temp {itens_path} removido.")
        except Exception as clean_e: logging.error(f"Erro ao limpar {itens_path}: {clean_e}")
    st.session_state.processed_file_paths = {"cabecalho": None, "itens": None}
    st.session_state.files_ready_for_ingestion = False

# --- Barra Lateral (Sidebar) ---
st.sidebar.header("Configuração")

st.session_state.google_api_key = st.sidebar.text_input(
    "🔑 Google Gemini API Key", 
    type="password", 
    value=st.session_state.google_api_key or "",
    help="Insira sua chave da API do Google Gemini."
)

if not st.session_state.google_api_key:
    st.sidebar.warning("🔑 Por favor, insira sua chave da API do Google Gemini para habilitar o chat.")

st.sidebar.divider()

st.sidebar.header("Upload de Arquivos (CSV ou ZIP)")

uploaded_files = st.sidebar.file_uploader(
    "Envie os 2 arquivos CSV ou 1 arquivo ZIP",
    type=["csv", "zip"],
    accept_multiple_files=True,
    key="file_uploader",
    # Quando arquivos mudam, limpamos os processados e resetamos o estado de prontidão
    on_change=cleanup_processed_files 
)

upload_error = None
cabecalho_found_path = None
itens_found_path = None

# Processar arquivos APENAS se novos arquivos foram enviados E não estão prontos ainda
if uploaded_files and not st.session_state.files_ready_for_ingestion:
    # Limpar arquivos temporários de processamentos anteriores desta sessão
    # cleanup_processed_files() # Já é chamado pelo on_change

    if len(uploaded_files) == 1 and uploaded_files[0].name.lower().endswith(".zip"):
        zip_file = uploaded_files[0]
        st.sidebar.info(f"Processando arquivo ZIP: {zip_file.name}...")
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                    zip_ref.extractall(tmpdir)
                logging.info(f"ZIP extraído para {tmpdir}")
                
                all_files = []
                for root, _, files in os.walk(tmpdir):
                   for file in files:
                       all_files.append(os.path.join(root, file))

                cabecalho_candidates = [f for f in all_files if f.lower().endswith("_nfs_cabecalho.csv")]
                itens_candidates = [f for f in all_files if f.lower().endswith("_nfs_itens.csv")]

                if len(cabecalho_candidates) == 1:
                    cabecalho_found_path = cabecalho_candidates[0]
                elif len(cabecalho_candidates) > 1:
                     upload_error = "Erro: Múltiplos arquivos `*_NFs_Cabecalho.csv` encontrados no ZIP."
                else:
                     upload_error = "Erro: Arquivo `*_NFs_Cabecalho.csv` não encontrado no ZIP."

                if not upload_error:
                    if len(itens_candidates) == 1:
                        itens_found_path = itens_candidates[0]
                    elif len(itens_candidates) > 1:
                         upload_error = "Erro: Múltiplos arquivos `*_NFs_Itens.csv` encontrados no ZIP."
                    else:
                         upload_error = "Erro: Arquivo `*_NFs_Itens.csv` não encontrado no ZIP."

                if cabecalho_found_path and itens_found_path and not upload_error:
                    try:
                        # Usar arquivos temporários nomeados que persistem até serem limpos
                        tmp_cabecalho_perm = tempfile.NamedTemporaryFile(delete=False, suffix="_cabecalho.csv")
                        with open(cabecalho_found_path, 'rb') as src:
                            tmp_cabecalho_perm.write(src.read())
                        st.session_state.processed_file_paths["cabecalho"] = tmp_cabecalho_perm.name
                        tmp_cabecalho_perm.close() # Fechar o handle, mas o arquivo persiste
                        logging.info(f"Arquivo Cabeçalho encontrado no ZIP e salvo em {st.session_state.processed_file_paths['cabecalho']}")
                        
                        tmp_itens_perm = tempfile.NamedTemporaryFile(delete=False, suffix="_itens.csv")
                        with open(itens_found_path, 'rb') as src:
                            tmp_itens_perm.write(src.read())
                        st.session_state.processed_file_paths["itens"] = tmp_itens_perm.name
                        tmp_itens_perm.close()
                        logging.info(f"Arquivo Itens encontrado no ZIP e salvo em {st.session_state.processed_file_paths['itens']}")
                        
                        st.session_state.files_ready_for_ingestion = True
                        st.sidebar.success("Arquivos do ZIP identificados!")
                        # Não usar st.rerun() aqui, deixar o fluxo seguir
                    except Exception as copy_e:
                        upload_error = f"Erro ao salvar arquivos temporários do ZIP: {copy_e}"
                        cleanup_processed_files()

            except zipfile.BadZipFile:
                upload_error = "Erro: O arquivo enviado não parece ser um ZIP válido."
            except Exception as e:
                upload_error = f"Erro ao processar o ZIP: {e}"
                logging.error(f"Erro ao processar ZIP: {e}", exc_info=True)

    elif len(uploaded_files) == 2 and all(f.name.lower().endswith(".csv") for f in uploaded_files):
        st.sidebar.info("Processando arquivos CSV...")
        file1, file2 = uploaded_files
        identified_cabecalho = None
        identified_itens = None

        if file1.name.lower().endswith("_nfs_cabecalho.csv"): identified_cabecalho = file1
        elif file2.name.lower().endswith("_nfs_cabecalho.csv"): identified_cabecalho = file2

        if file1.name.lower().endswith("_nfs_itens.csv"): identified_itens = file1
        elif file2.name.lower().endswith("_nfs_itens.csv"): identified_itens = file2

        if identified_cabecalho and identified_itens:
            try:
                tmp_cabecalho_perm = tempfile.NamedTemporaryFile(delete=False, suffix="_cabecalho.csv")
                tmp_cabecalho_perm.write(identified_cabecalho.getvalue())
                st.session_state.processed_file_paths["cabecalho"] = tmp_cabecalho_perm.name
                tmp_cabecalho_perm.close()

                tmp_itens_perm = tempfile.NamedTemporaryFile(delete=False, suffix="_itens.csv")
                tmp_itens_perm.write(identified_itens.getvalue())
                st.session_state.processed_file_paths["itens"] = tmp_itens_perm.name
                tmp_itens_perm.close()
                
                st.session_state.files_ready_for_ingestion = True
                st.sidebar.success("Arquivos CSV identificados!")
            except Exception as copy_e:
                upload_error = f"Erro ao salvar arquivos temporários CSV: {copy_e}"
                cleanup_processed_files()
        else:
            upload_error = "Erro: Renomeie os arquivos para terminar com `_NFs_Cabecalho.csv` e `_NFs_Itens.csv`."

    elif len(uploaded_files) > 0:
        upload_error = "Erro: Envie exatamente 2 arquivos CSV ou 1 arquivo ZIP."

    if upload_error:
        st.sidebar.error(upload_error)
        cleanup_processed_files()

# --- Botão de Ingestão --- 
# Habilitar botão se arquivos estão prontos E (ingestão não está completa OU não está em progresso)
# Isso permite re-ingerir se o usuário quiser, mas não enquanto uma ingestão está ocorrendo.
ingest_button_disabled = not st.session_state.files_ready_for_ingestion or st.session_state.ingestion_in_progress

if st.sidebar.button("Processar Arquivos e Ingerir Dados", key="ingest_button", disabled=ingest_button_disabled):
    st.session_state.ingestion_in_progress = True
    st.session_state.ingestion_complete = False # Marcar como não completo ao iniciar nova ingestão
    st.rerun() # Mostrar spinner

# --- Lógica de Ingestão --- 
if st.session_state.ingestion_in_progress:
    with st.spinner("Processando arquivos e ingerindo dados no banco de dados SQLite..."):
        ingestion_success = False
        try:
            cabecalho_path = st.session_state.processed_file_paths.get("cabecalho")
            itens_path = st.session_state.processed_file_paths.get("itens")
            if not cabecalho_path or not itens_path or not os.path.exists(cabecalho_path) or not os.path.exists(itens_path):
                 raise ValueError("Caminhos dos arquivos CSV processados inválidos ou não encontrados para ingestão.")

            logging.info("Iniciando processo de ingestão...")
            conn = create_connection()
            if conn:
                create_tables(conn)
                success = ingest_data(conn, cabecalho_path, itens_path)
                conn.close()
                if success:
                    logging.info("Ingestão concluída com sucesso.")
                    ingestion_success = True # Marcar sucesso
                    st.sidebar.success("Dados ingeridos com sucesso! ✅") # Mover msg de sucesso para cá
                else:
                    st.sidebar.error("Falha na ingestão dos dados. Verifique os logs.")
                    logging.error("Falha durante a ingestão de dados.")
            else:
                st.sidebar.error("Não foi possível conectar ao banco de dados.")
                logging.error("Falha ao criar conexão com o banco de dados para ingestão.")
            
            # ATUALIZAR ESTADO AQUI, ANTES DO FINALLY E RERUN
            st.session_state.ingestion_complete = ingestion_success
            # st.session_state.db_exists = ingestion_success # Não precisamos mais disso

        except Exception as e:
            st.sidebar.error(f"Erro durante a ingestão: {e}")
            logging.error(f"Erro excepcional durante ingestão: {e}", exc_info=True)
            st.session_state.ingestion_complete = False # Garantir que falha marque como não completo
        finally:
            st.session_state.ingestion_in_progress = False # Terminou o processo
            # Limpar arquivos temporários processados APÓS a tentativa de ingestão
            cleanup_processed_files()
            # st.rerun() # Rerun para atualizar a UI com o novo estado de ingestion_complete
            # O rerun aqui pode ser o problema. Vamos tentar atualizar o estado e deixar o fluxo natural do Streamlit redesenhar.
            # Se o rerun for necessário, garantir que o estado seja lido corretamente após ele.
            # Vamos remover o rerun explícito e ver se o Streamlit atualiza corretamente.
            pass # Deixar o Streamlit redesenhar

# --- Mensagens de Status --- 
# Usar o estado atualizado para mostrar mensagens
if st.session_state.ingestion_complete:
    st.sidebar.success(f"Banco de dados `{os.path.basename(DB_FILE)}` pronto para consulta. ✅")
elif st.session_state.files_ready_for_ingestion and not st.session_state.ingestion_in_progress:
     st.sidebar.info("Arquivos identificados. Clique em \"Processar Arquivos\" para iniciar.")
elif not uploaded_files:
     st.sidebar.info("Aguardando o upload de arquivos (2 CSVs ou 1 ZIP).")
elif uploaded_files and not st.session_state.files_ready_for_ingestion and not upload_error:
     st.sidebar.info("Processando arquivos enviados...")
# Adicionar uma mensagem se a ingestão falhou mas não está mais em progresso
elif not st.session_state.ingestion_complete and not st.session_state.ingestion_in_progress and st.session_state.processed_file_paths.get("cabecalho") is None:
    # Isso cobre o caso onde a ingestão falhou e os arquivos temporários foram limpos
    st.sidebar.warning("A ingestão anterior falhou ou foi interrompida. Faça upload dos arquivos novamente.")


# --- Interface de Chat --- 
st.header("Chat com os Dados das Notas Fiscais")

for entry in st.session_state.history:
    with st.chat_message(entry["role"]):
        st.markdown(entry["content"])

# Habilitar chat SE a ingestão estiver completa E a chave API estiver presente
chat_disabled = not st.session_state.ingestion_complete or not st.session_state.google_api_key
disabled_reason = "" 
if not st.session_state.ingestion_complete:
    # Mensagem mais específica se o DB existe mas o estado não está completo (pode acontecer se app reiniciar)
    if os.path.exists(DB_FILE) and not st.session_state.ingestion_complete:
         disabled_reason += " O banco de dados existe, mas a ingestão precisa ser refeita nesta sessão. Faça upload e processe os arquivos."
    else:
        disabled_reason += " Faça o upload e processe os arquivos primeiro." 
if not st.session_state.google_api_key:
    disabled_reason += " Insira sua chave da API do Google na barra lateral." 

user_input = st.chat_input(
    "Faça sua pergunta sobre os dados...", 
    disabled=chat_disabled, 
    key="chat_input"
)

# Mostrar aviso apenas se o chat estiver desabilitado e não houver processos ativos
if chat_disabled and not st.session_state.ingestion_in_progress and not st.session_state.files_ready_for_ingestion:
    st.info(f"O chat está desabilitado.{disabled_reason}")

if user_input and not chat_disabled:
    st.session_state.history.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Pensando..."):
            try:
                # Verificar se o DB existe antes de tentar consultar
                if not os.path.exists(DB_FILE):
                    raise FileNotFoundError(f"O arquivo do banco de dados {DB_FILE} não foi encontrado. A ingestão pode ter falhado ou sido interrompida.")
                
                logging.info(f"Enviando pergunta para o agente: {user_input}")
                agent_raw_response = query_database_agent(user_input, st.session_state.google_api_key)
                logging.info(f"Resposta bruta do agente: {agent_raw_response}")
                
                formatted_output = format_response(agent_raw_response, user_input)
                logging.info("Resposta formatada gerada.")
                
                st.markdown(formatted_output)
                st.session_state.history.append({"role": "assistant", "content": formatted_output})
            
            except FileNotFoundError as e:
                error_msg = f"Erro: {e}"
                st.error(error_msg)
                st.session_state.history.append({"role": "assistant", "content": error_msg})
                logging.error(error_msg)
            except Exception as e:
                error_msg = f"Ocorreu um erro inesperado ao processar sua pergunta: {e}"
                st.error(error_msg)
                st.session_state.history.append({"role": "assistant", "content": error_msg})
                logging.error(f"Erro excepcional no fluxo de chat: {e}", exc_info=True)

st.sidebar.divider()

