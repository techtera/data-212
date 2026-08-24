"""Database connection pool and query helpers using asyncpg."""

import asyncio
import logging

import asyncpg

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None

SQL_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(64) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    display_name VARCHAR(64),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(128),
    job_type VARCHAR(16) NOT NULL CHECK (job_type IN ('eval', 'finetune')),
    status VARCHAR(16) NOT NULL DEFAULT 'uploading' CHECK (status IN ('uploading', 'running', 'done', 'error')),
    model_id VARCHAR(128) NOT NULL,
    dataset_id VARCHAR(64) NOT NULL,
    gcs_images_zip VARCHAR(512) NOT NULL,
    gcs_masks_zip VARCHAR(512) NOT NULL,
    mean_iou FLOAT,
    dice_score FLOAT,
    pixel_accuracy FLOAT,
    predictions JSONB DEFAULT '[]',
    artifacts JSONB DEFAULT '{}',
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    model_name VARCHAR(128) NOT NULL,
    category VARCHAR(32) NOT NULL,
    base_model VARCHAR(128) NOT NULL,
    checkpoint_path VARCHAR(512) NOT NULL,
    inference_script VARCHAR(512) NOT NULL,
    version INT DEFAULT 1,
    job_id UUID REFERENCES jobs(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sessions_token_hash ON sessions(token_hash);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_owner_id ON jobs(owner_id);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_user_models_user_id ON user_models(user_id);
"""


async def init_pool(dsn: str) -> None:
    """Initialize the connection pool and create tables. Retries on transient DNS failures."""
    global _pool
    for attempt in range(5):
        try:
            _pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10, statement_cache_size=0)
            async with _pool.acquire() as conn:
                await conn.execute(SQL_CREATE_TABLES)
                await conn.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS name VARCHAR(128);")
                await conn.execute("ALTER TABLE jobs ALTER COLUMN model_id TYPE VARCHAR(128);")
            return
        except OSError as e:
            logger.warning("DB connection attempt %d failed: %s", attempt + 1, e)
            if attempt < 4:
                await asyncio.sleep(3)
            else:
                raise


async def close_pool() -> None:
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


def get_pool() -> asyncpg.Pool:
    """Get the current connection pool. Raises if not initialized."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


async def fetch_one(query: str, *args) -> asyncpg.Record | None:
    """Execute a query and return the first row or None."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def fetch_all(query: str, *args) -> list[asyncpg.Record]:
    """Execute a query and return all rows."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def execute(query: str, *args) -> str:
    """Execute a query and return the status string."""
    pool = get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)
