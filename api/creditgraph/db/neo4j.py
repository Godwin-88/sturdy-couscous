"""Neo4j driver lifecycle and helpers (async facade over the sync 4.x driver).

GraphAlpha's api container pins ``neo4j <5.0`` because ``gqlalchemy`` requires
``neo4j>=4.4.3,<5.0.0``. The CreditGraph services were written against the
neo4j **5.x async** API (``AsyncGraphDatabase``). Rather than force a driver
upgrade that would break GraphAlpha's knowledge-graph stack, this module
exposes the same async surface the ported services expect
(``async with driver.session()`` → ``await sess.run()`` →
``await cursor.single()`` / ``async for row``) by running the sync driver's
blocking calls inside a thread pool via :func:`asyncio.to_thread`.

Interface parity target (attest ``backend/app/db/neo4j.py``):
    - ``init_neo4j() / close_neo4j() / get_driver()``
    - driver: ``verify_connectivity()`` (async), ``session()`` (async CM)
    - session: ``run(query, params)`` (async) → result
    - result: ``single()`` (async), async iteration
"""

import asyncio
import logging
from typing import Any, AsyncIterator, Optional

from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


class _AsyncResult:
    """Async wrapper over the sync ``neo4j.Result``."""

    def __init__(self, result: Any):
        self._r = result

    async def single(self) -> Any | None:
        return await asyncio.to_thread(self._r.single)

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._aiter()

    async def _aiter(self) -> AsyncIterator[Any]:
        # neo4j 4.x sync ``Result`` (probed live): has ``data()`` and ``__iter__``
        # (a generator) but NOT ``records()`` and NOT ``__next__``. So materialise
        # via ``data()`` when present (returns list[dict]), otherwise fall back to
        # ``list(result)`` (works for both the real driver and test fakes).
        r = self._r
        if hasattr(r, "data") and callable(r.data):
            rows = await asyncio.to_thread(r.data)
            for row in rows:
                yield row
            return
        rows = await asyncio.to_thread(list, r)
        for row in rows:
            yield row


class _AsyncTransaction:
    """Async wrapper over the sync ``neo4j.Transaction`` (via to_thread)."""

    def __init__(self, tx: Any):
        self._t = tx

    async def run(self, query: str, parameters: Optional[dict] = None) -> _AsyncResult:
        params = parameters or {}
        # Pass params POSITIONALLY: the neo4j 4.x driver signature is
        # run(query, parameters=None, **kwparameters). Unpacking with ** would
        # collide when a cypher parameter is itself named "parameters"
        # (e.g. RiskObservation SET r.parameters = $parameters).
        result = await asyncio.to_thread(self._t.run, query, params)
        return _AsyncResult(result)

    async def commit(self) -> None:
        await asyncio.to_thread(self._t.commit)

    async def rollback(self) -> None:
        await asyncio.to_thread(self._t.rollback)

    async def close(self) -> None:
        await asyncio.to_thread(self._t.close)

    async def __aenter__(self) -> "_AsyncTransaction":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if exc_type is not None:
            try:
                await self.rollback()
            except Exception:
                pass
        else:
            try:
                await self.commit()
            except Exception:
                try:
                    await self.rollback()
                except Exception:
                    pass


class _AsyncSession:
    """Async wrapper over the sync ``neo4j.Session``."""

    def __init__(self, session: Any):
        self._s = session

    async def run(self, query: str, parameters: Optional[dict] = None) -> _AsyncResult:
        params = parameters or {}
        # Positional params (see _AsyncTransaction.run comment — avoids the
        # named-parameter collision when a cypher param is called "parameters").
        result = await asyncio.to_thread(self._s.run, query, params)
        return _AsyncResult(result)

    async def begin_transaction(self) -> _AsyncTransaction:
        tx = await asyncio.to_thread(self._s.begin_transaction)
        return _AsyncTransaction(tx)

    async def _close(self) -> None:
        await asyncio.to_thread(self._s.close)

    async def __aenter__(self) -> "_AsyncSession":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self._close()


class _AsyncDriver:
    """Async facade exposing the small driver surface the services consume."""

    def __init__(self, driver: Any):
        self._d = driver

    async def verify_connectivity(self) -> None:
        await asyncio.to_thread(self._d.verify_connectivity)

    def session(self) -> _AsyncSession:
        return _AsyncSession(self._d.session())

    async def close(self) -> None:
        await asyncio.to_thread(self._d.close)


_driver: _AsyncDriver | None = None


async def init_neo4j() -> None:
    """Create and verify the Neo4j driver (sync driver behind an async facade)."""
    global _driver
    from creditgraph.core.config import settings

    _driver = _AsyncDriver(
        GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    )
    await _driver.verify_connectivity()
    logger.info("CreditGraph Neo4j connected at %s", settings.neo4j_uri)


async def close_neo4j() -> None:
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


def get_driver() -> _AsyncDriver:
    if _driver is None:
        raise RuntimeError("Neo4j driver not initialized")
    return _driver