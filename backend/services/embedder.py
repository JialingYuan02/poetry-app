import os
from sentence_transformers import SentenceTransformer
import chromadb

BGE_QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
MODEL_NAME = "BAAI/bge-small-zh-v1.5"
VECTORSTORE_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "vectorstore")


class EmbedderService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.model = SentenceTransformer(MODEL_NAME)
        self.client = chromadb.PersistentClient(path=os.path.abspath(VECTORSTORE_PATH))
        cosine = {"hnsw:space": "cosine"}
        self.corpus = self.client.get_or_create_collection("corpus", metadata=cosine)
        self.personal = self.client.get_or_create_collection("personal", metadata=cosine)
        self._initialized = True

    def embed_text(self, text: str) -> list:
        return self.model.encode([text], normalize_embeddings=True)[0].tolist()

    def _embed_query(self, query: str) -> list:
        return self.model.encode([BGE_QUERY_PREFIX + query], normalize_embeddings=True)[0].tolist()

    def add_poem_to_corpus(self, poem_id: int, text: str, metadata: dict):
        self.corpus.upsert(
            ids=[str(poem_id)],
            embeddings=[self.embed_text(text)],
            documents=[text],
            metadatas=[metadata],
        )

    def add_poem_to_personal(self, poem_id: int, text: str, metadata: dict):
        self.personal.upsert(
            ids=[str(poem_id)],
            embeddings=[self.embed_text(text)],
            documents=[text],
            metadatas=[metadata],
        )

    def remove_from_personal(self, poem_id: int):
        self.personal.delete(ids=[str(poem_id)])

    def _format_results(self, results) -> list:
        items = []
        if not results["ids"] or not results["ids"][0]:
            return items
        for i, doc_id in enumerate(results["ids"][0]):
            items.append({
                "poem_id": int(doc_id),
                "distance": results["distances"][0][i],
                "metadata": results["metadatas"][0][i],
            })
        return items

    def search_corpus(self, query: str, n_results: int = 5) -> list:
        results = self.corpus.query(
            query_embeddings=[self._embed_query(query)],
            n_results=min(n_results, max(1, self.corpus.count())),
            include=["documents", "metadatas", "distances"],
        )
        return self._format_results(results)

    def search_personal(self, query: str, n_results: int = 5) -> list:
        if self.personal.count() == 0:
            return []
        results = self.personal.query(
            query_embeddings=[self._embed_query(query)],
            n_results=min(n_results, self.personal.count()),
            include=["documents", "metadatas", "distances"],
        )
        return self._format_results(results)

    def search_both(self, query: str, n_results: int = 8) -> list:
        corpus_hits = self.search_corpus(query, n_results)
        personal_hits = self.search_personal(query, n_results)
        seen = set()
        merged = []
        for hit in personal_hits + corpus_hits:
            pid = hit["poem_id"]
            if pid not in seen:
                seen.add(pid)
                merged.append(hit)
        merged.sort(key=lambda x: x["distance"])
        return merged[:n_results]

    def health_check(self) -> dict:
        return {
            "corpus_count": self.corpus.count(),
            "personal_count": self.personal.count(),
            "vectorstore_ready": self.corpus.count() > 0,
        }
