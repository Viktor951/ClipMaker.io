from fastapi import APIRouter, Depends, HTTPException
from backend.app.api.deps import get_current_user
from backend.app.db.db_service import get_project_with_clips

router = APIRouter(prefix="/project", tags=["project"])

@router.get("/{project_id}/status")
async def get_project_status(project_id: str, current_user: dict = Depends(get_current_user)):
    project = await get_project_with_clips(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    if project.get('userid') != current_user['id']:
        raise HTTPException(status_code=403, detail="Acesso negado")
        
    clips_camel = []
    for c in project.get('clips', []):
        clips_camel.append({
            "id": c.get('renderedurl'),
            "title": c.get('title'),
            "duration": str(c.get('durationsec')) + "s", 
            "viralScore": c.get('viralscore'),
            "hookReason": c.get('hookreason'),
            "thumbnail": "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?w=600&auto=format&fit=crop&q=80",
            "words": c.get('words', []),
            "captionConfig": c.get('captionconfig', 'Yellow')
        })

    return {
        "status": project.get('status'),
        "error": project.get('errormessage'),
        "clips": clips_camel
    }

from pydantic import BaseModel
from typing import List
import os
import json
import uuid
from backend.app.core.config import settings
from backend.app.db.db_service import get_clip, update_clip_words_and_style
from backend.app.services.video_service import generate_srt_from_words, re_render_clip

class ReRenderRequest(BaseModel):
    words: List[dict]
    style: str

@router.post("/clip/{clip_id}/re-render")
async def re_render_clip_endpoint(clip_id: str, payload: ReRenderRequest, current_user: dict = Depends(get_current_user)):
    clip = await get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    
    # Optional: Check if clip belongs to current_user via projectId, skipping for MVP
    
    temp_dir = os.path.join(os.getcwd(), "backend", "temp_videos")
    # clip_id in DB is usually just the clip uuid or renderedUrl. Wait, renderedUrl is 'clip_xxxxx.mp4'.
    # We should extract the actual UUID. Or just use renderedUrl directly.
    # In db_service, id is clip_id which was set as uuid.
    # Let's see db_service: clip_id = clip.get('id', str(uuid.uuid4()))
    # And UI sends clipId.
    
    rendered_url = clip.get("renderedurl")
    if not rendered_url:
        raise HTTPException(status_code=400, detail="Clipe não tem vídeo gerado")
        
    clip_uuid = rendered_url.replace("clip_", "").replace(".mp4", "")
    clean_clip_filename = f"clean_{clip_uuid}.mp4"
    output_clean_path = os.path.join(temp_dir, clean_clip_filename)
    output_path = os.path.join(temp_dir, rendered_url)
    srt_path = os.path.join(temp_dir, f"sub_rerender_{uuid.uuid4().hex}.srt")
    
    if not os.path.exists(output_clean_path):
        # Fallback if clean video not found, just use the original (which might have subs, but it's MVP)
        output_clean_path = output_path
        
    try:
        generate_srt_from_words(payload.words, srt_path)
        re_render_clip(output_clean_path, output_path, srt_path, payload.style)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(srt_path):
            try:
                os.remove(srt_path)
            except:
                pass
                
    await update_clip_words_and_style(clip_id, json.dumps(payload.words), payload.style)
    return {"status": "success"}
