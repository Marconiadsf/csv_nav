# csv-nav

Ferramenta conversacional para análise de Notas Fiscais Eletrônicas (NF-e) brasileiras via linguagem natural. O usuário faz upload dos arquivos CSV exportados da SEFAZ, faz perguntas em português e recebe respostas baseadas nos dados reais — sem escrever SQL.

Demo: [csvnav-dvjmgnhdbkphhishggyi6q.streamlit.app](https://csvnav-dvjmgnhdbkphhishggyi6q.streamlit.app/)

---

## Como funciona

O fluxo tem três etapas:

1. **Ingestão** — os CSVs são lidos, as colunas mapeadas dos nomes originais da SEFAZ para nomes SQL-friendly, e os dados carregados em um banco SQLite local com duas tabelas relacionadas (`nfs_cabecalho` e `nfs_itens`).

2. **Agente SQL** — a pergunta do usuário é passada a um agente LangChain que usa o modelo Gemini para gerar a query SQL correspondente, executa no SQLite e retorna o resultado.

3. **Interface** — tudo exposto via Streamlit: upload de arquivos, campo de chat e exibição das respostas.

O padrão de agente usado é ReAct (Reasoning + Acting): o modelo alterna entre raciocinar sobre o que precisa saber, escolher uma ferramenta SQL (inspecionar schema, executar query, checar resultado) e agir — até ter dados suficientes para responder.

---

## Tecnologias

| Camada | Tecnologia |
|---|---|
| LLM | Google Gemini 2.5 Flash |
| Orquestração de agente | LangGraph (`create_react_agent`) + LangChain (`SQLDatabaseToolkit`) |
| Banco de dados | SQLite |
| Interface | Streamlit |
| Manipulação de dados | Pandas |
| Linguagem | Python 3 |

---

## Estrutura

```
csv_nav/
├── app.py               # Interface Streamlit e gerenciamento de estado
├── data_ingestion.py    # Leitura dos CSVs, mapeamento de colunas, carga no SQLite
├── database_agent.py    # Configuração do agente LangChain + system prompt
├── output_formatter.py  # Formatação das respostas para exibição
└── requirements.txt
```

---

## Rodando localmente

**Pré-requisitos:** Python 3.10+ e uma chave da [Google AI Studio](https://aistudio.google.com/app/apikey).

```bash
git clone https://github.com/marconiadsf/csv_nav.git
cd csv_nav
pip install -r requirements.txt
streamlit run app.py
```

A chave da API é inserida diretamente na interface — não é necessário configurar variável de ambiente.

---

## Formato dos arquivos

A ferramenta espera os CSVs no formato padrão exportado pelo portal da SEFAZ:

- `*_NFs_Cabecalho.csv` — dados do cabeçalho da NF-e
- `*_NFs_Itens.csv` — itens de cada nota

Também aceita um único arquivo `.zip` contendo os dois CSVs.

---

## Conceitos aplicados

- **Text-to-SQL via LLM** — tradução de linguagem natural para SQL usando um modelo de linguagem como intermediário
- **Padrão ReAct** — agente que alterna raciocínio e ação em loop até atingir resposta suficiente
- **System prompt estruturado** — o agente recebe schema completo das tabelas e regras de output antes de qualquer pergunta, garantindo consistência nas respostas
- **Schema da NF-e** — modelagem dos dados fiscais brasileiros (CFOP, NCM, CHAVE_DE_ACESSO, emitente/destinatário)
