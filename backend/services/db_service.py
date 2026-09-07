import aiosqlite
import os
import json
import uuid
from typing import List, Dict, Any

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'dev.db')

async def create_user_safe(email: str, password_hash: str, name: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Check if user exists
        async with db.execute("SELECT id FROM users WHERE email = ?", (email,)) as cursor:
            user = await cursor.fetchone()
            if user:
                return dict(user)
        
        user_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO users (id, email, passwordHash, name) VALUES (?, ?, ?, ?)",
            (user_id, email, password_hash, name)
        )
        await db.commit()
        return {"id": user_id, "email": email, "name": name}

async def get_user_by_email(email: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE email = ?", (email,)) as cursor:
            user = await cursor.fetchone()
            return dict(user) if user else None

async def create_project(user_id: str, title: str, source_file_key: str, duration_sec: float, source_url: str = None):
    project_id = str(uuid.uuid4())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO projects (id, userId, title, sourceUrl, sourceFileKey, durationSec, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, user_id, title, source_url, source_file_key, duration_sec, 'PENDING')
        )
        await db.commit()
    return project_id

async def update_project_status(project_id: str, status: str, error_message: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE projects SET status = ?, errorMessage = ? WHERE id = ?",
            (status, error_message, project_id)
        )
        await db.commit()

async def get_project_with_clips(project_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM projects WHERE id = ?", (project_id,)) as cursor:
            project_row = await cursor.fetchone()
            if not project_row:
                return None
            
            project = dict(project_row)
            
            async with db.execute("SELECT * FROM clips WHERE projectId = ?", (project_id,)) as clip_cursor:
                clips = await clip_cursor.fetchall()
                project['clips'] = [dict(c) for c in clips]
                
            return project

async def save_project_results(project_id: str, clips_data: List[Dict[str, Any]]):
    async with aiosqlite.connect(DB_PATH) as db:
        for clip in clips_data:
            clip_id = clip.get('id', str(uuid.uuid4()))
            await db.execute(
                """INSERT INTO clips (id, projectId, title, hookReason, startTime, endTime, durationSec, viralScore, renderedUrl, status) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (clip_id, project_id, clip['title'], clip['hookReason'], 0.0, 0.0, 
                 float(clip['duration'].replace(':', '.')), # simplified
                 clip['viralScore'], clip['id'], 'COMPLETED')
            )
        await db.execute("UPDATE projects SET status = 'READY' WHERE id = ?", (project_id,))
        await db.commit()
