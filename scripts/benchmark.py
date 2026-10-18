#!/usr/bin/env python3
"""
ClipMaker.io Pipeline Benchmark CLI
Executa process_video_full_pipeline de forma direta (project_id=None, sem banco)
e gera uma tabela com o tempo detalhado de cada fase e o tempo total,
com suporte a múltiplas rodadas (--runs N) calculando mediana e variação.
"""

import os
import sys
import time
import shutil
import tempfile
import argparse
import statistics
from pathlib import Path

# Adiciona a raiz do projeto ao sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.timing import get_stage_timings, reset_stage_timings
from backend.app.services.engine_service import process_video_full_pipeline
from backend.app.services.video_service import get_video_info, is_nvenc_available
from backend.app.services.ai_service import get_last_llm_meta


def execute_single_run(video_path: str, skip_llm: bool, aspect_ratio: str, keep_output: bool) -> dict:
    temp_dir = tempfile.mkdtemp(prefix="clipmaker_bench_")
    reset_stage_timings()
    t_start = time.perf_counter()

    try:
        clips = process_video_full_pipeline(
            input_path=video_path,
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

    probe_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "probe")
    trans_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "transcription")
    llm_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "llm")
    face_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "face_tracking")
    render_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "render")
    sub_time = sum(item["seconds"] for item in raw_timings if item["stage"] == "subtitles")

    clip_count = len(clips)
    sum_accounted = probe_time + trans_time + llm_time + face_time + render_time + sub_time
    overhead_time = max(0.0, t_total - sum_accounted)

    if not keep_output:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return {
        "total": t_total,
        "probe": probe_time,
        "transcription": trans_time,
        "llm": llm_time,
        "face_tracking": face_time,
        "render": render_time,
        "subtitles": sub_time,
        "overhead": overhead_time,
        "clip_count": clip_count,
        "llm_meta": get_last_llm_meta(),
    }


