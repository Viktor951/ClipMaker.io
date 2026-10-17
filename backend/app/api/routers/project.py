import uuid
from typing import List, Optional, Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from backend.app.api.deps import get_current_user
from backend.app.db.db_service import (
    get_project_with_clips,
    get_clip,
    create_project,
    get_user_projects,
    update_clip_status
)
from backend.app.worker.worker import re_render_clip_task

router = APIRouter(tags=["project"])


class ProjectCreate(BaseModel):
    title: str = "Projeto Criado via API"
    source_url: Optional[str] = None
    duration_sec: float = 0.0


class WordItem(BaseModel):
    text: str
    start: float
    end: float
    highlighted: Optional[bool] = False


class ReRenderRequest(BaseModel):
    words: List[WordItem] = Field(default_factory=list, max_length=5000)
    style: Literal["Yellow", "Green", "White"] = "Yellow"
    start_time: Optional[float] = Field(default=None, ge=0.0)
    end_time: Optional[float] = Field(default=None, gt=0.0)
    aspect_ratio: Literal["9:16", "1:1", "16:9"] = "9:16"
    add_subtitles: bool = True
    quality: Literal["720p", "1080p"] = "1080p"

    @model_validator(mode="after")
    def validate_times(self):
        if self.start_time is not None and self.end_time is not None:
            if self.end_time <= self.start_time:
                raise ValueError("end_time deve ser estritamente maior que start_time")
        return self


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
        thumb_key = c.get("thumbnail_key") or c.get("thumbnailkey") or ""
        thumb_url = f"/api/videos/thumbnail/{c.get('id')}" if thumb_key else ""
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
            "thumbnail": thumb_url,
            "thumbnailKey": thumb_key,
            "status": c.get("status", "COMPLETED"),
            "words": c.get("words", []),
            "captionConfig": c.get("captionconfig", "Yellow")
        })

    return {
        "status": project.get("status"),
        "error": project.get("errormessage"),
        "title": project.get("title"),
        "clips": clips_list
    }


@router.get("/clip/{clip_id}/status")
async def get_clip_status(clip_id: str, current_user: dict = Depends(get_current_user)):
    clip = await get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")

    project = await get_project_with_clips(clip.get("projectid"))
    if not project or str(project.get("userid")) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Acesso negado")

    return {
        "status": clip.get("status", "COMPLETED"),
        "error": clip.get("errormessage"),
        "renderedUrl": clip.get("renderedurl"),
        "aspectRatio": clip.get("aspectratio"),
        "clipId": str(clip.get("id"))
    }


@router.post("/clip/{clip_id}/re-render")
async def re_render_clip_endpoint(clip_id: str, payload: ReRenderRequest, current_user: dict = Depends(get_current_user)):
    clip = await get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")

    project = await get_project_with_clips(clip.get("projectid"))
    if not project or str(project.get("userid")) != str(current_user["id"]):
        raise HTTPException(status_code=403, detail="Acesso negado")

    proj_dur = float(project.get("durationsec") or 0.0)
    if proj_dur > 0 and payload.end_time is not None:
        if payload.end_time > proj_dur + 2.0:
            raise HTTPException(status_code=400, detail="end_time excede a duração do vídeo original")

    await update_clip_status(clip_id, "QUEUED")
    re_render_clip_task(clip_id, payload.model_dump())
    return {"status": "processing", "clip_id": clip_id, "aspect_ratio": payload.aspect_ratio}
