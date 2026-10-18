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
                thumbnail_key TEXT,
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
            CREATE TABLE IF NOT EXISTS job_metrics (
                id TEXT PRIMARY KEY,
                projectId TEXT,
                videoDurationSec REAL NOT NULL,
                totalProcessingSec REAL NOT NULL,
                secPerMinute REAL NOT NULL,
                createdAt DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(projectId) REFERENCES projects(id) ON DELETE SET NULL
            );
        """)
        try:
            await self._conn.execute("ALTER TABLE clips ADD COLUMN wordsJson TEXT;")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE clips ADD COLUMN thumbnail_key TEXT;")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE clips ADD COLUMN face_center_x INTEGER;")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE projects ADD COLUMN ai_cuts_fallback INTEGER DEFAULT 0;")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE transcriptions ADD COLUMN userId TEXT;")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE transcriptions ADD COLUMN sourceUrl TEXT;")
        except Exception:
            pass
        try:
            await self._conn.execute("ALTER TABLE transcriptions ADD COLUMN fileHash TEXT;")
        except Exception:
            pass
        try:
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_user_status ON projects (userId, status);")
        except Exception:
            pass
        try:
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_status_created ON projects (status, createdAt);")
        except Exception:
            pass
        try:
            await self._conn.execute("CREATE INDEX IF NOT EXISTS idx_job_metrics_created_at ON job_metrics (createdAt DESC);")
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
    allow_sqlite = os.getenv("ALLOW_SQLITE_FALLBACK", "false").lower() in ("true", "1") and settings.ENVIRONMENT != "production"

    if not is_sqlite and (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        try:
            backend = PostgresBackend(db_url)
            await backend.connect()
            _backends[loop] = backend
            logger.info("Conexão com PostgreSQL estabelecida com sucesso.")
            return backend
        except Exception as e:
            if not allow_sqlite:
                logger.critical(f"Falha ao conectar no PostgreSQL: {e}")
                raise RuntimeError(
                    f"PostgreSQL indisponível ({e}). Em produção ou sem permissão explícita, "
                    f"a aplicação falha imediatamente. Para testes/dev local sem banco, use ALLOW_SQLITE_FALLBACK=true."
                ) from e
            logger.warning(
                f"[AVISO] PostgreSQL indisponível ({e}). ALLOW_SQLITE_FALLBACK=true ativado: utilizando SQLite local (dev.db)."
            )
    elif is_sqlite:
        if not allow_sqlite:
            raise RuntimeError(
                "DATABASE_URL SQLite configurada, mas ALLOW_SQLITE_FALLBACK não está habilitada. "
                "Defina ALLOW_SQLITE_FALLBACK=true para utilizar SQLite fora de produção."
            )
        logger.warning("[AVISO] ALLOW_SQLITE_FALLBACK=true ativado: utilizando SQLite local (dev.db).")
    else:
        if not allow_sqlite:
            raise RuntimeError(
                f"DATABASE_URL inválida ou não configurada ({db_url}). Configure o PostgreSQL ou ative ALLOW_SQLITE_FALLBACK=true."
            )

    dev_db_path = str(Path(__file__).resolve().parent.parent.parent.parent / "dev.db")
    backend = SqliteBackend(dev_db_path)
    await backend.connect()
    _backends[loop] = backend
    logger.warning("[AVISO] Conexão com SQLite local (dev.db) estabelecida com sucesso.")
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
    source_url: str = None,
    status: str = 'PENDING'
) -> str:
    if not _is_valid_uuid(user_id):
        raise ValueError(f"user_id inválido: {user_id}")
    project_id = str(uuid.uuid4())
    db = await get_backend()
    await db.execute(
        "INSERT INTO projects (id, userId, title, sourceUrl, sourceFileKey, durationSec, status) VALUES ($1, $2, $3, $4, $5, $6, $7)",
        project_id, user_id, title, source_url, source_file_key, duration_sec, status
    )
    return project_id


async def update_project_source(project_id: str, source_file_key: str, duration_sec: float, title: str = None):
    """Atualiza arquivo fonte e duração do projeto após download assíncrono."""
    if not _is_valid_uuid(project_id):
        return
    db = await get_backend()
    if title:
        await db.execute(
            "UPDATE projects SET sourceFileKey = $1, durationSec = $2, title = $3 WHERE id = $4",
            source_file_key, duration_sec, title, project_id
        )
    else:
        await db.execute(
            "UPDATE projects SET sourceFileKey = $1, durationSec = $2 WHERE id = $3",
            source_file_key, duration_sec, project_id
        )


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
    project['ai_cuts_fallback'] = bool(project.get('ai_cuts_fallback') or project.get('aicutsfallback') or False)
    clips = await db.fetch("SELECT * FROM clips WHERE projectId = $1", project_id)
    clips_list = []
    for c in clips:
        cdict = dict(c)
        cdict['thumbnail_key'] = cdict.get('thumbnail_key') or cdict.get('thumbnailkey') or ''
        cdict['face_center_x'] = cdict.get('face_center_x') if cdict.get('face_center_x') is not None else cdict.get('facecenterx')
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


async def save_single_clip(project_id: str, clip: Dict[str, Any]):
    """Salva um clipe incrementalmente assim que fica pronto no pipeline."""
    if not _is_valid_uuid(project_id):
        return
    db = await get_backend()
    raw_clip_id = clip.get('id')
    clip_id = str(raw_clip_id) if (raw_clip_id and _is_valid_uuid(raw_clip_id)) else str(uuid.uuid4())
    words_json = json.dumps(clip.get('words', []))
    start_t = float(clip.get('startTime', 0.0))
    end_t = float(clip.get('endTime', 0.0))
    dur_s = float(clip.get('durationSec', (end_t - start_t) if (end_t > start_t) else 0.0))
    thumb_key = clip.get('thumbnail_key') or clip.get('thumbnailKey') or ''
    face_cx = clip.get('face_center_x')
    if face_cx is not None:
        try:
            face_cx = int(face_cx)
        except (ValueError, TypeError):
            face_cx = None

    await db.execute(
        """INSERT INTO clips (id, projectId, title, hookReason, startTime, endTime, durationSec, viralScore, aspectRatio, renderedUrl, status, captionConfig, wordsJson, thumbnail_key, face_center_x) 
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
           ON CONFLICT (id) DO UPDATE SET
               renderedUrl = EXCLUDED.renderedUrl,
               thumbnail_key = EXCLUDED.thumbnail_key,
               face_center_x = EXCLUDED.face_center_x,
               status = 'COMPLETED',
               updatedAt = CURRENT_TIMESTAMP""",
        clip_id, project_id, clip.get('title', 'Clipe'), clip.get('hookReason', ''), 
        start_t, end_t, dur_s,
        clip.get('viralScore', 85), clip.get('aspectRatio', '9:16'), clip.get('renderedUrl', ''), 'COMPLETED', 'Yellow', words_json, thumb_key, face_cx
    )


async def set_project_ai_fallback(project_id: str, is_fallback: bool):
    """Registra no projeto se os cortes foram feitos via fallback matemático."""
    if not _is_valid_uuid(project_id):
        return
    db = await get_backend()
    await db.execute("UPDATE projects SET ai_cuts_fallback = $1 WHERE id = $2", is_fallback, project_id)


async def get_cached_transcription(user_id: Optional[str], source_url: Optional[str] = None, file_hash: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Busca transcrição já realizada para o mesmo vídeo do mesmo usuário."""
    if not user_id or not _is_valid_uuid(user_id):
        return None
    if not source_url and not file_hash:
        return None
    db = await get_backend()
    row = None
    if source_url and file_hash:
        row = await db.fetchrow(
            "SELECT * FROM transcriptions WHERE userId = $1 AND (sourceUrl = $2 OR fileHash = $3) ORDER BY createdAt DESC LIMIT 1",
            user_id, source_url, file_hash
        )
    elif source_url:
        row = await db.fetchrow(
            "SELECT * FROM transcriptions WHERE userId = $1 AND sourceUrl = $2 ORDER BY createdAt DESC LIMIT 1",
            user_id, source_url
        )
    elif file_hash:
        row = await db.fetchrow(
            "SELECT * FROM transcriptions WHERE userId = $1 AND fileHash = $2 ORDER BY createdAt DESC LIMIT 1",
            user_id, file_hash
        )

    if row:
        raw_words = row.get("wordsjson")
        segments = []
        if raw_words:
            try:
                segments = json.loads(raw_words) if isinstance(raw_words, str) else raw_words
            except Exception:
                segments = []
        return {
            "id": row.get("id"),
            "full_text": row.get("fulltext"),
            "language": row.get("language", "pt"),
            "segments": segments
        }
    return None


