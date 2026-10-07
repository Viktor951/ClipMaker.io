import os
import json
import uuid
from typing import List, Dict, Any, Optional
import asyncio
import asyncpg
from backend.app.core.config import settings

_pools = {}


def _is_valid_uuid(val: Any) -> bool:
    try:
        uuid.UUID(str(val))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


async def init_pool():
    loop = asyncio.get_running_loop()
    if loop not in _pools:
        _pools[loop] = await asyncpg.create_pool(dsn=settings.DATABASE_URL, min_size=1, max_size=5)


async def close_pool():
    loop = asyncio.get_running_loop()
    if loop in _pools:
        await _pools[loop].close()
        del _pools[loop]


async def get_pool():
    loop = asyncio.get_running_loop()
    if loop not in _pools:
        await init_pool()
    return _pools[loop]


async def create_user_safe(email: str, password_hash: str, name: str = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id FROM users WHERE email = $1", email)
        if user:
            return dict(user)

        user_id = str(uuid.uuid4())
        await conn.execute(
            "INSERT INTO users (id, email, passwordHash, name) VALUES ($1, $2, $3, $4)",
            user_id, email, password_hash, name
        )
        return {"id": user_id, "email": email, "name": name}


async def get_user_by_email(email: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
        return dict(user) if user else None


async def create_project(user_id: str, title: str, source_file_key: str, duration_sec: float, source_url: str = None):
    if not _is_valid_uuid(user_id):
        raise ValueError(f"user_id inválido: {user_id}")
    project_id = str(uuid.uuid4())
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, userId, title, sourceUrl, sourceFileKey, durationSec, status) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            project_id, user_id, title, source_url, source_file_key, duration_sec, 'PENDING'
        )
    return project_id


async def get_user_projects(user_id: str):
    if not _is_valid_uuid(user_id):
        return []
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, userId, title, sourceUrl, sourceFileKey, durationSec, status, errorMessage, createdAt, updatedAt FROM projects WHERE userId = $1 ORDER BY createdAt DESC",
            user_id
        )
        return [dict(r) for r in rows]


async def update_project_status(project_id: str, status: str, error_message: str = None):
    if not _is_valid_uuid(project_id):
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE projects SET status = $1, errorMessage = $2 WHERE id = $3",
            status, error_message, project_id
        )


async def get_project_with_clips(project_id: str):
    if not _is_valid_uuid(project_id):
        return None
    pool = await get_pool()
    async with pool.acquire() as conn:
        project_row = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
        if not project_row:
            return None

        project = dict(project_row)

        clips = await conn.fetch("SELECT * FROM clips WHERE projectId = $1", project_id)
        clips_list = []
        for c in clips:
            cdict = dict(c)
            cdict['words'] = json.loads(cdict['wordsjson']) if cdict.get('wordsjson') else []
            clips_list.append(cdict)

        project['clips'] = clips_list
        return project


async def save_project_results(project_id: str, clips_data: List[Dict[str, Any]]):
    if not _is_valid_uuid(project_id):
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for clip in clips_data:
                raw_clip_id = clip.get('id')
                clip_id = str(raw_clip_id) if (raw_clip_id and _is_valid_uuid(raw_clip_id)) else str(uuid.uuid4())
                words_json = json.dumps(clip.get('words', []))
                start_t = float(clip.get('startTime', 0.0))
                end_t = float(clip.get('endTime', 0.0))
                dur_s = float(clip.get('durationSec', (end_t - start_t) if (end_t > start_t) else 0.0))
                await conn.execute(
                    """INSERT INTO clips (id, projectId, title, hookReason, startTime, endTime, durationSec, viralScore, aspectRatio, renderedUrl, status, captionConfig, wordsJson) 
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)""",
                    clip_id, project_id, clip['title'], clip['hookReason'], 
                    start_t, end_t, dur_s,
                    clip['viralScore'], clip.get('aspectRatio', '9:16'), clip['renderedUrl'], 'COMPLETED', 'Yellow', words_json
                )
            await conn.execute("UPDATE projects SET status = 'READY' WHERE id = $1", project_id)


async def get_clip(clip_id: str):
    if not _is_valid_uuid(clip_id):
        return None
    pool = await get_pool()
    async with pool.acquire() as conn:
        clip = await conn.fetchrow("SELECT * FROM clips WHERE id = $1", clip_id)
        if not clip:
            return None
        cdict = dict(clip)
        cdict['words'] = json.loads(cdict['wordsjson']) if cdict.get('wordsjson') else []
        return cdict


async def update_clip_render_details(clip_id: str, words_json: str, caption_config: str, aspect_ratio: str, start_time: float = None, end_time: float = None):
    if not _is_valid_uuid(clip_id):
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        if start_time is not None and end_time is not None:
            duration_sec = max(0.0, end_time - start_time)
            await conn.execute(
                """UPDATE clips 
                   SET wordsJson = $1, captionConfig = $2, aspectRatio = $3, startTime = $4, endTime = $5, durationSec = $6, updatedAt = CURRENT_TIMESTAMP 
                   WHERE id = $7""",
                words_json, caption_config, aspect_ratio, start_time, end_time, duration_sec, clip_id
            )
        else:
            await conn.execute(
                """UPDATE clips 
                   SET wordsJson = $1, captionConfig = $2, aspectRatio = $3, updatedAt = CURRENT_TIMESTAMP 
                   WHERE id = $4""",
                words_json, caption_config, aspect_ratio, clip_id
            )


async def update_clip_words_and_style(clip_id: str, words_json: str, caption_config: str):
    return await update_clip_render_details(clip_id, words_json, caption_config, "9:16")
