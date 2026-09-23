from __future__ import annotations

import asyncpg


def _split_sql_statements(query: str) -> list[str]:
    """Split PostgreSQL SQL on top-level semicolons.

    This deliberately handles quoted strings, quoted identifiers, line/block
    comments, and PostgreSQL dollar-quoted bodies so multi-command queries can
    be executed without changing the SQL copied from the n8n workflow.
    """
    statements: list[str] = []
    start = 0
    i = 0
    n = len(query)
    quote = None
    dollar_tag = None
    line_comment = False
    block_comment = False

    while i < n:
        ch = query[i]
        nxt = query[i + 1] if i + 1 < n else ""

        if line_comment:
            if ch in "\r\n":
                line_comment = False
            i += 1
            continue

        if block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                i += 2
            else:
                i += 1
            continue

        if dollar_tag is not None:
            if query.startswith(dollar_tag, i):
                i += len(dollar_tag)
                dollar_tag = None
            else:
                i += 1
            continue

        if quote == "'":
            if ch == "'":
                if nxt == "'":
                    i += 2
                    continue
                quote = None
            elif ch == "\\":
                i += 2
                continue
            i += 1
            continue

        if quote == '"':
            if ch == '"':
                if nxt == '"':
                    i += 2
                    continue
                quote = None
            i += 1
            continue

        if ch == "-" and nxt == "-":
            line_comment = True
            i += 2
            continue

        if ch == "/" and nxt == "*":
            block_comment = True
            i += 2
            continue

        if ch == "'":
            quote = "'"
            i += 1
            continue

        if ch == '"':
            quote = '"'
            i += 1
            continue

        if ch == "$":
            j = i + 1
            while j < n and (query[j].isalnum() or query[j] == "_"):
                j += 1
            if j < n and query[j] == "$":
                dollar_tag = query[i : j + 1]
                i = j + 1
                continue

        if ch == ";":
            statement = query[start:i].strip()
            if statement:
                statements.append(statement)
            start = i + 1

        i += 1

    tail = query[start:].strip()
    if tail:
        statements.append(tail)
    return statements


class Postgres:
    def __init__(self, dsn):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=1,
            max_size=5,
            command_timeout=180,
        )

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def execute(self, query, args):
        async with self.pool.acquire() as con:
            statements = _split_sql_statements(query)
            if not statements:
                return []

            # Keep the original single-statement fast path. asyncpg.fetch()
            # preserves rows for SELECT/RETURNING statements.
            if len(statements) == 1:
                return [dict(r) for r in await con.fetch(statements[0], *args)]

            # PostgreSQL's prepared-statement path rejects multiple commands.
            # Execute all preceding commands in order, then fetch rows from the
            # final command when it returns rows. Everything runs in one
            # transaction so the multi-command behavior remains atomic.
            async with con.transaction():
                for statement in statements[:-1]:
                    await con.execute(statement, *args)

                final = statements[-1]
                try:
                    rows = await con.fetch(final, *args)
                except asyncpg.exceptions.PostgresError as exc:
                    # Commands such as INSERT/UPDATE/DELETE without RETURNING
                    # have no row result. Execute them normally if fetch reports
                    # that no result set exists; re-raise all other SQL errors.
                    message = str(exc).lower()
                    if "does not return rows" not in message and "cannot insert multiple commands" not in message:
                        raise
                    await con.execute(final, *args)
                    return []

                return [dict(r) for r in rows]
