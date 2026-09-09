import os
import json
import uuid
from typing import List, Dict, Any
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DB_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/clipmaker_db")

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(dsn=DB_URL, min_size=1, max_size=10)
    return _pool

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
    project_id = str(uuid.uuid4())
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO projects (id, userId, title, sourceUrl, sourceFileKey, durationSec, status) VALUES ($1, $2, $3, $4, $5, $6, $7)",
            project_id, user_id, title, source_url, source_file_key, duration_sec, 'PENDING'
        )
    return project_id

async def update_project_status(project_id: str, status: str, error_message: str = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE projects SET status = $1, errorMessage = $2 WHERE id = $3",
            status, error_message, project_id
        )

async def get_project_with_clips(project_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        project_row = await conn.fetchrow("SELECT * FROM projects WHERE id = $1", project_id)
        if not project_row:
            return None
        
        project = dict(project_row)
        
        clips = await conn.fetch("SELECT * FROM clips WHERE projectId = $1", project_id)
        project['clips'] = [dict(c) for c in clips]
            
        return project

async def save_project_results(project_id: str, clips_data: List[Dict[str, Any]]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for clip in clips_data:
                clip_id = clip.get('id', str(uuid.uuid4()))
                await conn.execute(
                    """INSERT INTO clips (id, projectId, title, hookReason, startTime, endTime, durationSec, viralScore, renderedUrl, status) 
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                    clip_id, project_id, clip['title'], clip['hookReason'], 0.0, 0.0, 
                    float(str(clip['duration']).replace(':', '.')), # simplified
                    clip['viralScore'], clip['id'], 'COMPLETED'
                )
            await conn.execute("UPDATE projects SET status = 'READY' WHERE id = $1", project_id)
