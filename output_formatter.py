# -*- coding: utf-8 -*-
import pandas as pd
import logging
import re

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Funções de Formatação (mantidas para possível uso futuro, mas não aplicadas por padrão) ---
# import locale
# try:
#     locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
# except locale.Error:
#     try: locale.setlocale(locale.LC_ALL, 'pt_BR')
#     except: logging.warning("Locale pt_BR não definido.")

def format_brazilian_currency(value):
    if pd.isna(value): return ""
    try:
        num = float(value)
        formatted = f"{num:_.2f}".replace(".", "#").replace("_", ".").replace("#", ",")
        return f"R$ {formatted}"
    except: return str(value)

def format_brazilian_number(value):
    if pd.isna(value): return ""
    try:
        if isinstance(value, (int, float)) and value == int(value):
            return f"{int(value):_}".replace("_", ".")
        else:
            return f"{float(value):_.2f}".replace(".", "#").replace("_", ".").replace("#", ",")
    except: return str(value)

def _format_matched_number_as_currency(match):
    number_str = match.group(1).replace(".", "").replace(",", ".")
    try: return format_brazilian_currency(float(number_str))
    except: return match.group(0)

def format_currency_in_text(text):
    if not isinstance(text, str): return text
    # Regex simplificado para evitar complexidade e erros
    # Apenas números com 2 casas decimais precedidos por espaço ou início de linha
    pattern = r"(?<=\s|^)(\d+(?:\.\d+)*,\d{2})(?=\s|$)"
    pattern_dot = r"(?<=\s|^)(\d+\.\d{2})(?=\s|$)" # Formato 123.45
    try:
        formatted_text = re.sub(pattern, _format_matched_number_as_currency, text)
        formatted_text = re.sub(pattern_dot, _format_matched_number_as_currency, formatted_text)
        return formatted_text
    except Exception as e:
        logging.error(f"Erro na formatação de moeda em texto (regex): {e}")
        return text
# --- Fim Funções de Formatação ---

def is_markdown_table(text: str) -> bool:
    """ Verifica heuristicamente se o texto parece ser uma tabela Markdown. """
    if not isinstance(text, str):
        return False
    # Procurar por padrões comuns de tabelas Markdown
    # Linha de separador: |---|---| ou |:---|:---:|
    if re.search(r"\|.*\|.*\|\n\| *[:-]-+[:-]? *\|.*\|", text):
        return True
    # Múltiplas linhas começando e terminando com |
    if len(re.findall(r"^\|.*\|$", text, re.MULTILINE)) > 1:
        return True
    return False

def format_response(agent_response: dict, original_question: str) -> str:
    """ 
    Formata a resposta do agente, exibindo tabelas Markdown ou texto conversacional.
    (Versão focada em exibir a resposta do agente de forma robusta).
    """
    logging.info(f"Formatando resposta para a pergunta: \n{original_question}\n")
    logging.debug(f"Resposta bruta recebida: {agent_response}")

    # Lidar com respostas que não são dict (caso raro, mas possível)
    if not isinstance(agent_response, dict):
        logging.warning(f"Formato de resposta inesperado (não dict): {type(agent_response)}. Retornando como string.")
        # Tentar exibir como string, pode ser texto direto ou representação de lista/etc.
        return str(agent_response)

    # Caso 1: Erro explícito retornado pelo agente
    if "error" in agent_response:
        code = agent_response["error"]
        logging.error(f"Erro retornado pelo agente: {code}")
        messages = {
            "rate_limit": "Limite de requisições por minuto atingido. Aguarde alguns segundos e tente novamente.",
            "unavailable": "O modelo está temporariamente sobrecarregado. Tente novamente em alguns segundos.",
            "unexpected": "Ocorreu um erro inesperado. Tente reformular a pergunta ou verifique sua chave de API.",
        }
        return messages.get(code, f"Erro: {code}")

    # Caso 2: Resposta bem-sucedida (contida em "result")
    if "result" in agent_response:
        result_content = agent_response["result"]
        logging.info("Processando conteúdo de \'result\'.")
        
        # Verificar se o conteúdo é uma string (esperado do agente .run())
        if isinstance(result_content, str):
            # Verificar se a string parece ser uma tabela Markdown
            if is_markdown_table(result_content):
                logging.info("Resultado identificado como tabela Markdown. Exibindo diretamente.")
                # Simplesmente retorna a string Markdown para o Streamlit renderizar
                # Nenhuma formatação numérica aplicada aqui para garantir estabilidade
                return f"**Resultado da Consulta:**\n\n{result_content}"
            else:
                logging.info("Resultado identificado como texto conversacional. Exibindo diretamente.")
                # É texto conversacional, retorna como está.
                # Nenhuma formatação numérica aplicada aqui para garantir estabilidade
                # Se quiséssemos tentar formatar moeda no texto, seria aqui:
                # formatted_text = format_currency_in_text(result_content) # Desativado por padrão
                # return f"**Resposta:**\n\n{formatted_text}"
                return f"**Resposta:**\n\n{result_content}"
        else:
            # Se o resultado não for string (inesperado, mas tratar)
            logging.warning(f"Conteúdo de \'result\' não é string ({type(result_content)}). Exibindo como string.")
            return f"**Resposta (formato inesperado):**\n\n```\n{str(result_content)}\n```"

    # Caso 3: Dicionário, mas sem "error" ou "result" (formato inesperado)
    logging.warning(f"Formato de dicionário inesperado na resposta (sem error/result): {agent_response}")
    return f"**Resposta (formato inesperado):**\n\n```\n{str(agent_response)}\n```"

# Bloco para teste direto do script (opcional)
if __name__ == '__main__':
    print("--- Teste do Agente Formatador de Saída (Robusto) ---")

    # Teste 1: Erro
    error_resp = {"error": "Falha grave."}
    print("\nTeste 1: Erro")
    print(format_response(error_resp, "Pergunta"))

    # Teste 2: Resposta textual
    text_resp = {"result": "O faturamento total foi 12345.67 para o cliente X."}
    print("\nTeste 2: Texto Conversacional")
    print(format_response(text_resp, "Qual faturamento?"))

    # Teste 3: Resposta Tabela Markdown
    table_resp = {"result": "| Col A | Col B |\n|---|---|\n| Val 1 | 100,00 |\n| Val 2 | 2.000,50 |"}
    print("\nTeste 3: Tabela Markdown")
    print(format_response(table_resp, "Me dê a tabela"))

    # Teste 4: Resposta Inesperada (não dict)
    unexpected_resp = [1, 2, 3]
    print("\nTeste 4: Resposta Inesperada (Lista)")
    print(format_response(unexpected_resp, "Pergunta"))

    # Teste 5: Resposta Inesperada (dict sem result/error)
    unexpected_dict = {"data": "abc"}
    print("\nTeste 5: Resposta Inesperada (Dict)")
    print(format_response(unexpected_dict, "Pergunta"))

    print("\n--- Teste Concluído ---")