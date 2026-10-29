import asyncpg
import contextlib
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
pool = None


async def init_pool():
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL)

async def close_pool():
    await pool.close()

@contextlib.asynccontextmanager
async def tenant_connection(tenantid: str):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT set_config('app.current_tenant', $1, true)", tenantid)
            yield conn