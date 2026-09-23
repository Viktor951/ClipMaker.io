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
            "clipId": str(c.get('id')),
            "title": c.get('title'),
            "duration": str(c.get('durationsec')) + "s", 
            "durationSec": c.get('durationsec'),
            "startTime": c.get('starttime', 0.0),
            "endTime": c.get('endtime', 0.0),
            "aspectRatio": c.get('aspectratio', '9:16'),
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
import shutil
from backend.app.core.config import settings
from backend.app.db.db_service import get_clip, update_clip_render_details
from backend.app.services.video_service import generate_srt_from_words, re_render_clip
from backend.app.api.routers.video import TEMP_DIR

class ReRenderRequest(BaseModel):
    words: List[dict]
    style: str
    start_time: float | None = None
    end_time: float | None = None
    aspect_ratio: str = "9:16"
    add_subtitles: bool = True
    quality: str = "1080p"

@router.post("/clip/{clip_id}/re-render")
async def re_render_clip_endpoint(clip_id: str, payload: ReRenderRequest, current_user: dict = Depends(get_current_user)):
    clip = await get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clipe não encontrado")
    
    project = await get_project_with_clips(clip.get("projectid"))
    if not project:
        raise HTTPException(status_code=404, detail="Projeto não encontrado")
    
    temp_dir = str(TEMP_DIR)
    
    rendered_url = clip.get("renderedurl")
    if not rendered_url:
        raise HTTPException(status_code=400, detail="Clipe não tem vídeo gerado")
        
    clip_uuid = rendered_url.replace("clip_", "").replace(".mp4", "")
    clean_clip_filename = f"clean_{clip_uuid}.mp4"
    output_clean_path = os.path.join(temp_dir, clean_clip_filename)
    output_path = os.path.join(temp_dir, rendered_url)
    srt_path = os.path.join(temp_dir, f"sub_rerender_{uuid.uuid4().hex}.srt")
    source_filename = project.get("sourcefilekey", "")
    source_video_path = os.path.join(temp_dir, source_filename) if source_filename else ""
    
    # Timing
    current_start = float(clip.get("starttime") or 0.0)
    current_end = float(clip.get("endtime") or clip.get("durationsec") or 0.0)
    
    new_start = payload.start_time if payload.start_time is not None else current_start
    new_end = payload.end_time if payload.end_time is not None else current_end
    
    current_aspect = clip.get("aspectratio", "9:16")
    
    # Verifica se precisa de re-extração completa de enquadramento
    needs_full_render = False
    if payload.aspect_ratio != current_aspect:
        needs_full_render = True
    if abs(new_start - current_start) > 0.5 or abs(new_end - current_end) > 0.5:
        needs_full_render = True
        
    try:
        generate_srt_from_words(payload.words, srt_path)
        
        has_source = bool(source_video_path and os.path.exists(source_video_path))
        from backend.app.services.video_service import extract_and_crop_clip
        
        if needs_full_render or not os.path.exists(output_clean_path):
            if has_source:
                # 1. Extrai do vídeo original em resolução plena com a proporção escolhida
                extract_and_crop_clip(
                    source_video_path, output_clean_path, None, 
                    new_start, new_end, 
                    aspect_ratio=payload.aspect_ratio, 
                    add_subtitles=False,
                    style_name=payload.style,
                    quality=payload.quality
                )
            else:
                # Fallback: vídeo fonte original foi limpo anteriormente; reenquadra a partir do clipe limpo/atual
                fallback_source = output_clean_path if os.path.exists(output_clean_path) else output_path
                temp_clean = os.path.join(temp_dir, f"temp_clean_{uuid.uuid4().hex}.mp4")
                clip_duration = max(0.0, new_end - new_start)
                if clip_duration <= 0.0:
                    clip_duration = float(clip.get("durationsec") or 30.0)
                extract_and_crop_clip(
                    fallback_source, temp_clean, None, 
                    0.0, clip_duration, 
                    aspect_ratio=payload.aspect_ratio, 
                    add_subtitles=False,
                    style_name=payload.style,
                    quality=payload.quality
                )
                if os.path.exists(temp_clean):
                    shutil.move(temp_clean, output_clean_path)
            
            # Aplica legendas se habilitado, ou copia o vídeo limpo
            if payload.add_subtitles and os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
                re_render_clip(
                    output_clean_path, output_path, srt_path, payload.style, 
                    True, payload.quality, payload.aspect_ratio
                )
            else:
                shutil.copyfile(output_clean_path, output_path)
        else:
            # Re-render rápido (mesmo aspect ratio e trim, apenas alteração de estilo de legenda)
            re_render_clip(
                output_clean_path, output_path, srt_path, payload.style, 
                payload.add_subtitles, payload.quality, payload.aspect_ratio
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(srt_path):
            try:
                os.remove(srt_path)
            except:
                pass
                
    await update_clip_render_details(
        clip_id=clip_id,
        words_json=json.dumps(payload.words),
        caption_config=payload.style,
        aspect_ratio=payload.aspect_ratio,
        start_time=new_start,
        end_time=new_end
    )
    
    return {"status": "success", "aspect_ratio": payload.aspect_ratio}
