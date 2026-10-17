#!/usr/bin/env python3
"""
ClipMaker.io Pipeline Benchmark CLI
Executa process_video_full_pipeline de forma direta (project_id=None, sem banco)
e gera uma tabela com o tempo detalhado de cada fase e o tempo total.
"""

import os
import sys
import time
import shutil
import tempfile
import argparse
from pathlib import Path

# Adiciona a raiz do projeto ao sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.timing import get_stage_timings, reset_stage_timings
from backend.app.services.engine_service import process_video_full_pipeline
from backend.app.services.video_service import get_video_info, is_nvenc_available


def run_benchmark(video_path: str, skip_llm: bool = False, aspect_ratio: str = "9:16", keep_output: bool = False):
    abs_video = os.path.abspath(video_path)
    if not os.path.exists(abs_video):
        print(f"\n[ERRO] Arquivo de vídeo não encontrado: {abs_video}")
        sys.exit(1)

    file_size_mb = os.path.getsize(abs_video) / (1024 * 1024)
    print("=" * 80)
    print("                 CLIPMAKER.IO — PIPELINE BENCHMARK")
    print("=" * 80)
    print(f"Vídeo de entrada: {abs_video}")
    print(f"Tamanho do arquivo: {file_size_mb:.2f} MB")
    print(f"Aspect Ratio: {aspect_ratio}")
    print(f"Modo LLM: {'Fallback Matemático (--skip-llm)' if skip_llm else 'Gemini API Real'}")
    print(f"Aceleração NVENC detectada: {'SIM' if is_nvenc_available() else 'NÃO (CPU libx264)'}")

    try:
        w, h, duration = get_video_info(abs_video)
        print(f"Dimensões originais: {w}x{h} | Duração total: {duration:.1f}s ({duration/60:.2f} min)")
    except Exception as e:
        print(f"[AVISO] Não foi possível obter info prévia: {e}")
        duration = 0.0

    temp_dir = tempfile.mkdtemp(prefix="clipmaker_bench_")
    print(f"Diretório temporário: {temp_dir}")
    print("-" * 80)

    reset_stage_timings()
    t_start = time.perf_counter()

    try:
        clips = process_video_full_pipeline(
            input_path=abs_video,
            temp_dir=temp_dir,
            project_id=None,
            aspect_ratio=aspect_ratio,
            skip_llm=skip_llm,
        )
    except Exception as e:
        print(f"\n[FALHA NO BENCHMARK] O pipeline gerou uma exceção: {e}")
        import traceback
        traceback.print_exc()
        if not keep_output and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        sys.exit(1)

    t_total = time.perf_counter() - t_start
    raw_timings = get_stage_timings()

    # Agrupar tempos por categoria
    probe_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "probe")
    trans_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "transcription")
    llm_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "llm")
    face_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "face_tracking")
    render_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "render")
    sub_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "subtitles")

    clip_count = len(clips)
    sum_accounted = probe_time + trans_time + llm_time + face_time + render_time + sub_time
    overhead_time = max(0.0, t_total - sum_accounted)

    # Imprimir tabela formatada
    print("\n" + "=" * 80)
    print(f"{'FASE DO PIPELINE':<30} | {'TEMPO (s)':<12} | {'% TOTAL':<10} | {'OBSERVAÇÕES'}")
    print("-" * 80)

    def print_row(name: str, sec: float, note: str = ""):
        pct = (sec / t_total * 100) if t_total > 0 else 0.0
        print(f"{name:<30} | {sec:>10.2f}s | {pct:>8.1f}% | {note}")

    print_row("1. Probe (ffprobe)", probe_time, "Metadados do vídeo")
    print_row("2. Transcrição (Whisper)", trans_time, "Áudio -> segmentos e palavras")
    print_row("3. LLM (Detecção Momentos)", llm_time, "Fallback matemático" if skip_llm else "Gemini API")
    print_row("4. Face Tracking (OpenCV)", face_time, f"{clip_count} clipe(s) processados")
    print_row("5. Render Vídeo (FFmpeg)", render_time, "Corte e re-enquadramento")
    print_row("6. Legendas Burn-in (FFmpeg)", sub_time, "Re-render com legendas")
    print_row("7. Overhead / E/S / Thumbnail", overhead_time, "Thumbs, GC e IO de disco")
    print("-" * 80)
    print(f"{'TEMPO TOTAL PIPELINE':<30} | {t_total:>10.2f}s | {'100.0%':>9} | {clip_count} clipe(s) gerado(s)")
    print("=" * 80)

    # Limpeza do diretório temporário se solicitado
    if not keep_output:
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"\n[OK] Diretório temporário limpo: {temp_dir}")
    else:
        print(f"\n[INFO] Saídas preservadas em: {temp_dir}")

    return {
        "total_seconds": t_total,
        "probe": probe_time,
        "transcription": trans_time,
        "llm": llm_time,
        "face_tracking": face_time,
        "render": render_time,
        "subtitles": sub_time,
        "overhead": overhead_time,
        "clip_count": clip_count,
    }


def main():
    parser = argparse.ArgumentParser(description="ClipMaker.io Pipeline Benchmark CLI")
    parser.add_argument("--video", type=str, required=True, help="Caminho do arquivo de vídeo de entrada")
    parser.add_argument("--skip-llm", action="store_true", help="Usa fallback matemático de cortes sem chamar API do Gemini")
    parser.add_argument("--aspect", type=str, default="9:16", choices=["9:16", "1:1", "16:9"], help="Proporção de aspecto para recorte (padrão: 9:16)")
    parser.add_argument("--keep-output", action="store_true", help="Mantém arquivos temporários no disco após o término")

    args = parser.parse_args()
    run_benchmark(
        video_path=args.video,
        skip_llm=args.skip_llm,
        aspect_ratio=args.aspect,
        keep_output=args.keep_output,
    )


if __name__ == "__main__":
    main()
