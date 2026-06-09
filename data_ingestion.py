# -*- coding: utf-8 -*-
import sqlite3
import pandas as pd
import logging

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_FILE = "notas_fiscais.db"

# --- Funções do "Agente Curador" --- 

def get_database_schema():
    """ Retorna a definição do esquema do banco de dados (SQL para criação). """
    sql_create_cabecalho_table = """
    CREATE TABLE IF NOT EXISTS nfs_cabecalho (
        CHAVE_DE_ACESSO TEXT PRIMARY KEY,
        MODELO TEXT,
        SERIE INTEGER,
        NUMERO INTEGER,
        NATUREZA_DA_OPERACAO TEXT,
        DATA_EMISSAO TEXT,
        EVENTO_MAIS_RECENTE TEXT,
        DATA_HORA_EVENTO_MAIS_RECENTE TEXT,
        CPF_CNPJ_EMITENTE TEXT,
        RAZAO_SOCIAL_EMITENTE TEXT,
        INSCRICAO_ESTADUAL_EMITENTE TEXT,
        UF_EMITENTE TEXT,
        MUNICIPIO_EMITENTE TEXT,
        CNPJ_DESTINATARIO TEXT,
        NOME_DESTINATARIO TEXT,
        UF_DESTINATARIO TEXT,
        INDICADOR_IE_DESTINATARIO TEXT,
        DESTINO_DA_OPERACAO TEXT,
        CONSUMIDOR_FINAL TEXT,
        PRESENCA_DO_COMPRADOR TEXT,
        VALOR_NOTA_FISCAL REAL
    );"""

    sql_create_itens_table = """
    CREATE TABLE IF NOT EXISTS nfs_itens (
        ID_ITEM INTEGER PRIMARY KEY AUTOINCREMENT,
        CHAVE_DE_ACESSO TEXT NOT NULL,
        NUMERO_PRODUTO INTEGER,
        DESCRICAO_PRODUTO_SERVICO TEXT,
        CODIGO_NCM_SH TEXT,
        NCM_SH_TIPO_PRODUTO TEXT,
        CFOP INTEGER,
        QUANTIDADE REAL,
        UNIDADE TEXT,
        VALOR_UNITARIO REAL,
        VALOR_TOTAL REAL,
        FOREIGN KEY (CHAVE_DE_ACESSO) REFERENCES nfs_cabecalho (CHAVE_DE_ACESSO)
    );"""
    return [sql_create_cabecalho_table, sql_create_itens_table]

def get_ingestion_instructions():
    """ Retorna as instruções de mapeamento de colunas para a ingestão. """
    cabecalho_column_mapping = {
        'CHAVE DE ACESSO': 'CHAVE_DE_ACESSO',
        'MODELO': 'MODELO',
        'SÉRIE': 'SERIE',
        'NÚMERO': 'NUMERO',
        'NATUREZA DA OPERAÇÃO': 'NATUREZA_DA_OPERACAO',
        'DATA EMISSÃO': 'DATA_EMISSAO',
        'EVENTO MAIS RECENTE': 'EVENTO_MAIS_RECENTE',
        'DATA/HORA EVENTO MAIS RECENTE': 'DATA_HORA_EVENTO_MAIS_RECENTE',
        'CPF/CNPJ Emitente': 'CPF_CNPJ_EMITENTE',
        'RAZÃO SOCIAL EMITENTE': 'RAZAO_SOCIAL_EMITENTE',
        'INSCRIÇÃO ESTADUAL EMITENTE': 'INSCRICAO_ESTADUAL_EMITENTE',
        'UF EMITENTE': 'UF_EMITENTE',
        'MUNICÍPIO EMITENTE': 'MUNICIPIO_EMITENTE',
        'CNPJ DESTINATÁRIO': 'CNPJ_DESTINATARIO',
        'NOME DESTINATÁRIO': 'NOME_DESTINATARIO',
        'UF DESTINATÁRIO': 'UF_DESTINATARIO',
        'INDICADOR IE DESTINATÁRIO': 'INDICADOR_IE_DESTINATARIO',
        'DESTINO DA OPERAÇÃO': 'DESTINO_DA_OPERACAO',
        'CONSUMIDOR FINAL': 'CONSUMIDOR_FINAL',
        'PRESENÇA DO COMPRADOR': 'PRESENCA_DO_COMPRADOR',
        'VALOR NOTA FISCAL': 'VALOR_NOTA_FISCAL'
    }

    itens_column_mapping = {
        'CHAVE DE ACESSO': 'CHAVE_DE_ACESSO',
        'NÚMERO PRODUTO': 'NUMERO_PRODUTO',
        'DESCRIÇÃO DO PRODUTO/SERVIÇO': 'DESCRICAO_PRODUTO_SERVICO',
        'CÓDIGO NCM/SH': 'CODIGO_NCM_SH',
        'NCM/SH (TIPO DE PRODUTO)': 'NCM_SH_TIPO_PRODUTO',
        'CFOP': 'CFOP',
        'QUANTIDADE': 'QUANTIDADE',
        'UNIDADE': 'UNIDADE',
        'VALOR UNITÁRIO': 'VALOR_UNITARIO',
        'VALOR TOTAL': 'VALOR_TOTAL'
    }
    return {"cabecalho": cabecalho_column_mapping, "itens": itens_column_mapping}