def run_benchmark(video_path: str, skip_llm: bool = False, aspect_ratio: str = "9:16", runs: int = 1, keep_output: bool = False):
    abs_video = os.path.abspath(video_path)
    if not os.path.exists(abs_video):
        print(f"\n[ERRO] Arquivo de vídeo não encontrado: {abs_video}")
        sys.exit(1)

    file_size_mb = os.path.getsize(abs_video) / (1024 * 1024)
    print("=" * 85)
    print("                      CLIPMAKER.IO — PIPELINE BENCHMARK")
    print("=" * 85)
    print(f"Vídeo de entrada: {abs_video}")
    print(f"Tamanho do arquivo: {file_size_mb:.2f} MB")
    print(f"Aspect Ratio: {aspect_ratio}")
    print(f"Número de rodadas: {runs}")
    print(f"Modo LLM: {'Fallback Matemático (--skip-llm)' if skip_llm else 'Gemini API Real'}")
    print(f"Aceleração NVENC detectada: {'SIM' if is_nvenc_available() else 'NÃO (CPU libx264)'}")

    try:
        w, h, duration = get_video_info(abs_video)
        print(f"Dimensões originais: {w}x{h} | Duração total: {duration:.1f}s ({duration/60:.2f} min)")
    except Exception as e:
        print(f"[AVISO] Não foi possível obter info prévia: {e}")
        duration = 0.0

    print("-" * 85)

    all_results = []
    for r in range(1, runs + 1):
        print(f"\n>>> INICIANDO RODADA {r}/{runs}...")
        res = execute_single_run(abs_video, skip_llm, aspect_ratio, keep_output)
        all_results.append(res)
        print(f">>> RODADA {r}/{runs} CONCLUÍDA EM {res['total']:.2f}s ({res['clip_count']} clipes)")

    # Agregação estatística
    def get_stats(key: str):
        vals = [r[key] for r in all_results]
        med = statistics.median(vals)
        vmin = min(vals)
        vmax = max(vals)
        vrange = vmax - vmin
        return med, vmin, vmax, vrange

    med_total, min_total, max_total, range_total = get_stats("total")
    med_probe, min_probe, max_probe, _ = get_stats("probe")
    med_trans, min_trans, max_trans, _ = get_stats("transcription")
    med_llm, min_llm, max_llm, _ = get_stats("llm")
    med_face, min_face, max_face, _ = get_stats("face_tracking")
    med_render, min_render, max_render, _ = get_stats("render")
    med_sub, min_sub, max_sub, _ = get_stats("subtitles")
    med_over, min_over, max_over, _ = get_stats("overhead")
    clip_count = all_results[0]["clip_count"]
    llm_meta = all_results[-1]["llm_meta"]

    # Imprimir tabela formatada
    print("\n" + "=" * 85)
    if runs > 1:
        print(f"{'FASE DO PIPELINE':<28} | {'MEDIANA':<10} | {'VARIAÇÃO (MIN-MAX)':<20} | {'% TOTAL':<8} | {'OBSERVAÇÕES'}")
        print("-" * 85)

        def print_row(name: str, med: float, vmin: float, vmax: float, note: str = ""):
            pct = (med / med_total * 100) if med_total > 0 else 0.0
            var_str = f"{vmin:>6.2f}s - {vmax:<6.2f}s"
            print(f"{name:<28} | {med:>8.2f}s | {var_str:<20} | {pct:>6.1f}% | {note}")

        print_row("1. Probe (ffprobe)", med_probe, min_probe, max_probe, "Metadados do vídeo")
        print_row("2. Transcrição (Whisper)", med_trans, min_trans, max_trans, "Áudio -> segmentos")
        print_row("3. LLM (Detecção Momentos)", med_llm, min_llm, max_llm, "Fallback mat." if skip_llm else "Gemini API")
        print_row("4. Face Tracking (OpenCV)", med_face, min_face, max_face, f"{clip_count} cortes analisados")
        print_row("5. Render Vídeo (FFmpeg)", med_render, min_render, max_render, "Corte e re-enquadramento")
        print_row("6. Legendas Burn-in (FFmpeg)", med_sub, min_sub, max_sub, "Re-render com legendas")
        print_row("7. Overhead / E/S / Thumbs", med_over, min_over, max_over, "Thumbs, GC e IO de disco")
        print("-" * 85)
        print(f"{'TEMPO TOTAL PIPELINE':<28} | {med_total:>8.2f}s | {min_total:>6.2f}s - {max_total:<6.2f}s | {'100.0%':>6} | {runs} rodada(s) executada(s)")
    else:
        print(f"{'FASE DO PIPELINE':<30} | {'TEMPO (s)':<12} | {'% TOTAL':<10} | {'OBSERVAÇÕES'}")
        print("-" * 85)

        def print_single_row(name: str, sec: float, note: str = ""):
            pct = (sec / med_total * 100) if med_total > 0 else 0.0
            print(f"{name:<30} | {sec:>10.2f}s | {pct:>8.1f}% | {note}")

        print_single_row("1. Probe (ffprobe)", med_probe, "Metadados do vídeo")
        print_single_row("2. Transcrição (Whisper)", med_trans, "Áudio -> segmentos e palavras")
        print_single_row("3. LLM (Detecção Momentos)", med_llm, "Fallback matemático" if skip_llm else "Gemini API")
        print_single_row("4. Face Tracking (OpenCV)", med_face, f"{clip_count} clipe(s) processados")
        print_single_row("5. Render Vídeo (FFmpeg)", med_render, "Corte e re-enquadramento")
        print_single_row("6. Legendas Burn-in (FFmpeg)", med_sub, "Re-render com legendas")
        print_single_row("7. Overhead / E/S / Thumbnail", med_over, "Thumbs, GC e IO de disco")
        print("-" * 85)
        print(f"{'TEMPO TOTAL PIPELINE':<30} | {med_total:>10.2f}s | {'100.0%':>9} | {clip_count} clipe(s) gerado(s)")

    print("=" * 85)
    if not skip_llm and llm_meta:
        print(f"\n[AUDITORIA LLM]")
        print(f"  • Modelo que respondeu: {llm_meta.get('model')}")
        print(f"  • Tentativas realizadas: {llm_meta.get('attempts')}")
        print(f"  • Limite 429 detectado:  {'SIM (Quota Exceeded)' if llm_meta.get('had_429') else 'NÃO'}")
        print(f"  • Origem dos cortes:     {llm_meta.get('source')}")
        print("=" * 85)

    return {
        "runs": runs,
        "med_total": med_total,
        "min_total": min_total,
        "max_total": max_total,
        "med_probe": med_probe,
        "med_transcription": med_trans,
        "med_llm": med_llm,
        "med_face_tracking": med_face,
        "med_render": med_render,
        "med_subtitles": med_sub,
        "med_overhead": med_over,
        "clip_count": clip_count,
        "llm_meta": llm_meta,
    }


def main():
    parser = argparse.ArgumentParser(description="ClipMaker.io Pipeline Benchmark CLI")
    parser.add_argument("--video", type=str, required=True, help="Caminho do arquivo de vídeo de entrada")
    parser.add_argument("--skip-llm", action="store_true", help="Usa fallback matemático de cortes sem chamar API do Gemini")
    parser.add_argument("--aspect", type=str, default="9:16", choices=["9:16", "1:1", "16:9"], help="Proporção de aspecto para recorte (padrão: 9:16)")
    parser.add_argument("--runs", type=int, default=1, help="Número de execuções para calcular mediana e variação (padrão: 1)")
    parser.add_argument("--keep-output", action="store_true", help="Mantém arquivos temporários no disco após o término")

    args = parser.parse_args()
    run_benchmark(
        video_path=args.video,
        skip_llm=args.skip_llm,
        aspect_ratio=args.aspect,
        runs=args.runs,
        keep_output=args.keep_output,
    )


if __name__ == "__main__":
    main()
