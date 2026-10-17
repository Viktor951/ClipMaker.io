import os
import sys
import re
import json
import uuid
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from pathlib import Path

from backend.app.core.config import settings

logger = logging.getLogger("clipmaker.db")

_backends: Dict[asyncio.AbstractEventLoop, Any] = {}


def _is_valid_uuid(val: Any) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


class PostgresTxWrapper:
    def __init__(self, conn):
        self._conn = conn

    async def execute(self, query: str, *args):
        return await self._conn.execute(query, *args)

    async def fetch(self, query: str, *args):
        rows = await self._conn.fetch(query, *args)
        return [{k.lower(): v for k, v in dict(r).items()} for r in rows]

    async def fetchrow(self, query: str, *args):
        row = await self._conn.fetchrow(query, *args)
        if not row:
            return None
        return {k.lower(): v for k, v in dict(row).items()}


class PostgresBackend:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.pool = None

    async def connect(self):
        import asyncpg
        if self.pool is None:
            self.pool = await asyncpg.create_pool(dsn=self.dsn, min_size=1, max_size=5)

    async def close(self):
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            if not row:
                return None
            return {k.lower(): v for k, v in dict(row).items()}

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [{k.lower(): v for k, v in dict(r).items()} for r in rows]

    async def execute(self, query: str, *args):
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)

    @asynccontextmanager
    async def transaction(self):
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                yield PostgresTxWrapper(conn)


class SqliteTxWrapper:
    def __init__(self, conn, convert_fn):
        self._conn = conn
        self._convert_query = convert_fn

    async def execute(self, query: str, *args):
        q = self._convert_query(query)
        await self._conn.execute(q, args)

    async def fetch(self, query: str, *args):
        q = self._convert_query(query)
        async with self._conn.execute(q, args) as cur:
            rows = await cur.fetchall()
            return [{k.lower(): r[k] for k in r.keys()} for r in rows]

    async def fetchrow(self, query: str, *args):
        q = self._convert_query(query)
        async with self._conn.execute(q, args) as cur:
            row = await cur.fetchone()
            if not row:
                return None
            return {k.lower(): row[k] for k in row.keys()}