async def save_transcription(project_id: str, user_id: Optional[str], full_text: str, segments: list, language: str = "pt", source_url: Optional[str] = None, file_hash: Optional[str] = None):
    """Persiste a transcrição na tabela transcriptions para futuro reuso."""
    if not _is_valid_uuid(project_id):
        return
    db = await get_backend()
    words_json = json.dumps(segments)
    tid = str(uuid.uuid4())
    uid = str(user_id) if (user_id and _is_valid_uuid(user_id)) else None
    await db.execute(
        """INSERT INTO transcriptions (id, projectId, userId, fullText, language, wordsJson, sourceUrl, fileHash)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
           ON CONFLICT (projectId) DO UPDATE SET
               fullText = EXCLUDED.fullText,
               wordsJson = EXCLUDED.wordsJson,
               sourceUrl = EXCLUDED.sourceUrl,
               fileHash = EXCLUDED.fileHash""",
        tid, project_id, uid, full_text, language, words_json, source_url, file_hash
    )


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
            thumb_key = clip.get('thumbnail_key') or clip.get('thumbnailKey') or ''
            face_cx = clip.get('face_center_x')
            if face_cx is not None:
                try:
                    face_cx = int(face_cx)
                except (ValueError, TypeError):
                    face_cx = None
            await tx.execute(
                """INSERT INTO clips (id, projectId, title, hookReason, startTime, endTime, durationSec, viralScore, aspectRatio, renderedUrl, status, captionConfig, wordsJson, thumbnail_key, face_center_x) 
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                   ON CONFLICT (id) DO UPDATE SET
                       renderedUrl = EXCLUDED.renderedUrl,
                       thumbnail_key = EXCLUDED.thumbnail_key,
                       face_center_x = EXCLUDED.face_center_x,
                       status = 'COMPLETED',
                       updatedAt = CURRENT_TIMESTAMP""",
                clip_id, project_id, clip['title'], clip['hookReason'], 
                start_t, end_t, dur_s,
                clip['viralScore'], clip.get('aspectRatio', '9:16'), clip['renderedUrl'], 'COMPLETED', 'Yellow', words_json, thumb_key, face_cx
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
    cdict['face_center_x'] = cdict.get('face_center_x') if cdict.get('face_center_x') is not None else cdict.get('facecenterx')
    raw_words = cdict.get('wordsjson')
    if raw_words:
        try:
            cdict['words'] = json.loads(raw_words) if isinstance(raw_words, str) else raw_words
        except Exception:
            cdict['words'] = []
    else:
        cdict['words'] = []
    return cdict


async def update_clip_status(clip_id: str, status: str, error_message: str = None):
    if not _is_valid_uuid(clip_id):
        return
    db = await get_backend()
    await db.execute(
        "UPDATE clips SET status = $1, errorMessage = $2, updatedAt = CURRENT_TIMESTAMP WHERE id = $3",
        status, error_message, clip_id
    )


async def update_clip_render_details(
    clip_id: str,
    words_json: str,
    caption_config: str,
    aspect_ratio: str,
    start_time: float = None,
    end_time: float = None,
    status: str = 'COMPLETED',
    error_message: str = None
):
    if not _is_valid_uuid(clip_id):
        return
    db = await get_backend()
    if start_time is not None and end_time is not None:
        duration_sec = max(0.0, end_time - start_time)
        await db.execute(
            """UPDATE clips 
               SET wordsJson = $1, captionConfig = $2, aspectRatio = $3, startTime = $4, endTime = $5, durationSec = $6, status = $7, errorMessage = $8, updatedAt = CURRENT_TIMESTAMP 
               WHERE id = $9""",
            words_json, caption_config, aspect_ratio, start_time, end_time, duration_sec, status, error_message, clip_id
        )
    else:
        await db.execute(
            """UPDATE clips 
               SET wordsJson = $1, captionConfig = $2, aspectRatio = $3, status = $4, errorMessage = $5, updatedAt = CURRENT_TIMESTAMP 
               WHERE id = $6""",
            words_json, caption_config, aspect_ratio, status, error_message, clip_id
        )


async def update_clip_words_and_style(clip_id: str, words_json: str, caption_config: str):
    return await update_clip_render_details(clip_id, words_json, caption_config, "9:16")


async def get_clip_with_owner(clip_id: str) -> Optional[Dict[str, Any]]:
    """Consulta otimizada com JOIN para download/stream sem carregar projeto inteiro nem parsear JSON."""
    if not _is_valid_uuid(clip_id):
        return None
    db = await get_backend()
    row = await db.fetchrow(
        """SELECT c.id, c.projectId, c.renderedUrl, c.thumbnail_key, c.status, p.userId
           FROM clips c
           JOIN projects p ON c.projectId = p.id
           WHERE c.id = $1""",
        clip_id
    )
    if not row:
        return None
    cdict = dict(row)
    cdict['renderedUrl'] = cdict.get('renderedurl') or cdict.get('renderedUrl') or ''
    cdict['thumbnail_key'] = cdict.get('thumbnail_key') or cdict.get('thumbnailkey') or ''
    cdict['userId'] = cdict.get('userid') or cdict.get('userId') or ''
    return cdict


async def count_active_projects_by_user(user_id: str) -> int:
    """Conta projetos ativos em andamento para o usuário para limitar concorrência."""
    if not _is_valid_uuid(user_id):
        return 0
    db = await get_backend()
    row = await db.fetchrow(
        """SELECT COUNT(*) as count FROM projects 
           WHERE userId = $1 AND status IN ('PENDING', 'DOWNLOADING', 'TRANSCRIBING', 'ANALYZING', 'RENDERING')""",
        user_id
    )
    return int(row["count"]) if row else 0


async def get_project_queue_info(project_id: str) -> Dict[str, Any]:
    """Calcula posição na fila e estimativa de tempo baseada na média móvel de processamento."""
    if not _is_valid_uuid(project_id):
        return {"queue_position": 1, "estimated_time_sec": 30}
    db = await get_backend()
    proj = await db.fetchrow("SELECT createdAt, durationSec, status FROM projects WHERE id = $1", project_id)
    if not proj:
        return {"queue_position": 1, "estimated_time_sec": 30}
    
    status = proj.get("status")
    if status in ("READY", "COMPLETED", "FAILED"):
        return {"queue_position": 0, "estimated_time_sec": 0}

    created_at = proj.get("createdat") or proj.get("createdAt")
    row_pos = await db.fetchrow(
        """SELECT COUNT(*) as count FROM projects 
           WHERE status IN ('PENDING', 'DOWNLOADING', 'TRANSCRIBING', 'ANALYZING', 'RENDERING')
             AND createdAt < $1""",
        created_at
    )
    prior_count = int(row_pos["count"]) if row_pos else 0
    queue_position = prior_count + 1

    # Média móvel dos últimos 10 jobs (segundos de processamento por minuto de vídeo)
    row_avg = await db.fetchrow(
        """SELECT AVG(secPerMinute) as avg_sec FROM (
               SELECT secPerMinute FROM job_metrics ORDER BY createdAt DESC LIMIT 10
           ) as recent"""
    )
    avg_sec_per_min = float(row_avg["avg_sec"]) if (row_avg and row_avg.get("avg_sec") is not None) else 13.0
    video_dur_min = max(0.5, float(proj.get("durationsec") or 60.0) / 60.0)
    estimated_time = round(queue_position * (avg_sec_per_min * video_dur_min))

    return {
        "queue_position": queue_position,
        "estimated_time_sec": max(5, estimated_time)
    }


async def record_job_metric(project_id: str, duration_sec: float, total_elapsed_sec: float):
    """Registra tempo de execução para cálculo da média móvel de estimativa de fila."""
    if not _is_valid_uuid(project_id) or duration_sec <= 0:
        return
    db = await get_backend()
    mid = str(uuid.uuid4())
    video_min = duration_sec / 60.0
    sec_per_min = total_elapsed_sec / video_min
    await db.execute(
        """INSERT INTO job_metrics (id, projectId, videoDurationSec, totalProcessingSec, secPerMinute)
           VALUES ($1, $2, $3, $4, $5)""",
        mid, project_id, duration_sec, total_elapsed_sec, sec_per_min
    )