# --- Funções de Banco de Dados (Poderiam estar no Agente Especialista) ---

def create_connection(db_file=DB_FILE):
    """ Cria uma conexão com o banco de dados SQLite. """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
        logging.info(f"Conexão com SQLite DB versão {sqlite3.sqlite_version} estabelecida em {db_file}")
        return conn
    except sqlite3.Error as e:
        logging.error(f"Erro ao conectar ao banco de dados {db_file}: {e}")
        return None

def create_tables(conn):
    """ Cria as tabelas com base no esquema do 'Agente Curador'. """
    schema_sqls = get_database_schema()
    try:
        cursor = conn.cursor()
        logging.info("Executando criação de tabelas (se não existirem)...")
        for sql in schema_sqls:
            cursor.execute(sql)
        conn.commit()
        logging.info("Tabelas verificadas/criadas com sucesso.")
    except sqlite3.Error as e:
        logging.error(f"Erro ao criar tabelas: {e}")

def read_csv_flexible(filepath):
    for sep in [',', ';']:
        try:
            df = pd.read_csv(filepath, sep=sep)
            # descarta leitura com separador errado (todas as colunas em uma só)
            if len(df.columns) > 1:
                logging.info(f"CSV lido com separador '{sep}' | shape: {df.shape}")
                logging.info(f"Colunas encontradas: {list(df.columns)}")
                return df
            logging.warning(f"Separador '{sep}' produziu apenas 1 coluna — tentando próximo")
        except Exception as e:
            logging.warning(f"Falha ao ler com '{sep}': {e}")
    raise ValueError(f"Não foi possível ler {filepath} com ',' nem ';'")

