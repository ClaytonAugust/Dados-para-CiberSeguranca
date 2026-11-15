from .graph_retriever import GraphRetriever
from .hybrid_retriever import HybridRetriever

def __init__(self, graph):
    self.graph = graph
    self.last_queries = []