class SqliteBackend:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn = None
        self._lock = asyncio.Lock()

    def _convert_query(self, query: str) -> str:
        # Converte placeholders $1, $2, ... para ? do SQLite
        return re.sub(r"\$\d+", "?", query)

    async def connect(self):
        import aiosqlite
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row
            await self._conn.execute("PRAGMA journal_mode=WAL;")
            await self._conn.execute("PRAGMA busy_timeout=10000;")
            await self._conn.execute("PRAGMA foreign_keys=ON;")
            async with self._conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'") as cur:
                has_users = await cur.fetchone()
            if not has_users:
                await self._init_schema()

    async def _init_schema(self):
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                passwordHash TEXT NOT NULL,
                name TEXT,
                credits INTEGER DEFAULT 60,
                createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                userId TEXT NOT NULL,
                title TEXT NOT NULL,
                sourceUrl TEXT,
                sourceFileKey TEXT NOT NULL,
                durationSec REAL NOT NULL,
                status TEXT DEFAULT 'PENDING',
                errorMessage TEXT,
                createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(userId) REFERENCES users(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS clips (
                id TEXT PRIMARY KEY,
                projectId TEXT NOT NULL,
                title TEXT NOT NULL,
                hookReason TEXT NOT NULL,
                startTime REAL NOT NULL,
                endTime REAL NOT NULL,
                durationSec REAL NOT NULL,
                viralScore INTEGER NOT NULL,
                aspectRatio TEXT DEFAULT '9:16',
                renderedUrl TEXT,
                status TEXT DEFAULT 'QUEUED',
                errorMessage TEXT,
                captionConfig TEXT,
                wordsJson TEXT,
                createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                updatedAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS transcriptions (
                id TEXT PRIMARY KEY,
                projectId TEXT UNIQUE NOT NULL,
                fullText TEXT NOT NULL,
                language TEXT DEFAULT 'pt',
                wordsJson TEXT NOT NULL,
                createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE CASCADE
            );
        """)
        try:
            await self._conn.execute("ALTER TABLE clips ADD COLUMN wordsJson TEXT;")
        except Exception:
            pass
        await self._conn.commit()

    async def close(self):
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        async with self._lock:
            q = self._convert_query(query)
            async with self._conn.execute(q, args) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                return {k.lower(): row[k] for k in row.keys()}

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        async with self._lock:
            q = self._convert_query(query)
            async with self._conn.execute(q, args) as cur:
                rows = await cur.fetchall()
                return [{k.lower(): r[k] for k in r.keys()} for r in rows]

    async def execute(self, query: str, *args):
        async with self._lock:
            q = self._convert_query(query)
            await self._conn.execute(q, args)
            await self._conn.commit()

    @asynccontextmanager
    async def transaction(self):
        async with self._lock:
            yield SqliteTxWrapper(self._conn, self._convert_query)
            await self._conn.commit()


async def get_backend():
    loop = asyncio.get_running_loop()
    if loop in _backends:
        return _backends[loop]

    db_url = settings.DATABASE_URL
    is_sqlite = db_url.startswith("sqlite") or db_url.endswith(".db")

    if not is_sqlite and (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        try:
            backend = PostgresBackend(db_url)
            await backend.connect()
            _backends[loop] = backend
            logger.info("Conexão com PostgreSQL estabelecida com sucesso.")
            return backend
        except Exception as e:
            if settings.ENVIRONMENT == "production" and os.getenv("STRICT_PROD") == "true":
                logger.error(f"Falha crítica ao conectar no PostgreSQL de produção: {e}")
                raise
            logger.warning(
                f"PostgreSQL indisponível ({e}). Alternando para SQLite local (dev.db) para desenvolvimento/testes."
            )

    dev_db_path = str(Path(__file__).resolve().parent.parent.parent.parent / "dev.db")
    backend = SqliteBackend(dev_db_path)
    await backend.connect()
    _backends[loop] = backend
    logger.info("Conexão com SQLite local (dev.db) estabelecida com sucesso.")
    return backend


async def init_pool():
    await get_backend()


async def close_pool():
    loop = asyncio.get_running_loop()
    if loop in _backends:
        await _backends[loop].close()
        del _backends[loop]


async def get_pool():
    return await get_backend()


async def create_user_safe(email: str, password_hash: str, name: str = None) -> Dict[str, Any]:
    db = await get_backend()
    user = await db.fetchrow("SELECT id FROM users WHERE email = $1", email)
    if user:
        return user

    user_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO users (id, email, passwordHash, name) VALUES ($1, $2, $3, $4)",
        user_id, email, password_hash, name
    )
    return {"id": user_id, "email": email, "name": name}


async def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    db = await get_backend()
    return await db.fetchrow("SELECT * FROM users WHERE email = $1", email)


async def create_project(
    user_id: str,
    title: str,
    source_file_key: str,
    duration_sec: float,
    source_url: str = None
) -> str:
    if not _is_valid_uuid(user_id):
        raise ValueError(f"user_id inválido: {user_id}")
    project_id = str(uuid.uuid4())
    db = await get_backend()
    await db.execute(
        "INSERT INTO projects (id, userId, title, sourceUrl, sourceFileKey, durationSec, status) VALUES ($1, $2, $3, $4, $5, $6, $7)",
        project_id, user_id, title, source_url, source_file_key, duration_sec, 'PENDING'
    )
    return project_id


async def get_user_projects(user_id: str) -> List[Dict[str, Any]]:
    if not _is_valid_uuid(user_id):
        return []
    db = await get_backend()
    rows = await db.fetch(
        "SELECT id, userId, title, sourceUrl, sourceFileKey, durationSec, status, errorMessage, createdAt, updatedAt FROM projects WHERE userId = $1 ORDER BY createdAt DESC",
        user_id
    )
    return rows


async def update_project_status(project_id: str, status: str, error_message: str = None):
    if not _is_valid_uuid(project_id):
        return
    db = await get_backend()
    await db.execute(
        "UPDATE projects SET status = $1, errorMessage = $2 WHERE id = $3",
        status, error_message, project_id
    )


async def get_project_with_clips(project_id: str) -> Optional[Dict[str, Any]]:
    if not _is_valid_uuid(project_id):
        return None
    db = await get_backend()
    project_row = await db.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
    if not project_row:
        return None

    project = dict(project_row)
    clips = await db.fetch("SELECT * FROM clips WHERE projectId = $1", project_id)
    clips_list = []
    for c in clips:
        cdict = dict(c)
        raw_words = cdict.get('wordsjson')
        if raw_words:
            try:
                cdict['words'] = json.loads(raw_words) if isinstance(raw_words, str) else raw_words
            except Exception:
                cdict['words'] = []
        else:
            cdict['words'] = []
        clips_list.append(cdict)

    project['clips'] = clips_list
    return project


async def save_project_results(project_id: str, clips_data: List[Dict[str, Any]]):
    if not _is_valid_uuid(project_id):
        return
    db = await get_backend()
    async with db.transaction() as tx:
        for clip in clips_data:
            raw_clip_id = clip.get('id')
            clip_id = str(raw_clip_id) if (raw_clip_id and _is_valid_uuid(raw_clip_id)) else str(uuid.uuid4())
            words_json = json.dumps(clip.get('words', []))
            start_t = float(clip.get('startTime', 0.0))
            end_t = float(clip.get('endTime', 0.0))
            dur_s = float(clip.get('durationSec', (end_t - start_t) if (end_t > start_t) else 0.0))
            await tx.execute(
                """INSERT INTO clips (id, projectId, title, hookReason, startTime, endTime, durationSec, viralScore, aspectRatio, renderedUrl, status, captionConfig, wordsJson) 
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)""",
                clip_id, project_id, clip['title'], clip['hookReason'], 
                start_t, end_t, dur_s,
                clip['viralScore'], clip.get('aspectRatio', '9:16'), clip['renderedUrl'], 'COMPLETED', 'Yellow', words_json
            )
        await tx.execute("UPDATE projects SET status = 'READY' WHERE id = $1", project_id)


async def get_clip(clip_id: str) -> Optional[Dict[str, Any]]:
    if not _is_valid_uuid(clip_id):
        return None
    db = await get_backend()
    clip = await db.fetchrow("SELECT * FROM clips WHERE id = $1", clip_id)
    if not clip:
        return None
    cdict = dict(clip)
    raw_words = cdict.get('wordsjson')
    if raw_words:
        try:
            cdict['words'] = json.loads(raw_words) if isinstance(raw_words, str) else raw_words
        except Exception:
            cdict['words'] = []
    else:
        cdict['words'] = []
    return cdict


async def update_clip_render_details(
    clip_id: str,
    words_json: str,
    caption_config: str,
    aspect_ratio: str,
    start_time: float = None,
    end_time: float = None
):
    if not _is_valid_uuid(clip_id):
        return
    db = await get_backend()
    if start_time is not None and end_time is not None:
        duration_sec = max(0.0, end_time - start_time)
        await db.execute(
            """UPDATE clips 
               SET wordsJson = $1, captionConfig = $2, aspectRatio = $3, startTime = $4, endTime = $5, durationSec = $6, updatedAt = CURRENT_TIMESTAMP 
               WHERE id = $7""",
            words_json, caption_config, aspect_ratio, start_time, end_time, duration_sec, clip_id
        )
    else:
        await db.execute(
            """UPDATE clips 
               SET wordsJson = $1, captionConfig = $2, aspectRatio = $3, updatedAt = CURRENT_TIMESTAMP 
               WHERE id = $4""",
            words_json, caption_config, aspect_ratio, clip_id
        )


async def update_clip_words_and_style(clip_id: str, words_json: str, caption_config: str):
    return await update_clip_render_details(clip_id, words_json, caption_config, "9:16")
