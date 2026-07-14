from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

import pytest

from rag_maker.adapters.driven.lancedb.vector_store import LanceVectorStore
from rag_maker.adapters.driven.loaders import loader_for
from rag_maker.application.config import AppConfig
from rag_maker.application.ingest_use_case import IngestUseCase
from rag_maker.application.query_use_case import QueryUseCase
from rag_maker.domain.models import QueryResult, RankedChunk, RetrievedChunk

CORPUS_MINI = Path(__file__).parent.parent / "fixtures" / "corpus_mini"
_DIM = 4


# ── Fakes ─────────────────────────────────────────────────────────────────────


class _FakeEmbedder:
    @property
    def dim(self) -> int:
        return _DIM

    def embed(self, text: str) -> tuple[float, ...]:
        seed = sum(ord(c) for c in text[:10]) % 100
        return tuple(float(seed + i) / 100.0 for i in range(_DIM))

    def embed_batch(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self.embed(t) for t in texts]


class _FakeReranker:
    """Reranker determinístico: score = comprimento do conteúdo (normalizado)."""

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        top_k: int,
    ) -> list[RankedChunk]:
        scored = sorted(chunks, key=lambda c: len(c.chunk.content), reverse=True)
        return [
            RankedChunk(
                chunk=rc.chunk,
                rerank_score=float(len(rc.chunk.content)),
                rrf_score=rc.rrf_score,
            )
            for rc in scored[:top_k]
        ]


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "db"
    p.mkdir()
    return p


@pytest.fixture()
def cfg(db_path: Path) -> AppConfig:
    return AppConfig.model_validate(
        {
            "paths": {"db_dir": str(db_path)},
            "retrieval": {"coarse_top_n": 50, "rerank_top_k": 3},
        }
    )


@pytest.fixture()
def populated_store(db_path: Path, cfg: AppConfig) -> LanceVectorStore:
    store = LanceVectorStore(db_path=db_path, embedding_dim=_DIM)
    embedder = _FakeEmbedder()
    uc = IngestUseCase(embedder=embedder, store=store, loader_for=loader_for, config=cfg)
    uc.ingest_incremental(CORPUS_MINI)
    return store


