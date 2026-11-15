
import os
import sys
import tempfile

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from dotenv import load_dotenv
from falkordb import FalkorDB
from pyvis.network import Network

# --------------------------------------------------
# CONFIGURAÇÃO DO PROJETO
# --------------------------------------------------

ROOT = Path(__file__).resolve().parents[3]

sys.path.insert(0, str(ROOT / "src"))

load_dotenv(ROOT / ".env")

from cti_graphrag.pipeline.answer import GraphRAGPipeline


st.set_page_config(
    page_title="CTI GraphRAG",
    page_icon="🛡️",
    layout="wide"
)


# --------------------------------------------------
# CONEXÃO COM O FALKORDB E PIPELINE
# --------------------------------------------------

@st.cache_resource(show_spinner=False)
def carregar_pipeline(host, port, graph_name):

    db = FalkorDB(
        host=host,
        port=port
    )

    graph = db.select_graph(graph_name)

    pipeline = GraphRAGPipeline(graph)

    # Mantemos db vivo junto ao pipeline.
    return db, pipeline


# --------------------------------------------------
# VISUALIZAÇÃO DO SUBGRAFO
# --------------------------------------------------

def mostrar_grafo(answer):

    if not answer.nodes:
        st.info("Nenhum nó disponível para visualizar.")
        return

    network = Network(
        height="520px",
        width="100%",
        directed=True,
        bgcolor="#111827",
        font_color="#FFFFFF",
        notebook=False,
        cdn_resources="in_line"
    )

    for node in answer.nodes:

        network.add_node(
            node.id,
            label=f"{node.name}\n[{node.label}]",
            title=f"ID: {node.id}\nTipo: {node.label}",
            group=node.label
        )

    for edge in answer.edges:

        network.add_edge(
            edge.from_,
            edge.to,
            label=edge.type,
            title=edge.type,
            arrows="to"
        )

    network.toggle_physics(True)

    temporary_file = tempfile.NamedTemporaryFile(
        suffix=".html",
        delete=False
    )

    temporary_path = Path(temporary_file.name)
    temporary_file.close()

    try:

        network.write_html(
            str(temporary_path),
            notebook=False,
            open_browser=False
        )

        html_content = temporary_path.read_text(
            encoding="utf-8"
        )

        components.html(
            html_content,
            height=550,
            scrolling=True
        )

    finally:

        temporary_path.unlink(missing_ok=True)


# --------------------------------------------------
# EXPLICABILIDADE DA RESPOSTA
# --------------------------------------------------

def mostrar_procedencia(answer):

    col1, col2 = st.columns(2)

    col1.metric(
        "Indicador de recuperação",
        f"{answer.confidence:.2%}"
    )

    col2.metric(
        "Tempo total",
        f"{answer.latency_ms} ms"
    )

    st.caption(
        "O indicador é a similaridade semântica média "
        "dos resultados recuperados; não representa "
        "uma probabilidade calibrada de acerto."
    )

    with st.expander(
        "Caminhos e evidências utilizados",
        expanded=True
    ):

        if not answer.paths:
            st.info("Nenhum caminho foi identificado.")

        for path in answer.paths:

            st.markdown(f"**[{path.id}]**")

            if path.nodes:
                st.write(
                    "Nós:",
                    " → ".join(path.nodes)
                )

            if path.rels:
                st.write(
                    "Relacionamentos:",
                    " → ".join(path.rels)
                )

            if path.chunk_ids:
                st.write(
                    "Chunks:",
                    ", ".join(path.chunk_ids)
                )

            if not path.rels:
                st.caption(
                    "Evidência documental recuperada "
                    "sem expansão de relacionamento."
                )

    with st.expander("Visualização do subgrafo"):

        mostrar_grafo(answer)

    with st.expander("Consultas Cypher utilizadas"):

        if answer.cypher:
            st.code(
                answer.cypher,
                language="cypher"
            )
        else:
            st.info("Nenhuma consulta registrada.")


# --------------------------------------------------
# INTERFACE PRINCIPAL
# --------------------------------------------------

st.title("🛡️ CTI GraphRAG")

st.markdown(
    """
    Sistema de inteligência de ameaças cibernéticas.

    Faça perguntas sobre grupos de ameaça, malwares,
    ferramentas, técnicas e relacionamentos recuperados
    do grafo de conhecimento.
    """
)

host = os.getenv(
    "FALKORDB_HOST",
    "127.0.0.1"
)

port = int(
    os.getenv("FALKORDB_PORT", "6379")
)

graph_name = os.getenv(
    "GRAPH_NAME",
    "cti_gold"
)


# --------------------------------------------------
# BARRA LATERAL
# --------------------------------------------------

with st.sidebar:

    st.header("Configurações")

    st.write("Banco:", "FalkorDB")
    st.write("Grafo:", graph_name)

    st.divider()

    st.caption(
        f"Servidor: {host}:{port}"
    )

    if st.button(
        "Limpar conversa",
        use_container_width=True
    ):

        st.session_state.messages = []
        st.rerun()

    st.divider()

    st.caption(
        "CTI GraphRAG — MITRE ATT&CK / CISA KEV"
    )


# --------------------------------------------------
# HISTÓRICO
# --------------------------------------------------

if "messages" not in st.session_state:
    st.session_state.messages = []


# --------------------------------------------------
# INICIALIZAR PIPELINE
# --------------------------------------------------

try:

    with st.spinner(
        "Conectando ao FalkorDB e carregando o modelo..."
    ):

        db, pipeline = carregar_pipeline(
            host,
            port,
            graph_name
        )

except Exception as erro:

    st.error(
        f"Não foi possível inicializar a aplicação: {erro}"
    )

    st.stop()


# --------------------------------------------------
# EXIBIR HISTÓRICO
# --------------------------------------------------

for message in st.session_state.messages:

    with st.chat_message(message["role"]):

        st.markdown(message["content"])

        answer = message.get("answer")

        if answer is not None:

            mostrar_procedencia(answer)


# --------------------------------------------------
# CAMPO DE PERGUNTA
# --------------------------------------------------

question = st.chat_input(
    "Ex.: Quais ferramentas são utilizadas pelo grupo Andariel?"
)

if question:

    st.session_state.messages.append({
        "role": "user",
        "content": question
    })

    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):

        try:

            with st.spinner(
                "Investigando o grafo e consultando o Gemini..."
            ):

                result = pipeline.answer(
                    question,
                    top_k=5,
                    max_entities=20
                )

            st.markdown(result.answer)

            mostrar_procedencia(result)

            st.session_state.messages.append({
                "role": "assistant",
                "content": result.answer,
                "answer": result
            })

        except Exception as erro:

            mensagem = (
                f"Não foi possível processar a pergunta: "
                f"{type(erro).__name__}: {erro}"
            )

            st.error(mensagem)

            st.session_state.messages.append({
                "role": "assistant",
                "content": mensagem
            })
