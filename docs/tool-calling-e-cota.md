# Dinâmica de tool calling e impacto na cota

## Por que tool calling é necessário

O agente não é apenas um gerador de texto de query. Ele precisa **executar** a query no banco e usar o resultado para compor a resposta. Isso exige uma ferramenta real (`sql_db_query`) que o LLM pode invocar — sem ela, o agente só produziria SQL como texto sem nunca obter os dados.

A mesma lógica vale para `sql_db_schema` e `sql_db_list_tables`: o agente não "sabe" o schema de memória, ele consulta ativamente via tool call. Remover tool calling degradaria o sistema a um gerador de SQL sem execução — inútil para o usuário.

## O problema: múltiplas chamadas por pergunta

Cada pergunta do usuário não resulta em uma única chamada ao LLM. O padrão ReAct gera um loop de chamadas em sequência:

```
Pergunta → [inspecionar tabelas] → [ler schema] → [gerar SQL] → [executar] → Resposta
```

O `SQLDatabaseToolkit` expõe quatro ferramentas ao agente:

| Ferramenta | O que faz | Chamada LLM? |
|---|---|---|
| `sql_db_list_tables` | Lista as tabelas disponíveis | Não |
| `sql_db_schema` | Lê o schema das tabelas | Não |
| `sql_db_query` | Executa uma query SQL | Não |
| `sql_db_query_checker` | Valida a query antes de executar | **Sim** |

`sql_db_query_checker` faz uma chamada extra ao LLM só para confirmar que a query está sintaticamente correta — mesmo com o schema já no system prompt. Com a cota free do Gemini em 5 RPM, uma única pergunta do usuário pode consumir 4–5 slots em segundos.

## Solução adotada

`sql_db_query_checker` é removido da lista de ferramentas em `database_agent.py`. Como o system prompt já contém o schema completo das tabelas, o modelo tem informação suficiente para gerar SQL correto sem o step extra de validação.

```python
tools = [t for t in toolkit.get_tools() if t.name != "sql_db_query_checker"]
```

Esse trade-off é irrelevante em produção (RPM alto), mas crítico na cota free tier.

## Limitação estrutural do free tier

Mesmo com `sql_db_query_checker` removido, uma pergunta simples consome 3 chamadas LLM em média (raciocínio inicial → tool call → resposta final). Com o Gemini free tier em **5 RPM**, duas perguntas consecutivas em menos de um minuto esgotam a cota.

Isso não é um bug — é uma incompatibilidade entre o padrão ReAct (projetado para ambientes com RPM alto) e a cota free tier da API. O projeto funciona corretamente com uma chave paga ou com um provedor de RPM mais generoso (ex: Groq, que oferece ~30 RPM no free tier com modelos Llama).

**Para fins de demonstração e avaliação do projeto**, o comportamento correto pode ser observado fazendo perguntas espaçadas de pelo menos 30 segundos, ou usando uma chave com cota paga.

## Tratamento de erros de cota

Quando o limite é atingido, o erro retornado pela API é um JSON com status `429 RESOURCE_EXHAUSTED`. Antes de chegar à UI, `database_agent.py` intercepta esse JSON e retorna um código limpo:

```python
if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
    return {"error": "rate_limit"}
if "503" in error_str or "UNAVAILABLE" in error_str:
    return {"error": "unavailable"}
```

`output_formatter.py` converte esses códigos em mensagens legíveis ao usuário, sem expor o JSON cru da API no chat.