def ingest_data(conn, cabecalho_csv_path, itens_csv_path):
    """ Lê os arquivos CSV e insere os dados nas tabelas SQLite usando as instruções do 'Agente Curador'. """
    try:
        ingestion_instructions = get_ingestion_instructions()
        cabecalho_mapping = ingestion_instructions["cabecalho"]
        itens_mapping = ingestion_instructions["itens"]

        # --- CABEÇALHO ---
        logging.info(f"[CABECALHO] Lendo: {cabecalho_csv_path}")
        df_cabecalho = read_csv_flexible(cabecalho_csv_path)

        colunas_csv = set(df_cabecalho.columns)
        colunas_esperadas = set(cabecalho_mapping.keys())
        nao_encontradas = colunas_esperadas - colunas_csv
        extras = colunas_csv - colunas_esperadas
        if nao_encontradas:
            logging.warning(f"[CABECALHO] Colunas do mapeamento NÃO encontradas no CSV: {sorted(nao_encontradas)}")
        if extras:
            logging.info(f"[CABECALHO] Colunas extras no CSV (ignoradas): {sorted(extras)}")

        df_cabecalho.rename(columns=cabecalho_mapping, inplace=True)

        df_cabecalho['VALOR_NOTA_FISCAL'] = pd.to_numeric(df_cabecalho['VALOR_NOTA_FISCAL'], errors='coerce')
        df_cabecalho['SERIE'] = pd.to_numeric(df_cabecalho['SERIE'], errors='coerce').astype('Int64')
        df_cabecalho['NUMERO'] = pd.to_numeric(df_cabecalho['NUMERO'], errors='coerce').astype('Int64')

        nulos_valor = df_cabecalho['VALOR_NOTA_FISCAL'].isna().sum()
        if nulos_valor > 0:
            logging.warning(f"[CABECALHO] {nulos_valor} linhas com VALOR_NOTA_FISCAL nulo após conversão")

        colunas_para_inserir = [c for c in cabecalho_mapping.values() if c in df_cabecalho.columns]
        colunas_faltando = [c for c in cabecalho_mapping.values() if c not in df_cabecalho.columns]
        if colunas_faltando:
            logging.warning(f"[CABECALHO] Colunas ausentes na inserção: {colunas_faltando}")

        logging.info(f"[CABECALHO] Inserindo {len(df_cabecalho)} linhas em nfs_cabecalho...")
        df_cabecalho[colunas_para_inserir].to_sql('nfs_cabecalho', conn, if_exists='replace', index=False)
        logging.info(f"[CABECALHO] OK — {len(df_cabecalho)} registros inseridos.")

        # --- ITENS ---
        logging.info(f"[ITENS] Lendo: {itens_csv_path}")
        df_itens = read_csv_flexible(itens_csv_path)

        colunas_csv_itens = set(df_itens.columns)
        colunas_esperadas_itens = set(itens_mapping.keys())
        nao_encontradas_itens = colunas_esperadas_itens - colunas_csv_itens
        extras_itens = colunas_csv_itens - colunas_esperadas_itens
        if nao_encontradas_itens:
            logging.warning(f"[ITENS] Colunas do mapeamento NÃO encontradas no CSV: {sorted(nao_encontradas_itens)}")
        if extras_itens:
            logging.info(f"[ITENS] Colunas extras no CSV (ignoradas): {sorted(extras_itens)}")

        df_itens.rename(columns=itens_mapping, inplace=True)

        colunas_itens_disponiveis = [c for c in itens_mapping.values() if c in df_itens.columns]
        df_itens_final = df_itens[colunas_itens_disponiveis].copy()

        for col in ['NUMERO_PRODUTO', 'CFOP']:
            if col in df_itens_final.columns:
                df_itens_final[col] = pd.to_numeric(df_itens_final[col], errors='coerce').astype('Int64')
        for col in ['QUANTIDADE', 'VALOR_UNITARIO', 'VALOR_TOTAL']:
            if col in df_itens_final.columns:
                nulos = df_itens_final[col].isna().sum()
                df_itens_final[col] = pd.to_numeric(df_itens_final[col], errors='coerce')
                nulos_depois = df_itens_final[col].isna().sum()
                if nulos_depois > nulos:
                    logging.warning(f"[ITENS] {nulos_depois - nulos} novos nulos em {col} após conversão numérica")

        cursor = conn.cursor()
        cursor.execute("DELETE FROM nfs_itens;")
        conn.commit()

        logging.info(f"[ITENS] Inserindo {len(df_itens_final)} linhas em nfs_itens...")
        df_itens_final.to_sql('nfs_itens', conn, if_exists='append', index=False)
        logging.info(f"[ITENS] OK — {len(df_itens_final)} registros inseridos.")

        logging.info("Ingestão concluída com sucesso.")
        return True

    except FileNotFoundError as e:
        logging.error(f"Erro: Arquivo não encontrado - {e}")
        return False
    except pd.errors.EmptyDataError as e:
        logging.error(f"Erro: Arquivo CSV vazio ou inválido - {e}")
        return False
    except sqlite3.Error as e:
        logging.error(f"Erro durante a ingestão no SQLite: {e}")
        return False
    except Exception as e:
        logging.error(f"Erro inesperado durante a ingestão: {e}")
        return False

# Bloco para teste direto do script (opcional)
if __name__ == '__main__':
    cabecalho_file = '/home/ubuntu/upload/202401_NFs_Cabecalho.csv'
    itens_file = '/home/ubuntu/upload/202401_NFs_Itens.csv'

    conn = create_connection()
    if conn is not None:
        create_tables(conn) # Usa get_database_schema internamente
        success = ingest_data(conn, cabecalho_file, itens_file) # Usa get_ingestion_instructions internamente
        if success:
            print("\nTeste de ingestão concluído com sucesso.")
            try:
                print("\nVerificando contagem de registros:")
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM nfs_cabecalho")
                print(f"Cabeçalhos: {cursor.fetchone()[0]}")
                cursor.execute("SELECT COUNT(*) FROM nfs_itens")
                print(f"Itens: {cursor.fetchone()[0]}")
            except sqlite3.Error as e:
                print(f"Erro ao verificar contagem: {e}")
        else:
            print("\nTeste de ingestão falhou.")
        conn.close()
        logging.info("Conexão com o banco de dados fechada.")
    else:
        print("Falha ao conectar ao banco de dados.")


