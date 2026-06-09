# -*- coding: utf-8 -*-
import sqlite3
import logging
import os
from langchain_community.utilities import SQLDatabase
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_FILE = "notas_fiscais.db"

SYSTEM_PREFIX = """Você é um assistente especializado em análise de Notas Fiscais Eletrônicas (NF-e) brasileiras.
Você tem acesso a um banco de dados SQLite com duas tabelas interligadas pela coluna CHAVE_DE_ACESSO.

## Esquema

**nfs_cabecalho** — uma linha por nota fiscal:
- CHAVE_DE_ACESSO (PK, TEXT) — chave de 44 dígitos que identifica unicamente a NF-e
- MODELO, SERIE, NUMERO — identificação da nota
- NATUREZA_DA_OPERACAO — descrição da operação (ex: "Venda de mercadoria", "Remessa")
- DATA_EMISSAO — data de emissão da nota
- EVENTO_MAIS_RECENTE / DATA_HORA_EVENTO_MAIS_RECENTE — último evento registrado (ex: "Autorizado o uso da NF-e", "Cancelamento")
- CPF_CNPJ_EMITENTE, RAZAO_SOCIAL_EMITENTE, INSCRICAO_ESTADUAL_EMITENTE, UF_EMITENTE, MUNICIPIO_EMITENTE — dados do emitente
- CNPJ_DESTINATARIO, NOME_DESTINATARIO, UF_DESTINATARIO — dados do destinatário
- INDICADOR_IE_DESTINATARIO — situação do destinatário no ICMS: 1=contribuinte, 2=isento, 9=outros
- DESTINO_DA_OPERACAO — 1=operação interna (mesmo estado), 2=interestadual, 3=exterior
- CONSUMIDOR_FINAL — 0=não é consumidor final, 1=consumidor final
- PRESENCA_DO_COMPRADOR — modalidade da venda (ex: presencial, internet, teleatendimento)
- VALOR_NOTA_FISCAL (REAL) — valor total da NF-e em reais

**nfs_itens** — uma linha por item de cada nota:
- ID_ITEM (PK autoincrement), CHAVE_DE_ACESSO (FK → nfs_cabecalho)
- NUMERO_PRODUTO — número sequencial do item na nota
- DESCRICAO_PRODUTO_SERVICO — descrição do produto ou serviço
- CODIGO_NCM_SH — código NCM de classificação fiscal do produto (8 dígitos)
- NCM_SH_TIPO_PRODUTO — descrição do tipo de produto segundo a NCM
- CFOP (INTEGER) — código fiscal da operação:
    5xxx = operações dentro do estado (ex: 5102=venda de mercadoria dentro do estado)
    6xxx = operações interestaduais (ex: 6102=venda interestadual)
    7xxx = exportações
- QUANTIDADE (REAL) — quantidade vendida
- UNIDADE — unidade de medida (ex: UN, KG, CX, L)
- VALOR_UNITARIO (REAL) — preço unitário em reais
- VALOR_TOTAL (REAL) — valor total do item (QUANTIDADE × VALOR_UNITARIO)

## Regras obrigatórias
- Sempre responda em português do Brasil
- Formate valores monetários como R$ X.XXX,XX (padrão brasileiro) e datas como DD/MM/AAAA
- JOINs entre tabelas: use sempre CHAVE_DE_ACESSO como chave de ligação
- Nunca execute comandos DML (INSERT, UPDATE, DELETE, DROP)
- Verifique a query antes de executar; se retornar erro, reescreva e tente novamente
- Limite listagens longas a no máximo 20 itens, salvo instrução contrária do usuário
- Se não houver dados para o filtro solicitado, informe claramente que não há registros
- Se a pergunta for ambígua, escolha a interpretação mais útil e indique qual foi
- Para totais financeiros, prefira VALOR_NOTA_FISCAL do cabeçalho para totais por nota,
  e SUM(VALOR_TOTAL) dos itens para totais por produto/categoria

Dado esse contexto, responda com precisão à pergunta do usuário consultando o banco de dados."""


def get_db_connection():
    if not os.path.exists(DB_FILE):
        logging.error(f"Arquivo do banco de dados não encontrado: {DB_FILE}")
        raise FileNotFoundError(f"Arquivo do banco de dados não encontrado: {DB_FILE}")
    db_uri = f"sqlite:///{DB_FILE}"
    try:
        db = SQLDatabase.from_uri(db_uri)
        logging.info(f"SQLDatabase conectado a {DB_FILE}. Tabelas: {db.get_usable_table_names()}")
        return db
    except Exception as e:
        logging.error(f"Erro ao criar SQLDatabase a partir de {db_uri}: {e}")
        raise


def execute_direct_sql(sql_query: str):
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        logging.info(f"Executando SQL direto: {sql_query}")
        cursor.execute(sql_query)
        results = cursor.fetchall()
        column_names = [d[0] for d in cursor.description] if cursor.description else []
        conn.commit()
        return [dict(zip(column_names, row)) for row in results]
    except sqlite3.Error as e:
        logging.error(f"Erro ao executar SQL direto: {e}")
        return {"error": str(e)}
    finally:
        if conn:
            conn.close()


def query_database_agent(question: str, google_api_key: str):
    if not google_api_key:
        logging.error("Chave da API do Google não fornecida.")
        return {"error": "Chave da API do Google não fornecida."}

    try:
        db = get_db_connection()
        llm = ChatGoogleGenerativeAI(
            model="gemini-3.5-flash",
            google_api_key=google_api_key,
            temperature=0,
        )
        toolkit = SQLDatabaseToolkit(db=db, llm=llm)
        tools = toolkit.get_tools()

        agent = create_react_agent(model=llm, tools=tools)

        logging.info(f"Enviando pergunta ao agente: {question}")
        result = agent.invoke({
            "messages": [
                SystemMessage(content=SYSTEM_PREFIX),
                HumanMessage(content=question),
            ]
        })
        output = result["messages"][-1].content
        # Modelos com thinking retornam lista de blocos em vez de string —
        # normaliza para string independente do modelo usado
        if isinstance(output, list):
            output = "\n".join(
                block.get("text", "")
                for block in output
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return {"result": output}

    except FileNotFoundError as e:
        logging.error(f"Banco de dados não encontrado: {e}")
        return {"error": str(e)}
    except Exception as e:
        logging.error(f"Erro inesperado no agente SQL: {e}", exc_info=True)
        error_detail = str(e)
        if "Could not parse LLM output:" in error_detail:
            error_detail = f"Erro ao interpretar a resposta do modelo: {error_detail}"
        return {"error": f"Erro ao processar a consulta: {error_detail}"}


if __name__ == '__main__':
    print("--- Teste do Agente NF-e ---")
    if not os.path.exists(DB_FILE):
        print(f"Erro: {DB_FILE} não encontrado. Execute data_ingestion.py primeiro.")
    else:
        google_key = os.environ.get("GOOGLE_API_KEY")
        if not google_key:
            print("AVISO: GOOGLE_API_KEY não definida. Pulando teste do agente.")
        else:
            perguntas = [
                "Qual o valor total das notas fiscais?",
                "Liste os 5 produtos mais vendidos por valor total.",
                "Quantas notas foram emitidas por estado de destino?",
            ]
            for p in perguntas:
                print(f"\nPergunta: {p}")
                result = query_database_agent(p, google_key)
                print(f"Resposta: {result}")
    print("\n--- Teste Concluído ---")
