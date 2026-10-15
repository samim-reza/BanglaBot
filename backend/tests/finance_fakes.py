"""An in-memory AsyncSession stand-in for the payments / finance tests (never a database)."""

from __future__ import annotations

from collections import deque
from typing import Any


class FakeResult:
    def __init__(self, rows: list[Any] | None = None, *, rowcount: int = 0) -> None:
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def all(self) -> list[Any]:
        return list(self._rows)

    def mappings(self) -> "FakeResult":
        return self


def _pk(row: Any) -> str:
    return str(getattr(row, "id", None) or getattr(row, "key", ""))


class FakeSession:
    """``get`` by (model, pk); queued answers for ``scalar`` / ``scalars`` / ``execute``.
    Also its own async context manager, so ``Factory(session)`` can stand in for a sessionmaker."""

    def __init__(self, *rows: Any, scalar: list[Any] | None = None, scalars: list[list[Any]] | None = None,
                 results: list[FakeResult] | None = None, fail_execute: bool = False) -> None:
        self.rows: dict[tuple[type, str], Any] = {}
        for row in rows:
            self.put(row)
        self.scalar_queue: deque[Any] = deque(scalar or [])
        self.scalars_queue: deque[list[Any]] = deque(scalars or [])
        self.results: deque[FakeResult] = deque(results or [])
        self.fail_execute = fail_execute
        self.added: list[Any] = []
        self.executed: list[Any] = []
        self.statements: list[Any] = []
        self.commits = 0
        self.rollbacks = 0

    def put(self, row: Any) -> None:
        self.rows[(type(row), _pk(row))] = row

    async def get(self, model: type, ident: Any, **_: Any) -> Any:
        return self.rows.get((model, str(ident)))

    def add(self, obj: Any) -> None:
        if hasattr(obj, "id") and getattr(obj, "id", None) is None:
            obj.id = f"new{len(self.added) + 1}"
        self.added.append(obj)
        if _pk(obj):
            self.put(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def refresh(self, obj: Any) -> None:
        return None

    async def scalar(self, stmt: Any) -> Any:
        self.statements.append(stmt)
        return self.scalar_queue.popleft() if self.scalar_queue else None

    async def scalars(self, stmt: Any) -> list[Any]:
        self.statements.append(stmt)
        return list(self.scalars_queue.popleft() if self.scalars_queue else [])

    async def execute(self, stmt: Any, params: Any = None) -> FakeResult:
        if self.fail_execute:
            raise ConnectionError("database unreachable")
        self.executed.append((stmt, params))
        return self.results.popleft() if self.results else FakeResult()

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class Factory:
    """``factory()`` → the same FakeSession (an async context manager)."""

    def __init__(self, session: FakeSession) -> None:
        self.session = session
        self.opened = 0

    def __call__(self) -> FakeSession:
        self.opened += 1
        return self.session


def db_dependency(session: FakeSession):
    async def _get_db():
        yield session

    return _get_db
