from __future__ import annotations
import asyncpg
class Postgres:
    def __init__(self,dsn): self.dsn=dsn; self.pool=None
    async def connect(self): self.pool=await asyncpg.create_pool(self.dsn,min_size=1,max_size=5,command_timeout=180)
    async def close(self):
        if self.pool: await self.pool.close()
    async def execute(self,query,args):
        async with self.pool.acquire() as con:
            return [dict(r) for r in await con.fetch(query,*args)]
