from __future__ import annotations

from pathlib import Path

import pytest

from rag_maker.adapters.driven.lancedb.vector_store import LanceVectorStore
from rag_maker.domain.models import Chunk, IndexedChunk

_DIM = 8


def _make_chunk(chunk_id: str, source: str = "doc.txt", content: str = "texto") -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_path=Path(source),
        content=content,
        char_offset=0,
        mtime=1.0,
    )


def _make_indexed(chunk_id: str, val: float = 0.1, **kw: object) -> IndexedChunk:
    vec = tuple([val] * _DIM)
    return IndexedChunk(chunk=_make_chunk(chunk_id, **kw), vector=vec)  # type: ignore[arg-type]


@pytest.mark.integration
class TestLanceVectorStore:
    def test_count_empty(self, tmp_path: Path) -> None:
        store = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        assert store.count() == 0

    def test_upsert_and_count(self, tmp_path: Path) -> None:
        store = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        store.upsert([_make_indexed("c1"), _make_indexed("c2")])
        assert store.count() == 2

    def test_upsert_idempotent(self, tmp_path: Path) -> None:
        store = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        ic = _make_indexed("c1")
        store.upsert([ic])
        store.upsert([ic])
        assert store.count() == 1

    def test_delete_by_source(self, tmp_path: Path) -> None:
        store = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        store.upsert(
            [
                _make_indexed("c1", source="a.txt"),
                _make_indexed("c2", source="b.txt"),
            ]
        )
        store.delete_by_source("a.txt")
        assert store.count() == 1

    def test_stats(self, tmp_path: Path) -> None:
        store = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        s = store.stats()
        assert s["embedding_dim"] == _DIM
        assert "count" in s

    def test_hybrid_search_returns_results(self, tmp_path: Path) -> None:
        store = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        store.upsert(
            [
                _make_indexed("c1", val=0.9, content="hermetismo e alquimia"),
                _make_indexed("c2", val=0.1, content="receita de bolo"),
            ]
        )
        query_vec = tuple([0.9] * _DIM)
        results = store.hybrid_search(query_vec, "hermetismo", top_n=5)
        assert len(results) >= 1
        ids = [r.chunk.chunk_id for r in results]
        assert "c1" in ids

    def test_hybrid_search_top_n_respected(self, tmp_path: Path) -> None:
        store = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        chunks = [_make_indexed(f"c{i}") for i in range(10)]
        store.upsert(chunks)
        results = store.hybrid_search(tuple([0.5] * _DIM), "texto", top_n=3)
        assert len(results) <= 3

    def test_persist_across_open(self, tmp_path: Path) -> None:
        store1 = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        store1.upsert([_make_indexed("c1")])
        store2 = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        assert store2.count() == 1

    def test_ensure_fts_index_makes_lexical_search_find_exact_term(self, tmp_path: Path) -> None:
        """AUD-TEST-2 (regressão): sem ensure_fts_index(), self._table.search(
        text, query_type="fts") levanta RuntimeError ("Cannot perform full
        text search unless an INVERTED index has been created"), engolido
        pelo except silencioso — hybrid_search degrada pra dense-only pra
        sempre. Este teste prova que o índice FTS de fato existe e que uma
        query lexical por termo EXATO recupera o chunk certo — não basta
        "não crashar" (os testes antigos passavam com lexical_score=0.0
        sempre, ver test_hybrid_search_returns_results).

        Vetores DELIBERADAMENTE próximos (mesmo `val`) para que dense-only
        não consiga discriminar os dois chunks — só a metade lexical do RRF
        pode colocar 'c_target' à frente de 'c_noise'.
        """
        store = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        store.upsert(
            [
                _make_indexed("c_target", val=0.5, content="xylophone quartznaut"),
                _make_indexed("c_noise", val=0.5, content="banana café tesoura"),
            ]
        )
        store.ensure_fts_index()

        # Busca direta por FTS pura no termo exato — se o índice invertido não
        # existir, isto levanta RuntimeError (era o bug: nunca chegava a
        # rodar porque ninguém chamava ensure_fts_index()).
        fts_rows = store._table.search("xylophone", query_type="fts").to_list()
        assert len(fts_rows) == 1
        assert fts_rows[0]["chunk_id"] == "c_target"

        # E via hybrid_search (RRF dense+lexical): com vetores empatados no
        # lado denso, só a lexical consegue ranquear 'c_target' em primeiro.
        query_vec = tuple([0.5] * _DIM)
        results = store.hybrid_search(query_vec, "xylophone", top_n=5)
        assert results[0].chunk.chunk_id == "c_target"
        assert results[0].lexical_score > 0.0

    def test_hybrid_search_logs_warning_when_fts_index_absent(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AUD-TEST-2: se por algum motivo o índice FTS não foi criado (ex.:
        adapter novo sem ensure_fts_index() chamado ainda), a falha da busca
        lexical NÃO pode ser silenciosa — precisa logar explicitamente para
        que o degrade-to-dense-only seja observável em produção."""
        store = LanceVectorStore(tmp_path, embedding_dim=_DIM)
        store.upsert([_make_indexed("c1", content="conteúdo sem índice fts")])
        # Propositalmente NÃO chama store.ensure_fts_index().

        with caplog.at_level("WARNING"):
            results = store.hybrid_search(tuple([0.1] * _DIM), "conteudo", top_n=5)

        assert len(results) >= 1  # ainda funciona via dense (degradação, não crash)
        assert any(
            "fts" in record.message.lower() or "hybrid_search_fts_unavailable" in record.message
            for record in caplog.records
        )
