from langchain.text_splitter import CharaterTextSplitter


def chunk_data(state):
    splitter = CharaterTextSplitter(chunk_size=800, chunk_overlap=200)
    chunks = splitter.split_text(state["output"])
    return {"chunks": chunks}

graph.add_node("chunk", chunk_data)
graph.set_entry_point("load")
graph.add_edge("load", "chunk")
graph.set_finish_point("chunk")