@pytest.fixture()
def query_uc(populated_store: LanceVectorStore, cfg: AppConfig) -> QueryUseCase:
    return QueryUseCase(
        embedder=_FakeEmbedder(),
        store=populated_store,
        reranker=_FakeReranker(),
        config=cfg,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration()
def test_answer_returns_query_result(query_uc: QueryUseCase) -> None:
    result = query_uc.answer("filosofia da mente")
    assert result.query == "filosofia da mente"
    assert len(result.ranked_chunks) > 0
    assert result.latency_ms > 0


@pytest.mark.integration()
def test_answer_respects_top_k(query_uc: QueryUseCase) -> None:
    result = query_uc.answer("texto", top_k=2)
    assert len(result.ranked_chunks) <= 2


@pytest.mark.integration()
def test_rerank_scores_are_non_increasing(query_uc: QueryUseCase) -> None:
    result = query_uc.answer("conhecimento", top_k=3)
    scores = [c.rerank_score for c in result.ranked_chunks]
    assert scores == sorted(scores, reverse=True), f"scores não decrescentes: {scores}"


@pytest.mark.integration()
def test_answer_empty_store_returns_empty(db_path: Path, cfg: AppConfig) -> None:
    store = LanceVectorStore(db_path=db_path, embedding_dim=_DIM)
    uc = QueryUseCase(
        embedder=_FakeEmbedder(),
        store=store,
        reranker=_FakeReranker(),
        config=cfg,
    )
    result = uc.answer("qualquer coisa")
    assert result.ranked_chunks == ()


# ── Canário: alpha é no-op reservado (F12.28 / AUD-TEST-7) ─────────────────────
#
# `QueryUseCase.answer(alpha=...)` documenta o parâmetro como "reservado para
# uso futuro na store" (query_use_case.py) mas HOJE não repassa `alpha` para
# `store.hybrid_search` de forma alguma. Comparar apenas chunk_ids/scores da
# saída final não detectaria isso: com o `_FakeReranker` atual (resorta 100%
# por len(content), e `coarse_top_n` >> corpus, então nada é cortado no
# estágio grosseiro) a saída final é insensível a quase qualquer mudança no
# estágio de retrieval — um teste que só olhasse a saída seria um canário
# falso (ficaria verde mesmo se alpha começasse a ser implementado errado,
# ou continuaria verde para sempre sem nunca detectar o no-op).
#
# O invariante honesto e verificável hoje é: os ARGUMENTOS recebidos por
# `hybrid_search` não variam com `alpha`. Espionamos a chamada real via
# `unittest.mock.patch.object(..., side_effect=...)` (wraps a chamada real —
# não é fake-de-tudo, o LanceDB real ainda roda) e comparamos os args
# capturados entre duas chamadas com alpha nos extremos (0.1 e 0.9).


def _make_hybrid_search_spy(
    store: LanceVectorStore,
    captured: list[tuple[tuple[float, ...], str, int]],
) -> Callable[[tuple[float, ...], str, int], list[RetrievedChunk]]:
    """Wrapper que registra os args recebidos e delega à busca real."""

    def _spy(vector: tuple[float, ...], text: str, top_n: int) -> list[RetrievedChunk]:
        captured.append((vector, text, top_n))
        return LanceVectorStore.hybrid_search(store, vector, text, top_n)

    return _spy


@pytest.mark.integration()
def test_answer_alpha_is_not_propagated_to_retrieval(
    query_uc: QueryUseCase, populated_store: LanceVectorStore
) -> None:
    """Pina que `alpha` é no-op reservado — não altera a chamada a `hybrid_search`.

    Quando alpha for implementado (fiado ao retrieval — ex.: a store passa a
    receber um peso denso/esparso, ou o use case decide a busca de acordo com
    alpha), este teste QUEBRA (os args capturados nas duas chamadas deixarão
    de ser idênticos) e DEVE ser substituído por um teste de delta:
    `answer(alpha=0.0)` (puro sparse) vs `answer(alpha=1.0)` (puro dense)
    devolvendo `ranked_chunks` observavelmente diferentes.
    """
    captured: list[tuple[tuple[float, ...], str, int]] = []
    spy = _make_hybrid_search_spy(populated_store, captured)
    with patch.object(populated_store, "hybrid_search", side_effect=spy):
        query_uc.answer("filosofia da mente", alpha=0.1)
        query_uc.answer("filosofia da mente", alpha=0.9)

    assert len(captured) == 2, "hybrid_search deveria ter sido chamado exatamente 2x"
    assert captured[0] == captured[1], (
        "alpha alterou os argumentos passados a hybrid_search — o no-op "
        "documentado deixou de valer; SUBSTITUA este teste por um teste de "
        "delta (alpha=0.0 puro sparse vs alpha=1.0 puro dense) conforme a "
        "docstring."
    )


class _AlphaPropagatingQueryUseCase(QueryUseCase):
    """Mutante usado SÓ para provar que o canário acima é real.

    Simula uma implementação futura hipotética que passa `alpha` adiante
    fazendo-o influenciar o `top_n` requisitado ao retrieval (uma forma
    plausível de "fiar" alpha ao retrieval sem mudar a assinatura do port).
    Não representa a implementação real esperada — é só um mutante para
    mutation testing manual desta suíte.
    """

    def answer(
        self,
        query: str,
        top_k: int | None = None,
        alpha: float | None = None,
    ) -> QueryResult:
        t0 = time.monotonic()
        k = top_k if top_k is not None else self._config.retrieval.rerank_top_k
        coarse_n = self._config.retrieval.coarse_top_n
        mutated_top_n = coarse_n + int((alpha or 0.0) * 10)

        query_vector = self._embedder.embed(query)
        retrieved = self._store.hybrid_search(query_vector, query, mutated_top_n)
        ranked = self._reranker.rerank(query, retrieved, k)

        return QueryResult(
            query=query,
            ranked_chunks=tuple(ranked),
            latency_ms=(time.monotonic() - t0) * 1000,
        )


@pytest.mark.integration()
def test_canary_would_fail_if_alpha_were_propagated(
    populated_store: LanceVectorStore, cfg: AppConfig
) -> None:
    """Mutation test manual: prova que o canário acima detectaria propagação.

    Roda a MESMA técnica de captura de argumentos contra o mutante
    `_AlphaPropagatingQueryUseCase` (que propositalmente varia `top_n`
    conforme `alpha`) e afirma que os args capturados DIVERGEM entre
    `alpha=0.1` e `alpha=0.9`. Se este teste falhasse, seria a técnica de
    captura em si que estaria quebrada — e o teste anterior seria,
    novamente, um canário falso.
    """
    mutant = _AlphaPropagatingQueryUseCase(
        embedder=_FakeEmbedder(),
        store=populated_store,
        reranker=_FakeReranker(),
        config=cfg,
    )
    captured: list[tuple[tuple[float, ...], str, int]] = []
    spy = _make_hybrid_search_spy(populated_store, captured)
    with patch.object(populated_store, "hybrid_search", side_effect=spy):
        mutant.answer("filosofia da mente", alpha=0.1)
        mutant.answer("filosofia da mente", alpha=0.9)

    assert len(captured) == 2
    assert captured[0] != captured[1], (
        "o mutante (alpha propagado ao top_n) deveria produzir args "
        "distintos entre alpha=0.1 e alpha=0.9 — se isso falhar, a técnica "
        "de captura usada em test_answer_alpha_is_not_propagated_to_retrieval "
        "não discrimina propagação de alpha, e aquele teste é um canário "
        "falso."
    )
