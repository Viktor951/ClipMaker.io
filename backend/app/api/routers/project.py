import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.app.api.deps import get_current_user
from backend.app.db.db_service import get_project_with_clips, get_clip, create_project, get_user_projects
from backend.app.worker.worker import re_render_clip_task

router = APIRouter(tags=["project"])


class ProjectCreate(BaseModel):
    title: str = "Projeto Criado via API"
    source_url: Optional[str] = None
    duration_sec: float = 0.0


class ReRenderRequest(BaseModel):
    words: List[dict] = Field(default_factory=list)
    style: str = "Yellow"
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    aspect_ratio: str = "9:16"
    add_subtitles: bool = True
    quality: str = "1080p"


@router.get("")
@router.get("/")
async def list_user_projects(current_user: dict = Depends(get_current_user)):
    projects = await get_user_projects(str(current_user["id"]))
    return {"status": "success", "projects": projects}


@router.post("")
@router.post("/")
async def create_new_project(payload: ProjectCreate = ProjectCreate(), current_user: dict = Depends(get_current_user)):
    safe_key = f"{uuid.uuid4()}.mp4"
    project_id = await create_project(
        user_id=str(current_user["id"]),
        title=payload.title,
        source_file_key=safe_key,
        duration_sec=payload.duration_sec,
        source_url=payload.source_url
    )
    return {"status": "success", "project_id": project_id}


@router.get("/{project_id}/status")
async def get_project_status(project_id: str, current_user: dict = Depends(get_current_user)):

    project = await get_project_with_clips(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")

    if str(project.get("userid")) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Acesso negado")

    clips_list = []
    for c in project.get("clips", []):
        clips_list.append({
            "id": c.get("renderedurl"),
            "clipId": str(c.get("id")),
            "title": c.get("title"),
            "duration": f"{c.get('durationsec')}s",
            "durationSec": c.get("durationsec"),
            "startTime": c.get("starttime", 0.0),
            "endTime": c.get("endtime", 0.0),
            "aspectRatio": c.get("aspectratio", "9:16"),
            "viralScore": c.get("viralscore"),
            "hookReason": c.get("hookreason"),
            "thumbnail": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80",
            "words": c.get("words", []),
            "captionConfig": c.get("captionconfig", "Yellow")
        })

    return {
        "status": project.get("status"),
        "error": project.get("errormessage"),
        "clips": clips_list
    }


@router.post("/clip/{clip_id}/re-render")
async def re_render_clip_endpoint(clip_id: str, payload: ReRenderRequest, current_user: dict = Depends(get_current_user)):
    clip = await get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")

    project = await get_project_with_clips(clip.get("projectid"))
    if not project or str(project.get("userid")) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Acesso negado")

    re_render_clip_task(clip_id, payload.model_dump())
    return {"status": "processing", "aspect_ratio": payload.aspect_ratio}
