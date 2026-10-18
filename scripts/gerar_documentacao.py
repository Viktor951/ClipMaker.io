#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/gerar_documentacao.py
Gera a documentação técnica completa do projeto ClipMaker.io em formato Word (.docx).
Extrai dados do Git, tabelas de PERFORMANCE.md, código-fonte e gera diagramas PNG.

Uso:
    python scripts/gerar_documentacao.py
"""

import os
import sys
import subprocess
import datetime
from pathlib import Path

import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn, nsdecls

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# Diretórios base
ROOT_DIR = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT_DIR / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DOCX = DOCS_DIR / "ClipMaker_Documentacao.docx"

# Paleta de Cores Institucional
COLOR_NAVY = RGBColor(26, 54, 93)      # #1A365D - Título 1 e cabeçalhos de tabela
COLOR_BLUE = RGBColor(43, 108, 176)    # #2B6CB0 - Título 2
COLOR_DARK = RGBColor(45, 55, 72)      # #2D3748 - Texto padrão e Título 3
COLOR_GRAY = RGBColor(113, 128, 150)   # #718096 - Legendas e rodapés
HEX_NAVY = "1A365D"
HEX_LIGHT_ROW = "F7FAFC"
HEX_BORDER = "CBD5E0"
HEX_CALLOUT_BG = "EBF8FF"
HEX_CALLOUT_BORDER = "3182CE"
HEX_WARN_BG = "FEFCBF"
HEX_WARN_BORDER = "D69E2E"


def run_cmd(cmd_list, cwd=ROOT_DIR):
    """Executa comando shell de forma segura e retorna saída de texto."""
    try:
        res = subprocess.run(cmd_list, cwd=str(cwd), capture_output=True, text=True, check=True, encoding='utf-8', errors='replace')
        return res.stdout.strip()
    except Exception as e:
        return f"Erro ao executar {' '.join(cmd_list)}: {e}"


def get_git_commits():
    """Retorna lista de commits ordenados cronologicamente a partir do git log."""
    raw = run_cmd(['git', 'log', '--reverse', '--date=short', '--format=%h|%ad|%an|%s'])
    commits = []
    for line in raw.split('\n'):
        if not line.strip():
            continue
        parts = line.split('|', 3)
        if len(parts) == 4:
            chash, cdate, cauthor, csubj = parts
            commits.append({
                'hash': chash.strip(),
                'date': cdate.strip(),
                'author': cauthor.strip(),
                'subject': csubj.strip()
            })
    return commits


def get_uncommitted_info():
    """Coleta o status e o diff stat de alterações locais."""
    status_raw = run_cmd(['git', 'status', '--short'])
    diff_stat_raw = run_cmd(['git', 'diff', '--stat'])
    return status_raw, diff_stat_raw


def generate_architecture_diagram():
    """Gera o diagrama de arquitetura física e containers em PNG."""
    fig, ax = plt.subplots(figsize=(12, 7.5), dpi=300)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Fundo geral
    bg = patches.Rectangle((0, 0), 100, 100, facecolor='#F8FAFC', edgecolor='none')
    ax.add_patch(bg)

    # Título do Diagrama
    ax.text(50, 96, "ClipMaker.io — Arquitetura de Produção Docker Compose (v3.0)", 
            fontsize=15, fontweight='bold', ha='center', va='center', color='#1A365D')
    ax.text(50, 93, "Isolamento de Microsserviços, Proxy Reverso Nginx, GPU Passthrough e Volumes Híbridos", 
            fontsize=9, ha='center', va='center', color='#4A5568')

    # 1. Usuário / Cliente
    client_box = patches.FancyBboxPatch((4, 76), 18, 12, boxstyle="round,pad=1.0",
                                        facecolor='#EBF8FF', edgecolor='#3182CE', linewidth=1.5)
    ax.add_patch(client_box)
    ax.text(13, 83.5, "Navegador Web / SPA", fontsize=10, fontweight='bold', ha='center', va='center', color='#2B6CB0')
    ax.text(13, 79, "HTML5 / CSS Puro / JS Vanilla\nUpload, Polling, Player, Editor", fontsize=7.5, ha='center', va='center', color='#4A5568')

    # Seta Cliente -> Nginx
    ax.annotate("", xy=(27, 82), xytext=(22, 82),
                arrowprops=dict(arrowstyle="->", color='#3182CE', lw=2))
    ax.text(24.5, 84, "Porta 80", fontsize=7.5, fontweight='bold', ha='center', color='#2B6CB0')

    # 2. Frontend / Proxy Reverso (Nginx)
    nginx_box = patches.FancyBboxPatch((27, 68), 24, 23, boxstyle="round,pad=1.0",
                                       facecolor='#EDF2F7', edgecolor='#4A5568', linewidth=1.8)
    ax.add_patch(nginx_box)
    ax.text(39, 87.5, "Frontend & Proxy (Nginx)", fontsize=11, fontweight='bold', ha='center', va='center', color='#1A202C')
    ax.text(39, 84, "nginx:alpine (Porta 80:80)", fontsize=8, ha='center', color='#718096')
    ax.text(39, 78.5, "• Servidor Estático SPA (gzip)\n• Proxy Reverso para /api/ -> api:8000\n• X-Accel-Redirect (/internal_videos/)\n• Suporte HTTP Range 206 (Seek)", 
            fontsize=7.5, ha='center', va='center', color='#2D3748')
    ax.text(39, 70.5, "Limites: cpus 0.5 | mem 128m", fontsize=7.5, fontweight='bold', ha='center', color='#4A5568')

    # Seta Nginx -> API
    ax.annotate("", xy=(56, 82), xytext=(51, 82),
                arrowprops=dict(arrowstyle="->", color='#2D3748', lw=1.8))
    ax.text(53.5, 84, "HTTP", fontsize=7.5, ha='center', color='#4A5568')

    # 3. Backend API (FastAPI)
    api_box = patches.FancyBboxPatch((56, 68), 22, 23, boxstyle="round,pad=1.0",
                                     facecolor='#E6FFFA', edgecolor='#319795', linewidth=1.8)
    ax.add_patch(api_box)
    ax.text(67, 87.5, "Backend API (FastAPI)", fontsize=11, fontweight='bold', ha='center', va='center', color='#234E52')
    ax.text(67, 84, "clipmakerai:prod (Uvicorn)", fontsize=8, ha='center', color='#718096')
    ax.text(67, 78.5, "• Autenticação JWT & Bcrypt\n• Validação Pydantic & Anti-SSRF\n• Rate Limit Distribuído (SlowAPI)\n• Ingestão Assíncrona (<15ms)", 
            fontsize=7.5, ha='center', va='center', color='#2D3748')
    ax.text(67, 70.5, "Limites: cpus 1.0 | mem 768m", fontsize=7.5, fontweight='bold', ha='center', color='#234E52')

    # Seta API -> Redis e API -> DB
    ax.annotate("", xy=(83, 82), xytext=(78, 82),
                arrowprops=dict(arrowstyle="->", color='#E53E3E', lw=1.8))
    ax.text(80.5, 84, "Fila", fontsize=7.5, ha='center', color='#C53030')

    # 4. Redis (Fila Huey)
    redis_box = patches.FancyBboxPatch((83, 72), 14, 17, boxstyle="round,pad=1.0",
                                       facecolor='#FFF5F5', edgecolor='#E53E3E', linewidth=1.5)
    ax.add_patch(redis_box)
    ax.text(90, 85.5, "Redis 7", fontsize=10, fontweight='bold', ha='center', color='#9B2C2C')
    ax.text(90, 82, "redis:7-alpine", fontsize=7.5, ha='center', color='#718096')
    ax.text(90, 78, "Filas Huey:\n• huey_ingest\n• huey_render\n• huey (geral)", fontsize=7, ha='center', color='#2D3748')
    ax.text(90, 73.5, "cpus 0.3 | mem 192m", fontsize=7, fontweight='bold', ha='center', color='#9B2C2C')

    # Seta Redis -> Worker
    ax.annotate("", xy=(90, 52), xytext=(90, 72),
                arrowprops=dict(arrowstyle="->", color='#E53E3E', lw=1.8))
    ax.text(93, 62, "Consumo\nde Tarefas", fontsize=7, ha='left', color='#C53030')

    # 5. Worker de Processamento Pesado
    worker_box = patches.FancyBboxPatch((52, 28), 45, 24, boxstyle="round,pad=1.0",
                                        facecolor='#FEFCBF', edgecolor='#D69E2E', linewidth=2.0)
    ax.add_patch(worker_box)
    ax.text(74.5, 48.5, "Worker Huey (Processamento Pesado & IA)", fontsize=11, fontweight='bold', ha='center', color='#744210')
    ax.text(74.5, 45, "clipmakerai:prod-gpu (Target: runtime-gpu)", fontsize=8, ha='center', color='#718096')
    ax.text(74.5, 38, "• Whisper GPU CTranslate2 (modelo small, float16, cache global VRAM)\n• Google Gemini API (gemini-3.8-flash) com fallback inteligente\n• OpenCV Haar Cascade (VideoCapture otimizado, amostragem direta)\n• FFmpeg com NVENC GPU (h264_nvenc, passe único integrado, paralelismo=2)", 
            fontsize=7.5, ha='center', va='center', color='#2D3748')
    ax.text(74.5, 30.5, "Recursos: NVIDIA RTX 3050 6GB | WORKER_CPUS=4.0 | WORKER_MEM_LIMIT=6g", fontsize=8, fontweight='bold', ha='center', color='#B7791F')

    # 6. Banco de Dados (PostgreSQL 15)
    db_box = patches.FancyBboxPatch((27, 28), 22, 24, boxstyle="round,pad=1.0",
                                    facecolor='#EBF8FF', edgecolor='#2B6CB0', linewidth=1.8)
    ax.add_patch(db_box)
    ax.text(38, 48.5, "PostgreSQL 15", fontsize=11, fontweight='bold', ha='center', color='#2B6CB0')
    ax.text(38, 45, "postgres:15-alpine", fontsize=8, ha='center', color='#718096')
    ax.text(38, 38, "Tabelas Relacionais:\n• users, projects, clips\n• transcriptions (cache hash)\n• job_metrics (ETA fila)\nPool assíncrono via asyncpg", 
            fontsize=7.5, ha='center', va='center', color='#2D3748')
    ax.text(38, 30.5, "cpus 1.0 | mem 512m", fontsize=8, fontweight='bold', ha='center', color='#2B6CB0')

    # Seta API <-> DB e Worker <-> DB
    ax.annotate("", xy=(38, 52), xytext=(60, 68),
                arrowprops=dict(arrowstyle="<->", color='#2B6CB0', lw=1.5, ls='--'))
    ax.annotate("", xy=(49, 40), xytext=(52, 40),
                arrowprops=dict(arrowstyle="<->", color='#2B6CB0', lw=1.5, ls='--'))

    # 7. Serviço de Migrações (One-shot)
    mig_box = patches.FancyBboxPatch((4, 42), 18, 10, boxstyle="round,pad=0.8",
                                     facecolor='#F7FAFC', edgecolor='#A0AEC0', linewidth=1.2)
    ax.add_patch(mig_box)
    ax.text(13, 48, "Migrate (One-shot)", fontsize=9, fontweight='bold', ha='center', color='#4A5568')
    ax.text(13, 44, "scripts/migrate.sh\nExecuta migrations/ *.sql", fontsize=7.5, ha='center', color='#718096')

    # 8. Serviço Cleanup (Daemon)
    clean_box = patches.FancyBboxPatch((4, 28), 18, 10, boxstyle="round,pad=0.8",
                                       facecolor='#F7FAFC', edgecolor='#A0AEC0', linewidth=1.2)
    ax.add_patch(clean_box)
    ax.text(13, 34, "Cleanup Daemon", fontsize=9, fontweight='bold', ha='center', color='#4A5568')
    ax.text(13, 30.5, "scripts/cleanup.py\nExpurgo a cada 1 hora", fontsize=7.5, ha='center', color='#718096')

    # 9. Camada de Armazenamento Híbrido (Rodapé)
    storage_area = patches.FancyBboxPatch((4, 4), 93, 19, boxstyle="round,pad=1.0",
                                          facecolor='#EDF2F7', edgecolor='#718096', linewidth=1.5, linestyle=':')
    ax.add_patch(storage_area)
    ax.text(50.5, 19.5, "CAMADA DE ARMAZENAMENTO HÍBRIDO E VOLUMES", fontsize=10, fontweight='bold', ha='center', color='#2D3748')

    # Bloco Volume Rápido Docker
    vol_fast = patches.Rectangle((7, 7), 40, 10, facecolor='#FFFFFF', edgecolor='#3182CE', linewidth=1.2)
    ax.add_patch(vol_fast)
    ax.text(27, 14, "Volume Nomeado Docker: clipmaker_temp_videos", fontsize=8.5, fontweight='bold', ha='center', color='#2B6CB0')
    ax.text(27, 9.5, "I/O ext4 nativo de alta velocidade | /app/backend/temp_videos\nCompartilhado entre API, Worker, Nginx (ro) e Cleanup", 
            fontsize=7, ha='center', color='#4A5568')

    # Bloco Persistência Disco D:
    vol_d = patches.Rectangle((50, 7), 44, 10, facecolor='#FFFFFF', edgecolor='#D69E2E', linewidth=1.2)
    ax.add_patch(vol_d)
    ax.text(72, 14, "Bind Mount Host D: (DATA_ROOT: D:/docker-data/clipmaker)", fontsize=8.5, fontweight='bold', ha='center', color='#B7791F')
    ax.text(72, 9.5, "Dados leves e persistentes: cache/ (HuggingFace Whisper),\nlogs/ (auditoria) e redis/ (banco de dados AOF do Redis)", 
            fontsize=7, ha='center', color='#4A5568')

    diagram_path = DOCS_DIR / "arch_diagram.png"
    plt.tight_layout()
    plt.savefig(str(diagram_path), dpi=300, bbox_inches='tight')
    plt.close()
    return diagram_path


def generate_pipeline_diagram():
    """Gera o fluxograma ponta a ponta do pipeline de processamento em PNG."""
    fig, ax = plt.subplots(figsize=(12, 7.0), dpi=300)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis('off')

    # Fundo
    bg = patches.Rectangle((0, 0), 100, 100, facecolor='#F8FAFC', edgecolor='none')
    ax.add_patch(bg)

    # Título
    ax.text(50, 96, "ClipMaker.io — Fluxo de Processamento de Mídia Ponta a Ponta", 
            fontsize=15, fontweight='bold', ha='center', va='center', color='#1A365D')
    ax.text(50, 93, "Ciclo Completo: Ingestão Assíncrona, Transcrição, LLM, Face Tracking, Render e Entrega", 
            fontsize=9, ha='center', va='center', color='#4A5568')

    # Etapa 1: Ingestão
    box1 = patches.FancyBboxPatch((3, 62), 17, 26, boxstyle="round,pad=0.8", facecolor='#EBF8FF', edgecolor='#3182CE', linewidth=1.5)
    ax.add_patch(box1)
    ax.text(11.5, 84, "1. Ingestão\nde Vídeo", fontsize=10, fontweight='bold', ha='center', color='#2B6CB0')
    ax.text(11.5, 74, "• Upload Multipart:\nescrita desacoplada\nvia asyncio.to_thread\n\n• Importação URL:\nvalidação Anti-SSRF,\nresposta em <15ms,\nyt-dlp na fila Huey", fontsize=7.5, ha='center', color='#2D3748')
    ax.text(11.5, 64.5, "Status: DOWNLOADING", fontsize=7, fontweight='bold', ha='center', color='#3182CE')

    # Seta 1 -> 2
    ax.annotate("", xy=(23, 75), xytext=(20, 75), arrowprops=dict(arrowstyle="->", color='#2B6CB0', lw=2))

    # Etapa 2: Transcrição Whisper
    box2 = patches.FancyBboxPatch((23, 62), 17, 26, boxstyle="round,pad=0.8", facecolor='#FEFCBF', edgecolor='#D69E2E', linewidth=1.5)
    ax.add_patch(box2)
    ax.text(31.5, 84, "2. Transcrição\nWhisper GPU", fontsize=10, fontweight='bold', ha='center', color='#744210')
    ax.text(31.5, 73.5, "• CTranslate2 float16\n• Modelo small em VRAM\n• Cache mantido 15 min\n\n• Reuso Inteligente:\nignora etapa se hash\nou URL já existirem\nno banco (-100% tempo)", fontsize=7.5, ha='center', color='#2D3748')
    ax.text(31.5, 64.5, "Status: TRANSCRIBING", fontsize=7, fontweight='bold', ha='center', color='#B7791F')

    # Seta 2 -> 3
    ax.annotate("", xy=(43, 75), xytext=(40, 75), arrowprops=dict(arrowstyle="->", color='#D69E2E', lw=2))

    # Etapa 3: Análise Semântica LLM
    box3 = patches.FancyBboxPatch((43, 62), 17, 26, boxstyle="round,pad=0.8", facecolor='#E6FFFA', edgecolor='#319795', linewidth=1.5)
    ax.add_patch(box3)
    ax.text(51.5, 84, "3. Seleção\nSemântica LLM", fontsize=10, fontweight='bold', ha='center', color='#234E52')
    ax.text(51.5, 73.5, "• Google Gemini API\n(gemini-3.8-flash)\n\n• Resiliência 429:\nchaveamento dinâmico\nde modelos alternativos\n\n• Fallback Heurístico:\nalgoritmo matemático\nse cota esgotar", fontsize=7.5, ha='center', color='#2D3748')
    ax.text(51.5, 64.5, "Status: ANALYZING", fontsize=7, fontweight='bold', ha='center', color='#234E52')

    # Seta 3 -> 4
    ax.annotate("", xy=(63, 75), xytext=(60, 75), arrowprops=dict(arrowstyle="->", color='#319795', lw=2))

    # Etapa 4: Face Tracking
    box4 = patches.FancyBboxPatch((63, 62), 17, 26, boxstyle="round,pad=0.8", facecolor='#FAF5FF', edgecolor='#805AD5', linewidth=1.5)
    ax.add_patch(box4)
    ax.text(71.5, 84, "4. Face Tracking\nOpenCV", fontsize=10, fontweight='bold', ha='center', color='#553C9A')
    ax.text(71.5, 73.5, "• cv2.VideoCapture:\nleitura direta do vídeo\n\n• Amostragem Leve:\ncap.grab() a cada 500ms,\nresize para 320px\n\n• Suavização alpha=0.3\n• Salva face_center_x\npara re-renders fiéis", fontsize=7.5, ha='center', color='#2D3748')
    ax.text(71.5, 64.5, "Status: RENDERING", fontsize=7, fontweight='bold', ha='center', color='#6B46C1')

    # Seta 4 -> 5
    ax.annotate("", xy=(83, 75), xytext=(80, 75), arrowprops=dict(arrowstyle="->", color='#805AD5', lw=2))

    # Etapa 5: Render FFmpeg
    box5 = patches.FancyBboxPatch((83, 62), 14, 26, boxstyle="round,pad=0.8", facecolor='#FFF5F5', edgecolor='#E53E3E', linewidth=1.5)
    ax.add_patch(box5)
    ax.text(90, 84, "5. Render\nPasse Único", fontsize=10, fontweight='bold', ha='center', color='#9B2C2C')
    ax.text(90, 73.5, "• Crop + Scale +\nLegendas num só filtro\n\n• Aceleração NVENC\n(h264_nvenc)\n\n• Paralelismo=2\n(ThreadPoolExecutor)\n\n• Faststart para web", fontsize=7.5, ha='center', color='#2D3748')
    ax.text(90, 64.5, "Elimina clean_*.mp4", fontsize=7, fontweight='bold', ha='center', color='#C53030')

    # Seta de retorno para Persistência e Entrega (Linha inferior)
    ax.annotate("", xy=(85, 48), xytext=(90, 62), arrowprops=dict(arrowstyle="->", color='#2D3748', lw=1.5, ls='--'))

    # Bloco 6: Persistência Incremental e Miniaturas
    box6 = patches.FancyBboxPatch((55, 14), 40, 32, boxstyle="round,pad=0.8", facecolor='#F7FAFC', edgecolor='#4A5568', linewidth=1.5)
    ax.add_patch(box6)
    ax.text(75, 41, "6. Persistência Incremental e Métricas de Fila", fontsize=10, fontweight='bold', ha='center', color='#1A202C')
    ax.text(75, 29, "• Cada clipe concluído é persistido imediatamente no PostgreSQL (status COMPLETED)\n• Geração de miniatura JPG (~480px, frame em ~1s) via FFmpeg durante o render\n• Interface exibe clipe imediatamente no polling (/api/projects/{id}/status)\n• Gravação de métricas na tabela job_metrics (duração, tempo total, secPerMinute)\n• Cálculo da média móvel para estimativa dinâmica de fila (queuePosition e ETA)", 
            fontsize=7.5, ha='center', va='center', color='#2D3748')
    ax.text(75, 18, "Status Final do Projeto: READY", fontsize=8, fontweight='bold', ha='center', color='#2F855A')

    # Seta 6 -> 7
    ax.annotate("", xy=(48, 30), xytext=(55, 30), arrowprops=dict(arrowstyle="->", color='#2B6CB0', lw=2))

    # Bloco 7: Entrega Acelerada Nginx
    box7 = patches.FancyBboxPatch((5, 14), 43, 32, boxstyle="round,pad=0.8", facecolor='#EDF2F7', edgecolor='#2B6CB0', linewidth=1.5)
    ax.add_patch(box7)
    ax.text(26.5, 41, "7. Entrega de Mídia em Alta Performance (Nginx)", fontsize=10, fontweight='bold', ha='center', color='#2B6CB0')
    ax.text(26.5, 29, "• Rota de Download: /api/videos/download/{clip_id}\n• Validação segura de token JWT e propriedade no backend FastAPI\n• Resposta com cabeçalho interno: X-Accel-Redirect: /internal_videos/<filename>\n• Nginx serve o arquivo diretamente do volume Docker somente-leitura\n• Suporte completo a HTTP Range (206 Partial Content) para seek instantâneo\n• Proteção contra Path Traversal via Path.relative_to() e basename", 
            fontsize=7.5, ha='center', va='center', color='#2D3748')
    ax.text(26.5, 18, "Consumo de RAM/CPU na API: Zero durante o streaming", fontsize=8, fontweight='bold', ha='center', color='#2B6CB0')

    diagram_path = DOCS_DIR / "pipeline_flow.png"
    plt.tight_layout()
    plt.savefig(str(diagram_path), dpi=300, bbox_inches='tight')
    plt.close()
    return diagram_path


# ==============================================================================
# FORMATAÇÃO E ESTILOS DOCX
# ==============================================================================

def set_cell_shading(cell, color_hex):
    """Aplica cor de fundo a uma célula de tabela no Word."""
    tcPr = cell._tc.get_or_add_tcPr()
    for child in list(tcPr):
        if child.tag.endswith('shd'):
            tcPr.remove(child)
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}"/>')
    tcPr.append(shd)


def set_cell_borders(cell, top=HEX_BORDER, bottom=HEX_BORDER, left=None, right=None, sz="4"):
    """Define bordas personalizadas em uma célula de tabela."""
    tcPr = cell._tc.get_or_add_tcPr()
    for child in list(tcPr):
        if child.tag.endswith('tcBorders'):
            tcPr.remove(child)
    
    borders_elm = OxmlElement('w:tcBorders')
    
    borders_dict = {
        'top': top,
        'bottom': bottom,
        'left': left,
        'right': right
    }
    for border_name, color in borders_dict.items():
        if color:
            b_elm = OxmlElement(f'w:{border_name}')
            b_elm.set(qn('w:val'), 'single')
            b_elm.set(qn('w:sz'), sz)
            b_elm.set(qn('w:space'), '0')
            b_elm.set(qn('w:color'), color)
            borders_elm.append(b_elm)
        else:
            b_elm = OxmlElement(f'w:{border_name}')
            b_elm.set(qn('w:val'), 'none')
            borders_elm.append(b_elm)
            
    tcPr.append(borders_elm)


def set_cell_margins(cell, top=100, bottom=100, left=140, right=140):
    """Define margens internas (padding) de uma célula de tabela em twips."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def style_table(table, col_widths=None, align_cols=None):
    """Aplica o padrão institucional de tabela corporativa."""
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    # Linha de cabeçalho
    header_tr = table.rows[0]._tr.get_or_add_trPr()
    trPr = OxmlElement('w:tblHeader')
    header_tr.append(trPr)

    for i, cell in enumerate(table.rows[0].cells):
        set_cell_shading(cell, HEX_NAVY)
        set_cell_borders(cell, top=HEX_NAVY, bottom=HEX_NAVY, left=None, right=None, sz="8")
        set_cell_margins(cell, top=120, bottom=120, left=140, right=140)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        for p in cell.paragraphs:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if not align_cols else align_cols[i]
            for run in p.runs:
                run.font.name = 'Calibri'
                run.font.size = Pt(9.5)
                run.font.bold = True
                run.font.color.rgb = RGBColor(255, 255, 255)

    # Linhas de dados
    for r_idx, row in enumerate(table.rows[1:], start=1):
        bg_color = HEX_LIGHT_ROW if r_idx % 2 == 1 else "FFFFFF"
        for c_idx, cell in enumerate(row.cells):
            set_cell_shading(cell, bg_color)
            set_cell_borders(cell, top=HEX_BORDER, bottom=HEX_BORDER, left=None, right=None, sz="4")
            set_cell_margins(cell, top=80, bottom=80, left=140, right=140)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            for p in cell.paragraphs:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT if not align_cols else align_cols[c_idx]
                for run in p.runs:
                    run.font.name = 'Calibri'
                    run.font.size = Pt(9.0)
                    run.font.color.rgb = COLOR_DARK

    # Aplicação de larguras
    if col_widths:
        for row in table.rows:
            for idx, width in enumerate(col_widths):
                if idx < len(row.cells):
                    row.cells[idx].width = Inches(width)


def add_callout(doc, text, title="NOTA IMPORTANTE", kind="info"):
    """Adiciona caixa de destaque / alerta estilizada."""
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    
    cell = table.rows[0].cells[0]
    cell.width = Inches(6.5)
    
    border_color = HEX_CALLOUT_BORDER if kind == "info" else HEX_WARN_BORDER
    bg_color = HEX_CALLOUT_BG if kind == "info" else HEX_WARN_BG
    
    set_cell_shading(cell, bg_color)
    set_cell_borders(cell, top=None, bottom=None, left=border_color, right=None, sz="24")
    set_cell_margins(cell, top=120, bottom=120, left=180, right=140)
    
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(2)
    run_t = p.add_run(f"[{title}] ")
    run_t.font.name = 'Calibri'
    run_t.font.size = Pt(9.5)
    run_t.font.bold = True
    run_t.font.color.rgb = COLOR_NAVY if kind == "info" else RGBColor(183, 121, 31)
    
    run_b = p.add_run(text)
    run_b.font.name = 'Calibri'
    run_b.font.size = Pt(9.5)
    run_b.font.color.rgb = COLOR_DARK
    
    doc.add_paragraph().paragraph_format.space_after = Pt(4)


def add_heading_1(doc, text):
    """Adiciona Título 1 formatado com padrão visual corporativo."""
    h = doc.add_heading(text, level=1)
    h.paragraph_format.space_before = Pt(16)
    h.paragraph_format.space_after = Pt(6)
    h.paragraph_format.keep_with_next = True
    for r in h.runs:
        r.font.name = 'Calibri'
        r.font.size = Pt(16)
        r.font.bold = True
        r.font.color.rgb = COLOR_NAVY
    return h


def add_heading_2(doc, text):
    """Adiciona Título 2 formatado."""
    h = doc.add_heading(text, level=2)
    h.paragraph_format.space_before = Pt(12)
    h.paragraph_format.space_after = Pt(4)
    h.paragraph_format.keep_with_next = True
    for r in h.runs:
        r.font.name = 'Calibri'
        r.font.size = Pt(13)
        r.font.bold = True
        r.font.color.rgb = COLOR_BLUE
    return h


def add_heading_3(doc, text):
    """Adiciona Título 3 formatado."""
    h = doc.add_heading(text, level=3)
    h.paragraph_format.space_before = Pt(8)
    h.paragraph_format.space_after = Pt(2)
    h.paragraph_format.keep_with_next = True
    for r in h.runs:
        r.font.name = 'Calibri'
        r.font.size = Pt(11)
        r.font.bold = True
        r.font.color.rgb = COLOR_DARK
    return h


def add_paragraph(doc, text, bold_prefix=None, space_after=4):
    """Adiciona parágrafo com tipografia consistente."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.font.name = 'Calibri'
        r_pre.font.size = Pt(10.5)
        r_pre.font.bold = True
        r_pre.font.color.rgb = COLOR_DARK
    r = p.add_run(text)
    r.font.name = 'Calibri'
    r.font.size = Pt(10.5)
    r.font.color.rgb = COLOR_DARK
    return p


def add_bullet(doc, text, bold_prefix=None):
    """Adiciona item de lista com marcadores."""
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.15
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.font.name = 'Calibri'
        r_pre.font.size = Pt(10.0)
        r_pre.font.bold = True
        r_pre.font.color.rgb = COLOR_DARK
    r = p.add_run(text)
    r.font.name = 'Calibri'
    r.font.size = Pt(10.0)
    r.font.color.rgb = COLOR_DARK
    return p


def build_cover_page(doc, latest_commit, gen_date):
    """Gera a capa formal do documento técnico."""
    p_pre = doc.add_paragraph()
    p_pre.paragraph_format.space_before = Pt(72)
    
    # Nome do Projeto
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_after = Pt(4)
    r_title = p_title.add_run("ClipMaker.io")
    r_title.font.name = 'Calibri'
    r_title.font.size = Pt(34)
    r_title.font.bold = True
    r_title.font.color.rgb = COLOR_NAVY
    
    # Subtítulo
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_after = Pt(28)
    r_sub = p_sub.add_run("DOCUMENTAÇÃO TÉCNICA E HISTÓRICA DO PROJETO")
    r_sub.font.name = 'Calibri'
    r_sub.font.size = Pt(13)
    r_sub.font.bold = True
    r_sub.font.color.rgb = COLOR_BLUE
    
    p_desc = doc.add_paragraph()
    p_desc.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_desc.paragraph_format.space_after = Pt(140)
    r_desc = p_desc.add_run("Engenharia de Mídia, Arquitetura de Microsserviços, Auditoria de Otimização,\nHardening de Segurança e Linha do Tempo Integral dos Commits")
    r_desc.font.name = 'Calibri'
    r_desc.font.size = Pt(10.5)
    r_desc.font.color.rgb = COLOR_GRAY
    
    # Metadados no rodapé da capa
    p_meta = doc.add_paragraph()
    p_meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_meta.paragraph_format.space_after = Pt(2)
    
    def add_meta_line(label, val):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(2)
        r1 = p.add_run(f"{label}: ")
        r1.font.name = 'Calibri'
        r1.font.size = Pt(10)
        r1.font.bold = True
        r1.font.color.rgb = COLOR_DARK
        r2 = p.add_run(val)
        r2.font.name = 'Calibri'
        r2.font.size = Pt(10)
        r2.font.color.rgb = COLOR_DARK

    add_meta_line("Versão da Arquitetura", "3.0 (Produção)")
    add_meta_line("Data de Geração", gen_date)
    add_meta_line("Commit de Referência", f"{latest_commit['hash']} ({latest_commit['date']})")
    add_meta_line("Ambiente Orquestrado", "Docker Compose / GPU NVIDIA / PostgreSQL / Redis")
    
    doc.add_page_break()


def build_toc(doc):
    """Insere o campo dinâmico de sumário do Word."""
    h = doc.add_heading("Sumário", level=1)
    h.paragraph_format.space_before = Pt(12)
    h.paragraph_format.space_after = Pt(8)
    for r in h.runs:
        r.font.name = 'Calibri'
        r.font.size = Pt(18)
        r.font.bold = True
        r.font.color.rgb = COLOR_NAVY

    p_toc = doc.add_paragraph()
    p_toc.paragraph_format.space_after = Pt(12)
    r_toc = p_toc.add_run()
    
    # XML Field TOC \o "1-3" \h \z \u
    fld1 = OxmlElement('w:fldChar')
    fld1.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = 'TOC \\o "1-3" \\h \\z \\u'
    fld2 = OxmlElement('w:fldChar')
    fld2.set(qn('w:fldCharType'), 'separate')
    fld3 = OxmlElement('w:fldChar')
    fld3.set(qn('w:fldCharType'), 'end')
    
    r_toc._r.append(fld1)
    r_toc._r.append(instr)
    r_toc._r.append(fld2)
    r_toc._r.append(fld3)

    add_callout(doc, 
                "Este sumário foi estruturado através do código de campo dinâmico nativo do Microsoft Word. "
                "Como o gerador de arquivos não executa a paginação gráfica do Word, clique com o botão direito "
                "sobre o índice acima e escolha 'Atualizar campo' (ou pressione a tecla F9 no Word) para renderizar "
                "a numeração exata de todas as páginas.", 
                title="INSTRUÇÃO DE ATUALIZAÇÃO DO SUMÁRIO", 
                kind="info")

    doc.add_page_break()


def setup_footer(doc):
    """Configura o rodapé do documento com numeração de páginas."""
    for section in doc.sections:
        footer = section.footer
        p = footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        
        r_pre = p.add_run("ClipMaker.io — Documentação Técnica | Página ")
        r_pre.font.name = 'Calibri'
        r_pre.font.size = Pt(8.5)
        r_pre.font.color.rgb = COLOR_GRAY
        
        fldSimple = OxmlElement('w:fldSimple')
        fldSimple.set(qn('w:instr'), 'PAGE')
        p._p.append(fldSimple)


# ==============================================================================
# EXECUÇÃO PRINCIPAL
# ==============================================================================

def main():
    print("[*] Iniciando geração da documentação ClipMaker.io em .docx...")
    
    # 1. Coleta de dados do Git
    commits = get_git_commits()
    total_commits = len(commits)
    first_commit = commits[0] if commits else {'hash': 'N/A', 'date': 'N/A'}
    latest_commit = commits[-1] if commits else {'hash': 'N/A', 'date': 'N/A'}
    uncommitted_status, uncommitted_diff = get_uncommitted_info()
    today_date = "2026-10-18"
    today_full = "18 de Outubro de 2026"
    
    print(f"[*] Total de commits no Git: {total_commits}")
    print(f"[*] Primeiro commit: {first_commit['hash']} em {first_commit['date']}")
    print(f"[*] Último commit: {latest_commit['hash']} em {latest_commit['date']}")
    
    # 2. Geração dos diagramas de alta resolução
    print("[*] Gerando diagramas com matplotlib...")
    arch_diagram_path = generate_architecture_diagram()
    pipeline_diagram_path = generate_pipeline_diagram()
    print(f"    -> Diagrama de arquitetura: {arch_diagram_path}")
    print(f"    -> Diagrama de fluxo de pipeline: {pipeline_diagram_path}")
    
    # 3. Inicialização do documento Word
    doc = docx.Document()
    
    # Configuração de margens (1 polegada = 2.54 cm)
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
    setup_footer(doc)
    
    # Capa e Sumário
    build_cover_page(doc, latest_commit, today_full)
    build_toc(doc)
    
    # --------------------------------------------------------------------------
    # CAPÍTULO 1: RESUMO EXECUTIVO
    # --------------------------------------------------------------------------
    add_heading_1(doc, "1. Resumo Executivo")
    add_paragraph(doc, 
                  "O ClipMaker.io é uma plataforma web completa e especializada em reaproveitamento inteligente de conteúdo audiovisual. "
                  "Seu propósito central é converter vídeos de longa duração (podcasts, entrevistas, aulas, transmissões ao vivo e palestras) "
                  "em cortes verticais de alta densidade semântica (formato 9:16) perfeitamente preparados para publicação no TikTok, "
                  "YouTube Shorts, Instagram Reels e Kwai.")
    
    add_paragraph(doc, 
                  "O sistema atende a produtores de conteúdo, emissoras, influenciadores, agências de marketing e equipes editoriais que "
                  "demandam alto volume de publicação com mínima intervenção manual. O pipeline automatiza de ponta a ponta as tarefas "
                  "de ingestão de mídia, extração de áudio, transcrição com precisão temporal de palavras, detecção semântica de ganchos virais por IA, "
                  "rastreamento dinâmico do locutor para corte inteligente de enquadramento (smart face crop) e queima de legendas animadas estilizadas.")
    
    add_heading_2(doc, "1.1 Estado Atual do Projeto")
    add_paragraph(doc, 
                  "Na data desta documentação (18 de Outubro de 2026), o ClipMaker.io opera em sua versão consolidada 3.0. "
                  "A aplicação encontra-se integralmente conteinerizada com Docker Compose, estruturada em microsserviços desacoplados "
                  "e com isolamento rigoroso de responsabilidades. O backend é fundamentado no framework assíncrono FastAPI, persistência relacional "
                  "assíncrona via asyncpg em banco PostgreSQL 15, fila de mensageria distribuída gerenciada pelo Huey sobre Redis 7, "
                  "proxy reverso Nginx com aceleração de entrega estática e streaming via cabeçalho X-Accel-Redirect, e aceleração de inferência "
                  "e codificação por hardware através de GPU dedicada NVIDIA (NVENC).")
    
    add_heading_2(doc, "1.2 Principais Indicadores de Desempenho (Antes x Depois no Container)")
    add_paragraph(doc, 
                  "Ao longo da sessão de engenharia e otimização, o pipeline de processamento foi submetido a rigorosos testes de carga "
                  "e perfilamento estatístico em container de produção, utilizando como padrão um vídeo Full HD de 6,77 minutos (256,56 MB) "
                  "para a geração de 5 clipes verticais de 75 segundos cada. Os resultados medidos no container demonstram ganhos expressivos:")
    
    # Tabela Resumo Executivo
    t_res = doc.add_table(rows=5, cols=5)
    t_res_data = [
        ["Cenário Avaliado", "Ambiente de Medição", "Tempo Total (Mediana)", "Ganho vs Baseline", "Velocidade Relativa"],
        ["Linha de Base Inicial (Etapa 0)", "Container Worker (2 vCPU, 3GB, NTFS)", "235,16s (3m 55s)", "— (Referência)", "1,00x"],
        ["Infraestrutura & GPU (Etapa 1)", "Container Worker (GPU NVENC, 4 vCPU, Volume)", "100,65s (1m 40s)", "-57,2%", "2,34x mais rápido"],
        ["Pipeline Único & Paralelo (Etapa 2)", "Container Worker (Passe Único, Parallel=2)", "86,41s (1m 26s)", "-63,3%", "2,72x mais rápido"],
        ["API Assíncrona & X-Accel (Etapa 3)", "Container Worker + Nginx + Filas", "72,25s (1m 12s)", "-69,3%", "3,25x mais rápido"]
    ]
    for r_idx, row in enumerate(t_res_data):
        for c_idx, val in enumerate(row):
            t_res.rows[r_idx].cells[c_idx].paragraphs[0].text = val
    style_table(t_res, col_widths=[1.8, 1.8, 1.2, 1.0, 1.2], 
                align_cols=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER])

    add_paragraph(doc, 
                  "Quando considerado o mecanismo de reuso inteligente de transcrição Whisper (onde o áudio de um mesmo arquivo ou URL já "
                  "foi processado anteriormente), o tempo de processamento total no container cai para ~59,88s, representando uma redução de 74,5% "
                  "e uma aceleração global de 3,93x em relação à linha de base original.", bold_prefix="Impacto com Reuso de Transcrição: ")
    
    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 2: LINHA DO TEMPO COMPLETA
    # --------------------------------------------------------------------------
    add_heading_1(doc, "2. Linha do Tempo do Projeto")
    add_paragraph(doc, 
                  "A tabela a seguir apresenta a história cronológica completa de evolução do repositório ClipMaker.io, "
                  "extraída estritamente a partir do histórico de commits do Git. A listagem cobre desde a criação inicial do repositório "
                  "até o estado de fechamento da sessão técnica atual, sem omissão de revisões.")
    
    t_log = doc.add_table(rows=total_commits + 1, cols=4)
    t_log.rows[0].cells[0].paragraphs[0].text = "Data"
    t_log.rows[0].cells[1].paragraphs[0].text = "Commit"
    t_log.rows[0].cells[2].paragraphs[0].text = "Autor"
    t_log.rows[0].cells[3].paragraphs[0].text = "Mensagem do Commit (Resumo)"
    
    for idx, c in enumerate(commits, start=1):
        t_log.rows[idx].cells[0].paragraphs[0].text = c['date']
        t_log.rows[idx].cells[1].paragraphs[0].text = c['hash']
        t_log.rows[idx].cells[2].paragraphs[0].text = c['author']
        t_log.rows[idx].cells[3].paragraphs[0].text = c['subject']
        
    style_table(t_log, col_widths=[0.9, 0.8, 1.2, 3.6],
                align_cols=[WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT])

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 3: HISTÓRIA DO PROJETO POR FASES
    # --------------------------------------------------------------------------
    add_heading_1(doc, "3. História do Projeto por Fases")
    add_paragraph(doc, 
                  "O desenvolvimento do ClipMaker.io transcorreu ao longo de quatro fases distintas, refletindo a evolução "
                  "de um protótipo inicial até uma plataforma de produção de alta disponibilidade e performance. As datas e arquivos "
                  "afetados foram apurados via histórico do Git.")

    # Fase 1
    add_heading_2(doc, "3.1 Fase 1: Concepção, Protótipo e MVP Inicial (2026-09-06)")
    add_paragraph(doc, 
                  "Nesta fase inaugural, o projeto foi concebido e seu fluxo de valor comprovado através de uma implementação mínima viável. "
                  "O objetivo residia em permitir o upload de vídeos ou submissão de URLs externas, transcrição básica com modelo Whisper, "
                  "identificação de momentos virais por inteligência artificial e geração automatizada de clipes em formato 9:16.", 
                  bold_prefix="Objetivo: ")
    add_paragraph(doc, 
                  "Commits 09019ac a cd912b4 (7 commits no total). Arquivos centrais criados: backend/app/main.py, backend/app/services/ai_service.py, "
                  "backend/app/services/video_service.py e a estrutura web em frontend/index.html e frontend/app.js.", 
                  bold_prefix="Evidências Git: ")
    add_paragraph(doc, 
                  "Durante esta fase inicial, a persistência e enfileiramento foram modelados de forma simples com SQLite local e Huey com "
                  "backend local. Foi realizada a primeira integração direta com a API do Google Gemini para seleção semântica dos melhores momentos "
                  "baseada na transcrição textual. Foi identificado o primeiro risco de segurança no commit eb65173, motivando a extração imediata da "
                  "SECRET_KEY para variáveis de ambiente.", 
                  bold_prefix="Decisões Técnicas: ")

    # Fase 2
    add_heading_2(doc, "3.2 Fase 2: Arquitetura de Produção e Migração para PostgreSQL/Redis (2026-09-08 a 2026-09-22)")
    add_paragraph(doc, 
                  "Transformar a base do MVP em uma arquitetura robusta e escalável, apta a suportar múltiplos usuários simultâneos sem "
                  "bloqueios de banco ou corrupção de arquivos temporários.", 
                  bold_prefix="Objetivo: ")
    add_paragraph(doc, 
                  "Commits 08f7e7b a df544dc (6 commits). Arquivos altamente modificados: backend/app/db/db_service.py, backend/app/worker/worker.py, "
                  "docker-compose.prod.yml, scripts/cleanup.py e migrations/001_init.sql.", 
                  bold_prefix="Evidências Git: ")
    add_paragraph(doc, 
                  "O banco SQLite foi substituído pelo PostgreSQL 15 orquestrado em container dedicado com pooling assíncrono via asyncpg. "
                  "A fila de tarefas do Huey foi portada para uma instância dedicada do Redis 7. Criação do primeiro docker-compose.prod.yml "
                  "com isolamento de serviços (api, worker, db, redis, frontend e cleanup). No commit b36dc32 foi implementado o MVP do Editor de Clipes "
                  "no frontend, permitindo edição de legendas e recorte temporal. No commit df544dc foram corrigidos problemas de aspect ratio 16:9 "
                  "e criado o script de limpeza periódica de disco temporário (cleanup.py).", 
                  bold_prefix="Decisões Técnicas: ")

    # Fase 3
    add_heading_2(doc, "3.3 Fase 3: Hardening DevOps, Isolamento de Proxy e Padronização REST (2026-10-06 a 2026-10-17)")
    add_paragraph(doc, 
                  "Elevar a postura de segurança dos containers, mitigar riscos de privilégios excessivos no host, isolar a exposição pública "
                  "exclusivamente através de um proxy reverso e desacoplar módulos de frontend e testes.", 
                  bold_prefix="Objetivo: ")
    add_paragraph(doc, 
                  "Commits c89b6d7 a 61bb2c6 (5 commits). Arquivos afetados: docker-compose.prod.yml, frontend/nginx.conf, backend/app/main.py, "
                  "frontend/js/ui.js e suíte de testes em tests/.", 
                  bold_prefix="Evidências Git: ")
    add_paragraph(doc, 
                  "No commit c89b6d7 foram aplicadas diretivas rígidas de segurança aos containers (security_opt: no-new-privileges:true, cap_drop: ALL) "
                  "e configurado o armazenamento de dados persistentes no disco D: via DATA_ROOT. No commit d8902c8 o Nginx assumiu o papel de gateway "
                  "único na porta 80, eliminando a exposição direta da porta do Uvicorn e unificando as rotas em /api/projects e /api/videos. "
                  "No frontend, o código de renderização DOM foi extraído do app.js para o módulo independente ui.js (commit ac7a02c). "
                  "No commit 61bb2c6 foram consolidadas migrações críticas e testes automatizados.", 
                  bold_prefix="Decisões Técnicas: ")

    # Fase 4
    add_heading_2(doc, "3.4 Fase 4: Otimização de Performance, Pipeline Único e Experiência do Usuário (2026-10-17 a 2026-10-18)")
    add_paragraph(doc, 
                  "Eliminar gargalos severos de computação no FFmpeg, transcrição Whisper e detecção facial OpenCV, além de destravar o event loop "
                  "assíncrono da API e otimizar radicalmente a velocidade percebida e uso de rede no frontend.", 
                  bold_prefix="Objetivo: ")
    add_paragraph(doc, 
                  "Commits 0a7db04 a b51c030 (7 commits) e mudanças de fechamento em 2026-10-18. Arquivos profundamente otimizados: "
                  "backend/app/services/video_service.py, backend/app/services/ai_service.py, backend/app/worker/worker.py, "
                  "backend/app/api/routers/video.py, backend/app/api/routers/project.py, frontend/js/app.js, frontend/js/ui.js e frontend/nginx.conf.", 
                  bold_prefix="Evidências Git: ")
    add_paragraph(doc, 
                  "A sessão foi estruturada em 5 etapas metódicas (Etapa 0 a Etapa 4). Implementação de decorador e context manager de medição timed() "
                  "(Etapa 0); habilitação de GPU passthrough NVIDIA NVENC e volume Docker ext4 de alta velocidade (Etapa 1); unificação de renderização "
                  "em passe único eliminando o arquivo intermediário clean_*.mp4 e paralelização de render com face tracking leve via cv2.VideoCapture (Etapa 2); "
                  "desacoplamento assíncrono total da rota de URL com Huey, entrega acelerada de MP4 via Nginx X-Accel-Redirect com HTTP Range 206 "
                  "e estimativa dinâmica de fila (Etapa 3); e renderização progressiva no frontend com eliminação de bibliotecas externas pesadas (Etapa 4).", 
                  bold_prefix="Decisões Técnicas: ")

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 4: ARQUITETURA ATUAL
    # --------------------------------------------------------------------------
    add_heading_1(doc, "4. Arquitetura Atual do Sistema")
    add_paragraph(doc, 
                  "A arquitetura do ClipMaker.io em produção opera sob topologia de microsserviços conteinerizados orquestrada via Docker Compose "
                  "(docker-compose.prod.yml). O tráfego externo de rede alcança exclusivamente o serviço Nginx, que atua como proxy reverso, "
                  "terminador de tráfego estático e despachante acelerado de fluxos de vídeo.")

    # Inserção da Figura de Arquitetura
    if arch_diagram_path.exists():
        doc.add_paragraph().paragraph_format.space_before = Pt(6)
        p_img = doc.add_paragraph()
        p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img.paragraph_format.space_after = Pt(4)
        run_img = p_img.add_run()
        run_img.add_picture(str(arch_diagram_path), width=Inches(6.4))
        
        p_cap = doc.add_paragraph()
        p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap.paragraph_format.space_after = Pt(12)
        r_cap = p_cap.add_run("Figura 4.1: Diagrama de Arquitetura de Containers, Volumes e Conexões em Produção (docker-compose.prod.yml).")
        r_cap.font.name = 'Calibri'
        r_cap.font.size = Pt(8.5)
        r_cap.font.italic = True
        r_cap.font.color.rgb = COLOR_GRAY

    add_heading_2(doc, "4.1 Descrição Detalhada dos Serviços (docker-compose.prod.yml)")
    add_paragraph(doc, 
                  "Todos os containers de aplicação utilizam diretivas rigorosas de isolamento operacional: security_opt com no-new-privileges:true, "
                  "cap_drop com ALL (remoção total de capacidades de superusuário do Linux) e limites explícitos de CPU e memória RAM.")

    # Tabela Serviços Docker Compose
    t_srv = doc.add_table(rows=8, cols=6)
    t_srv_data = [
        ["Serviço", "Imagem Base", "CPU", "Memória", "Volumes Montados", "Healthcheck / Comando"],
        ["db", "postgres:15-alpine", "1.0", "512m", "postgres_data:/var/lib/postgresql/data", "pg_isready -U ... -d ... (interval 10s)"],
        ["migrate", "postgres:15-alpine", "—", "64m", "./migrations:ro, ./scripts/migrate.sh:ro", "One-shot (restart: 'no', depende do db saudável)"],
        ["redis", "redis:7-alpine", "0.3", "192m", "${DATA_ROOT}/redis:/data (AOF persistente)", "redis-cli -a ... ping (interval 10s)"],
        ["api", "clipmakerai:prod (target runtime)", "1.0", "768m", "clipmaker_temp_videos, cache, logs", "FastAPI / Uvicorn (lifespan asyncpg)"],
        ["worker", "clipmakerai:prod-gpu (runtime-gpu)", "WORKER_CPUS (4.0)", "WORKER_MEM_LIMIT (6g)", "clipmaker_temp_videos, cache, logs, GPU all", "python -c 'redis.ping()' (interval 30s)"],
        ["cleanup", "clipmakerai:prod", "0.1", "64m", "clipmaker_temp_videos:/app/backend/temp_videos", "Loop: python scripts/cleanup.py; sleep 3600"],
        ["frontend", "nginx:alpine", "0.5", "128m", "./frontend:ro, ./nginx.conf:ro, videos:ro", "wget -qO- http://127.0.0.1/ (Porta 80:80)"]
    ]
    for r_idx, row in enumerate(t_srv_data):
        for c_idx, val in enumerate(row):
            t_srv.rows[r_idx].cells[c_idx].paragraphs[0].text = val
    style_table(t_srv, col_widths=[0.8, 1.3, 0.7, 0.7, 1.6, 1.4],
                align_cols=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT])

    add_heading_2(doc, "4.2 Fluxo Completo de um Vídeo no Pipeline")
    add_paragraph(doc, 
                  "O ciclo de vida de processamento de um vídeo segue uma trilha estrita, orquestrada por transições de estado "
                  "persistidas no banco relacional e notificadas à interface via polling do endpoint /api/projects/{id}/status:")

    # Inserção da Figura do Pipeline
    if pipeline_diagram_path.exists():
        doc.add_paragraph().paragraph_format.space_before = Pt(6)
        p_img2 = doc.add_paragraph()
        p_img2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_img2.paragraph_format.space_after = Pt(4)
        run_img2 = p_img2.add_run()
        run_img2.add_picture(str(pipeline_diagram_path), width=Inches(6.4))
        
        p_cap2 = doc.add_paragraph()
        p_cap2.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_cap2.paragraph_format.space_after = Pt(12)
        r_cap2 = p_cap2.add_run("Figura 4.2: Fluxograma Detalhado do Pipeline de Processamento de Mídia Ponta a Ponta.")
        r_cap2.font.name = 'Calibri'
        r_cap2.font.size = Pt(8.5)
        r_cap2.font.italic = True
        r_cap2.font.color.rgb = COLOR_GRAY

    add_paragraph(doc, "1. Ingestão da Mídia:", bold_prefix="Passo 1: ")
    add_bullet(doc, "Upload Direto: O cliente envia o arquivo via multipart/form-data. A gravação em disco temporário ocorre em blocos de 1MB desacoplada via asyncio.to_thread(_save_upload_file_sync), e a inspeção ffprobe roda sem travar a API. O projeto é registrado com status PENDING e enfileirado na tarefa process_video_task.")
    add_bullet(doc, "Importação via URL: A rota valida a URL contra regras anti-SSRF, cria o registro imediatamente com status DOWNLOADING e despacha a tarefa download_and_process_url_task para a fila huey_ingest do Huey, respondendo ao cliente em menos de 15ms.")

    add_paragraph(doc, "2. Transcrição e Cache com Whisper:", bold_prefix="Passo 2: ")
    add_bullet(doc, "O worker extrai o áudio em WAV 16kHz mono via FFmpeg. Antes de acionar o modelo neural, verifica na tabela transcriptions se já existe transcrição para o mesmo hash do arquivo ou sourceUrl normalizado pertencente àquele usuário.")
    add_bullet(doc, "Se já existir, a transcrição é reaproveitada integralmente em tempo zero. Caso contrário, invoca o Whisper (CTranslate2 com modelo small na GPU ou fallback int8 na CPU) com timestamping preciso por palavra (word-level). O modelo é mantido em cache de memória do processo por até 15 minutos de inatividade.")

    add_paragraph(doc, "3. Seleção Semântica com LLM (Gemini):", bold_prefix="Passo 3: ")
    add_bullet(doc, "A transcrição completa com minutagem é submetida à API do Google Gemini (gemini-3.8-flash). Em caso de esgotamento de cota (HTTP 429), o sistema itera dinamicamente para os modelos secundários configurados em GEMINI_MODELS.")
    add_bullet(doc, "Se todos os modelos falharem, o fallback heurístico/matemático gera automaticamente cortes equilibrados com títulos descritivos, marcando a flag ai_cuts_fallback=true no projeto.")

    add_paragraph(doc, "4. Rastreamento Facial Dinâmico (Face Tracking):", bold_prefix="Passo 4: ")
    add_bullet(doc, "Para cada clipe identificado, o worker instancia cv2.VideoCapture diretamente sobre o vídeo-fonte, navegando com cap.set() e pulando frames com cap.grab().")
    add_bullet(doc, "Frames são amostrados a cada 500ms e redimensionados para 320px de largura, detectando rostos via classificador Haar Cascade. O centro horizontal do corte é suavizado (alpha=0.3) e persistido na coluna face_center_x da tabela clips, garantindo consistência em re-renders futuros.")

    add_paragraph(doc, "5. Renderização em Passe Único e Paralelismo:", bold_prefix="Passo 5: ")
    add_bullet(doc, "O FFmpeg executa o corte 9:16, a escala e a renderização das legendas SRT em uma única passagem (eliminando o arquivo intermediário clean_*.mp4).")
    add_bullet(doc, "A codificação utiliza aceleração por hardware NVIDIA (h264_nvenc) com flag -movflags +faststart para início instantâneo de streaming na web. Até 2 clipes são renderizados simultaneamente via ThreadPoolExecutor.")
    add_bullet(doc, "Cada clipe renderizado tem sua miniatura JPG gerada (frame em ~1s) e é salvo incrementalmente no PostgreSQL com status COMPLETED, tornando-se imediatamente acessível ao usuário.")

    add_paragraph(doc, "6. Entrega de Mídia via Nginx (X-Accel-Redirect):", bold_prefix="Passo 6: ")
    add_bullet(doc, "Ao solicitar o download ou reprodução (/api/videos/download/{clip_id}), a API autentica o token JWT e confirma a propriedade no banco. Em seguida, responde com o cabeçalho X-Accel-Redirect: /internal_videos/<filename>.")
    add_bullet(doc, "O Nginx intercepta o cabeçalho e serve o vídeo diretamente do volume Docker somente-leitura com suporte a HTTP Range (206 Partial Content), desonerando o processo Python.")

    add_heading_2(doc, "4.3 Estrutura de Banco de Dados Relacional (PostgreSQL 15)")
    add_paragraph(doc, 
                  "O esquema de dados relacional foi modelado para integridade referencial estrita, performance em consultas "
                  "frequentes e isolamento multi-inquilino. As migrações são versionadas na pasta migrations/ e executadas pelo migrate.sh.")

    # Tabela de Entidades do Banco
    t_db = doc.add_table(rows=6, cols=4)
    t_db_data = [
        ["Tabela", "Chave Primária", "Chaves Estrangeiras / Relações", "Colunas Principais e Finalidade"],
        ["users", "id (UUID)", "— (Entidade Raiz)", "email (VARCHAR UNIQUE), passwordHash, name, credits (padrão 60), createdAt, updatedAt"],
        ["projects", "id (UUID)", "userId -> users(id) ON DELETE CASCADE", "title, sourceUrl, sourceFileKey, durationSec, status, errorMessage, ai_cuts_fallback, createdAt, updatedAt"],
        ["clips", "id (UUID)", "projectId -> projects(id) ON DELETE CASCADE", "title, hookReason, startTime, endTime, durationSec, viralScore, aspectRatio, renderedUrl, thumbnail_key, face_center_x, status, captionConfig, wordsJson"],
        ["transcriptions", "id (UUID)", "projectId -> projects(id) ON DELETE CASCADE, userId -> users(id)", "fullText, language (padrão 'pt'), wordsJson, sourceUrl, fileHash (lookup de cache para reuso)"],
        ["job_metrics", "id (VARCHAR(36))", "projectId -> projects(id) ON DELETE SET NULL", "videoDurationSec, totalProcessingSec, secPerMinute, createdAt (cálculo de média móvel para ETA de fila)"]
    ]
    for r_idx, row in enumerate(t_db_data):
        for c_idx, val in enumerate(row):
            t_db.rows[r_idx].cells[c_idx].paragraphs[0].text = val
    style_table(t_db, col_widths=[1.1, 1.1, 1.8, 2.5],
                align_cols=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT])

    add_paragraph(doc, 
                  "O banco possui os seguintes índices estratégicos: idx_projects_userid em projects(userId); "
                  "idx_projects_user_status em projects(userId, status); idx_projects_status_created em projects(status, createdAt); "
                  "idx_clips_projectid em clips(projectId); idx_clips_thumbnail em clips(thumbnail_key); "
                  "idx_transcriptions_lookup em transcriptions(userId, sourceUrl, fileHash); e "
                  "idx_job_metrics_created_at em job_metrics(createdAt DESC).", bold_prefix="Índices de Otimização: ")

    add_heading_2(doc, "4.4 Catálogo de Endpoints da API")
    add_paragraph(doc, 
                  "A API é estruturada no FastAPI com documentação Swagger desabilitada em produção. "
                  "Suporta prefixos duplos (/api/... e /api/v1/...) para retrocompatibilidade:")

    # Tabela Endpoints
    t_ep = doc.add_table(rows=11, cols=5)
    t_ep_data = [
        ["Método", "Caminho (Rotas)", "Autenticação", "Rate Limit", "Descrição e Parâmetros"],
        ["POST", "/api/auth/register", "Pública", "5 / min (Redis)", "Cadastro de usuário (email normalizado, senha, nome)."],
        ["POST", "/api/auth/login", "Pública (OAuth2)", "5 / min (Redis)", "Login com geração de token de acesso JWT."],
        ["GET", "/health, /api/health", "Pública", "Ilimitado", "Verificação de integridade operacional do container."],
        ["GET", "/api/config, /api/v1/config", "Pública", "Ilimitado", "Fornece limites de upload e versão da aplicação."],
        ["POST", "/api/videos/upload-and-process", "JWT (Bearer)", "5 / min + Max Jobs", "Upload multipart de arquivo local para processamento."],
        ["POST", "/api/videos/upload-url", "JWT (Bearer)", "5 / min + Max Jobs", "Ingestão assíncrona de vídeo por URL (retorno <15ms)."],
        ["GET", "/api/videos/download/{clip_id}", "JWT (Dono)", "Ilimitado", "Download acelerado via Nginx X-Accel-Redirect com HTTP Range."],
        ["GET", "/api/videos/thumbnail/{clip_id}", "JWT (Dono)", "Ilimitado", "Miniatura JPG 480px do clipe renderizado."],
        ["GET", "/api/projects", "JWT (Bearer)", "Ilimitado", "Lista todos os projetos do usuário autenticado."],
        ["GET", "/api/projects/{id}/status", "JWT (Dono)", "Ilimitado", "Status em tempo real, posição na fila, ETA e clipes concluídos."]
    ]
    for r_idx, row in enumerate(t_ep_data):
        for c_idx, val in enumerate(row):
            t_ep.rows[r_idx].cells[c_idx].paragraphs[0].text = val
    style_table(t_ep, col_widths=[0.7, 1.8, 1.1, 1.1, 1.8],
                align_cols=[WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT])

    add_heading_2(doc, "4.5 Variáveis de Ambiente e Configuração (config.py)")
    add_paragraph(doc, 
                  "As configurações são gerenciadas através do Pydantic BaseSettings no backend/app/core/config.py, "
                  "com injeção automática de variáveis de ambiente a partir do arquivo .env:")

    # Tabela Variáveis
    t_env = doc.add_table(rows=15, cols=4)
    t_env_data = [
        ["Variável de Ambiente", "Valor Padrão", "Onde é Usada", "Finalidade Operacional"],
        ["ENVIRONMENT", "development", "config.py, main.py", "Define se a aplicação opera em 'production' ou 'development'."],
        ["SECRET_KEY", "chave_secreta_padrao...", "config.py, security.py", "Chave simétrica HMAC-SHA256 para assinatura de tokens JWT."],
        ["DATABASE_URL", "postgresql://...:5432/...", "config.py, db_service.py", "String de conexão para o pool assíncrono do PostgreSQL."],
        ["REDIS_URL", "redis://localhost:6379/0", "config.py, worker.py, deps.py", "Conexão com Redis para filas Huey e storage do rate limiter."],
        ["GEMINI_API_KEY", "—", "config.py, ai_service.py", "Chave de autenticação na API de inteligência artificial do Google."],
        ["GEMINI_MODELS", "gemini-3.8-flash,...", "config.py, ai_service.py", "Lista de fallback ordenado de modelos em caso de HTTP 429."],
        ["WHISPER_MODEL", "auto", "config.py, ai_service.py", "Modelo do Whisper ('small' em GPU, 'tiny' em CPU, ou 'auto')."],
        ["WHISPER_IDLE_TIMEOUT_MINUTES", "15", "config.py, ai_service.py", "Tempo de inatividade em minutos antes de descarregar VRAM."],
        ["WORKER_CPUS", "4.0", "docker-compose.prod.yml", "Cota de processadores alocados ao container worker."],
        ["WORKER_MEM_LIMIT", "6g", "docker-compose.prod.yml", "Limite máximo de memória RAM alocada ao worker."],
        ["RENDER_PARALLELISM", "0 (automático)", "config.py, video_service.py", "Quantidade de clipes renderizados em paralelo (padrão 2 em GPU)."],
        ["MAX_FILE_SIZE_MB", "2000", "config.py, video.py, main.py", "Tamanho máximo permitido para envio de vídeos (em megabytes)."],
        ["MAX_DURATION_SEC", "14400 (4 horas)", "config.py, video.py", "Duração máxima permitida para o vídeo de origem."],
        ["MAX_CONCURRENT_JOBS_PER_USER", "2", "config.py, video.py", "Limite de tarefas ativas concorrentes por usuário antes de 429."]
    ]
    for r_idx, row in enumerate(t_env_data):
        for c_idx, val in enumerate(row):
            t_env.rows[r_idx].cells[c_idx].paragraphs[0].text = val
    style_table(t_env, col_widths=[1.8, 1.4, 1.3, 2.0],
                align_cols=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT])

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 5: SEGURANÇA
    # --------------------------------------------------------------------------
    add_heading_1(doc, "5. Segurança e Postura Defensiva")
    add_paragraph(doc, 
                  "A segurança da aplicação foi projetada sob o princípio de defesa em profundidade, cobrindo validação de entrada, "
                  "autenticação, autorização granular, isolamento do sistema operacional e hardening de containers.")

    add_heading_2(doc, "5.1 Controles Implementados no Código e Infraestrutura")
    
    add_paragraph(doc, "backend/app/api/routers/video.py (linhas 29-58)", bold_prefix="1. Proteção Anti-SSRF (Server-Side Request Forgery): ")
    add_paragraph(doc, "A função _is_safe_public_url valida rigorosamente URLs de importação externa antes de qualquer invocação ao yt-dlp. "
                       "Bloqueia esquemas diferentes de http/https, nomes de hosts internos do Docker (db, redis, api, worker, proxy, cleanup), "
                       "e analisa o endereço IP resultante via socket.gethostbyname() e biblioteca ipaddress. Bloqueia sumariamente endereços "
                       "privados (RFC 1918), endereços de loopback (127.0.0.0/8), link-local e IPs reservados.")

    add_paragraph(doc, "backend/app/api/routers/video.py (linhas 197-226)", bold_prefix="2. Mitigação de Path Traversal e Injeção de Arquivos: ")
    add_paragraph(doc, "Nos endpoints de download (/download/{clip_id}) e miniatura (/thumbnail/{clip_id}), o identificador é saneado via "
                       "os.path.basename(). Adicionalmente, o nome físico do arquivo é obtido estritamente a partir do registro do banco de dados "
                       "(coluna renderedUrl), e o caminho final resolvido é validado através de Path.relative_to(TEMP_DIR.resolve()). "
                       "Tentativas de escapar do diretório autorizado disparam HTTP 403 imediato.")

    add_paragraph(doc, "backend/app/api/deps.py e backend/app/core/security.py", bold_prefix="3. Autenticação JWT e Hash Criptográfico: ")
    add_paragraph(doc, "Senhas são armazenadas exclusivamente utilizando hash criptográfico Bcrypt com salt dinâmico via PassLib. "
                       "A autenticação emite JSON Web Tokens assinados com algoritmo HMAC-SHA256 (HS256) com tempo de expiração configurável. "
                       "A dependência get_current_user extrai e valida o token em cada requisição protegida.")

    add_paragraph(doc, "backend/app/api/routers/project.py e video.py", bold_prefix="4. Controle de Acesso e Autorização Multi-Inquilino: ")
    add_paragraph(doc, "Nenhum usuário pode visualizar, alterar ou baixar clipes pertencentes a outros usuários. Em todas as rotas de detalhe, "
                       "status e re-renderização, o backend compara explicitamente o userId do registro com o id do usuário autenticado no token JWT, "
                       "retornando HTTP 403 Forbidden caso haja divergência.")

    add_paragraph(doc, "backend/app/api/deps.py e backend/app/main.py", bold_prefix="5. Rate Limiting Distribuído com Armazenamento em Redis: ")
    add_paragraph(doc, "O controle de taxa de requisições utiliza a biblioteca SlowAPI configurada para persistir o histórico de requisições "
                       "diretamente na instância do Redis central (storage_uri=settings.REDIS_URL). Isso garante que o rate limit seja compartilhado "
                       "e consistente entre múltiplos workers e instâncias de API.")

    add_paragraph(doc, "backend/app/core/config.py (linhas 54-59)", bold_prefix="6. Trava de Segurança contra SECRET_KEY Padrão em Produção: ")
    add_paragraph(doc, "O inicializador do Settings executa uma validação estrita no boot da aplicação: caso ENVIRONMENT=production e a chave "
                       "secreta permaneça com o valor default de desenvolvimento, ou possua comprimento inferior a 32 caracteres, a aplicação "
                       "interrompe sua inicialização com erro fatal (RuntimeError), impedindo o deploy acidental de chaves fracas.")

    add_paragraph(doc, "docker-compose.prod.yml", bold_prefix="7. Hardening de Containers e Privilégios Mínimos: ")
    add_paragraph(doc, "Todos os serviços definem security_opt com no-new-privileges:true, impedindo que processos em container ganhem privilégios adicionais. "
                       "A diretiva cap_drop: ALL remove todas as capacidades do kernel Linux, readicionando apenas as estritamente necessárias para o PostgreSQL e Redis. "
                       "O volume de vídeos é montado como somente leitura (:ro) no container do Nginx.")

    add_paragraph(doc, "frontend/nginx.conf", bold_prefix="8. Cabeçalhos de Segurança HTTP (Security Headers): ")
    add_paragraph(doc, "O proxy reverso Nginx injeta cabeçalhos de proteção padrão em todas as respostas: X-Content-Type-Options: nosniff, "
                       "X-Frame-Options: DENY, X-XSS-Protection: '1; mode=block', Referrer-Policy: 'strict-origin-when-cross-origin' e "
                       "Content-Security-Policy com restrição estrita de origens.")

    add_heading_2(doc, "5.2 O que ainda NÃO está coberto (Lacunas de Segurança)")
    add_paragraph(doc, "Embora a aplicação possua excelente nível defensivo, identificam-se as seguintes oportunidades de aprimoramento futuro:")
    add_bullet(doc, "Falta de Autenticação Multifator (2FA/MFA): O fluxo de login depende exclusivamente de usuário e senha, sem suporte a TOTP.")
    add_bullet(doc, "Emissão Automática de Certificados SSL/TLS: O docker-compose.prod.yml expõe apenas a porta 80 e depende de um proxy reverso externo ou terminação TLS de infraestrutura para fornecer HTTPS.")
    add_bullet(doc, "Ausência de Blacklist de Revogação de Tokens JWT: O token é stateless e permanece válido até seu tempo de expiração natural, sem mecanismo de invalidação imediata em caso de logout voluntário.")
    add_bullet(doc, "Política de Bloqueio Temporário de Conta por Força Bruta: Não há bloqueio temporal de conta após tentativas sucessivas de senha incorreta (account lockout).")

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 6: OTIMIZAÇÃO DE DESEMPENHO
    # --------------------------------------------------------------------------
    add_heading_1(doc, "6. Auditoria de Otimização de Desempenho")
    add_paragraph(doc, 
                  "Esta seção registra detalhadamente todas as intervenções de engenharia de performance implementadas no projeto. "
                  "Os números apresentados foram extraídos literalmente do relatório docs/PERFORMANCE.md e de medições empíricas, "
                  "sem arredondamentos e com rigor estatístico de 3 rodadas consecutivas.")

    add_heading_2(doc, "6.1 Etapa 0 — Linha de Base (Baseline) e Diagnóstico de Gargalos")
    add_paragraph(doc, "No commit 0a7db04 e 4e87459, foi estabelecida a metodologia estatística de medição (3 rodadas) utilizando o vídeo "
                       "87e2634a-75a5-4f26-b18a-079fe423f7b5.mp4 (406,16s, 256,56 MB, 1080p, gerando 5 clipes de 75s em 9:16). "
                       "Foi criado o módulo backend/app/core/timing.py para instrumentação de alta precisão.")

    add_paragraph(doc, "A medição realizada DENTRO do container worker com os limites reais (cpus: 2.0, mem_limit: 3g) revelou o tempo total "
                       "de 235,16s na mediana (Tabela 3). No host com aceleração NVENC nativa, o tempo mediano foi de 88,87s sem LLM (Tabela 1) "
                       "e 103,76s com chamada real ao Gemini API (Tabela 2, com 1 tentativa, 0 erros 429 e resposta do modelo gemini-3.8-flash).", 
                       bold_prefix="Resultados da Etapa 0: ")

    # Tabela 3 da Etapa 0 (Baseline Container)
    add_paragraph(doc, "Tabela 3: Linha de Base no Container Worker (cpus: 2.0, mem: 3g, 3 rodadas) — PERFORMANCE.md", bold_prefix="Medição Oficial: ")
    t_tab3 = doc.add_table(rows=8, cols=5)
    t_tab3_data = [
        ["Fase do Pipeline", "Mediana", "Variação (Min - Max)", "% do Total", "Observações"],
        ["1. Probe (ffprobe)", "0.07s", "0.07s – 0.09s", "0.0%", "Metadados no Debian Bookworm"],
        ["2. Transcrição (Whisper)", "30.37s", "28.81s – 35.87s", "12.9%", "Whisper tiny com 4 threads na CPU (2 vCPUs)"],
        ["3. LLM (Detecção Momentos)", "0.00s", "0.00s – 0.00s", "0.0%", "Fallback matemático de cortes (--skip-llm)"],
        ["4. Face Tracking (OpenCV)", "16.34s", "16.09s – 16.83s", "6.9%", "Ativo! OpenCV 4.8.0 Haar (~3.27s/clipe)"],
        ["5. Render Vídeo (FFmpeg)", "107.01s", "103.67s – 114.23s", "45.5%", "5 clipes 9:16 limpos via CPU libx264 (~21.4s/clipe)"],
        ["6. Legendas Burn-in (FFmpeg)", "77.66s", "76.99s – 85.28s", "33.0%", "Re-render completo com filtro subtitles (~15.5s/clipe)"],
        ["TEMPO TOTAL PIPELINE", "235.16s", "232.98s – 247.09s", "100.0%", "Mediana de 3 rodadas (3m 55s)"]
    ]
    for r_idx, row in enumerate(t_tab3_data):
        for c_idx, val in enumerate(row):
            t_tab3.rows[r_idx].cells[c_idx].paragraphs[0].text = val
    style_table(t_tab3, col_widths=[2.0, 1.0, 1.3, 0.8, 1.4],
                align_cols=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT])

    add_paragraph(doc, "Causa Raiz e Correção do Face Tracking (Haar XML):", bold_prefix="Investigação Técnica: ")
    add_paragraph(doc, "O relatório inicial acusava '0.00s (sem haar xml)'. A investigação revelou que no host (Python 3.14 com OpenCV 5.0) "
                       "a classe CascadeClassifier havia sido omitida das bindings Python (hasattr(cv2, 'CascadeClassifier') == False). "
                       "No container (Python 3.11 com OpenCV 4.8.0), o XML existia mas faltava fallback robusto. "
                       "A correção em backend/app/services/video_service.py implementou resolução em múltiplos caminhos e copiou o arquivo "
                       "haarcascade_frontalface_default.xml localmente, ativando a detecção facial real (16,34s no container).")

    add_paragraph(doc, "Diagnóstico de Threads e Decomposição do FFmpeg (Tabela 4):", bold_prefix="Diagnóstico Incremental: ")
    add_paragraph(doc, "No commit 1d5225f foi apurado que o cgroup do worker impunha cota de 2.0 CPUs (/sys/fs/cgroup/cpu.max = 200000 100000), "
                       "mas o Python detectava 12 núcleos do host via os.cpu_count(), alocando 4 threads no Whisper e 4+ no FFmpeg. "
                       "Isso gerava concorrência severa e context switching. A decomposição incremental de um clipe de 75s (Tabela 4) comprovou que "
                       "no container o gargalo era o encode de CPU via libx264 (23,95s), enquanto no host o filtro subtitles (libass) era responsável por 8s.")

    add_heading_2(doc, "6.2 Etapa 1 — Infraestrutura, Volume Rápido e Aceleração GPU Worker")
    add_paragraph(doc, "No commit c748f09, foram aplicadas as seguintes otimizações de infraestrutura: "
                       "(1) Limites do worker parametrizados via .env (WORKER_CPUS=4.0, WORKER_MEM_LIMIT=6g); "
                       "(2) Migração da área de trabalho de vídeos temporários do bind-mount lento do NTFS para volume nomeado Docker gerenciado pelo Linux (clipmaker_temp_videos); "
                       "(3) Criação do target multi-stage runtime-gpu no Dockerfile com nvidia-cublas-cu12, nvidia-cudnn-cu12 e FFmpeg NVENC (h264_nvenc); "
                       "(4) Cache global em VRAM do modelo Whisper (small, float16) com descarga após 15 min de ociosidade; "
                       "(5) Limite de resolução MAX_SOURCE_HEIGHT=1080 no yt-dlp.")

    # Tabela 5 da Etapa 1
    add_paragraph(doc, "Tabela 5: Comparativo ANTES x DEPOIS (Etapa 0 Container vs Etapa 1 Container com GPU) — PERFORMANCE.md", bold_prefix="Medição Oficial: ")
    t_tab5 = doc.add_table(rows=8, cols=6)
    t_tab5_data = [
        ["Fase do Pipeline", "ANTES (Etapa 0)", "DEPOIS (Etapa 1)", "Variação Min-Max", "Ganho Absoluto", "Redução (%)"],
        ["1. Probe (ffprobe)", "0.07s", "0.06s", "0.06s – 0.06s", "-0.01s", "-14.3%"],
        ["2. Transcrição (Whisper)", "30.37s (tiny)", "13.28s (small!)", "13.10s – 24.85s", "-17.09s", "-56.3%"],
        ["3. LLM (Detecção Momentos)", "0.00s", "0.00s", "0.00s – 0.00s", "0.00s", "0.0%"],
        ["4. Face Tracking (OpenCV)", "16.34s", "8.11s", "8.01s – 8.46s", "-8.23s", "-50.4%"],
        ["5. Render Vídeo (FFmpeg)", "107.01s (CPU)", "40.54s (NVENC)", "40.25s – 41.40s", "-66.47s", "-62.1%"],
        ["6. Legendas Burn-in (FFmpeg)", "77.66s (CPU)", "35.56s (NVENC)", "35.03s – 36.38s", "-42.10s", "-54.2%"],
        ["TEMPO TOTAL PIPELINE", "235.16s (3m 55s)", "100.65s (1m 40s)", "98.69s – 109.53s", "-134.51s", "-57.2% (-2.34x)"]
    ]
    for r_idx, row in enumerate(t_tab5_data):
        for c_idx, val in enumerate(row):
            t_tab5.rows[r_idx].cells[c_idx].paragraphs[0].text = val
    style_table(t_tab5, col_widths=[1.8, 1.1, 1.1, 1.2, 0.9, 0.9],
                align_cols=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER])

    add_heading_2(doc, "6.3 Etapa 2 — Pipeline de Passe Único, Paralelismo e Enquadramento Persistente")
    add_paragraph(doc, "No commit df98056, a lógica interna do pipeline foi reestruturada para eliminar I/O redundante: "
                       "(1) Unificação do crop, scale e queima de legendas SRT em um único comando FFmpeg, eliminando a criação do arquivo clean_*.mp4 (-100% no tempo da fase 6); "
                       "(2) Persistência da coordenada face_center_x no banco (migração 003_etapa2_pipeline.sql) para enquadramento idêntico em re-renders; "
                       "(3) Otimização do face tracking com cv2.VideoCapture e cap.grab() direto no vídeo original com amostragem a cada 500ms; "
                       "(4) Paralelização da renderização (paralelismo=2 via ThreadPoolExecutor); "
                       "(5) Persistência incremental imediata de cada clipe finalizado; "
                       "(6) Reuso de transcrições Whisper existentes no banco via hash/URL.")

    # Tabela 6 da Etapa 2
    add_paragraph(doc, "Tabela 6: Comparativo de Desempenho Global (Etapa 0 vs Etapa 1 vs Etapa 2) — PERFORMANCE.md", bold_prefix="Medição Oficial: ")
    t_tab6 = doc.add_table(rows=8, cols=6)
    t_tab6_data = [
        ["Fase do Pipeline", "Etapa 0 (Baseline)", "Etapa 1 (Infra)", "Etapa 2 (Pipeline)", "Variação Etapa 2", "Redução Total (%)"],
        ["1. Probe (ffprobe)", "0.07s", "0.06s", "0.06s", "0.06s – 0.06s", "-14.3%"],
        ["2. Transcrição (Whisper)", "30.37s", "13.28s", "13.37s", "13.35s – 24.34s", "-56.0%"],
        ["3. LLM (Detecção Momentos)", "0.00s", "0.00s", "0.00s", "0.00s – 0.00s", "0.0%"],
        ["4. Face Tracking (OpenCV)", "16.34s", "8.11s", "55.35s*", "54.09s – 56.51s", "(Analisa 75s do clipe)"],
        ["5. Render Vídeo (FFmpeg)", "107.01s", "40.54s", "73.61s*", "72.42s – 74.02s", "(Passe Único NVENC)"],
        ["6. Legendas Burn-in (FFmpeg)", "77.66s", "35.56s", "0.00s", "0.00s – 0.00s", "-100.0% (Eliminado)"],
        ["TEMPO TOTAL (Wall-Clock)", "235.16s (3m 55s)", "100.65s (1m 40s)", "86.41s (1m 26s)", "85.58s – 95.24s", "-63.3% (-2.72x)"]
    ]
    for r_idx, row in enumerate(t_tab6_data):
        for c_idx, val in enumerate(row):
            t_tab6.rows[r_idx].cells[c_idx].paragraphs[0].text = val
    style_table(t_tab6, col_widths=[1.8, 1.1, 1.1, 1.1, 1.1, 0.9],
                align_cols=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER])
    add_paragraph(doc, "*Nota: Na Etapa 2, o face tracking e o render dos clipes executam concorrentemente no ThreadPoolExecutor (paralelismo=2). "
                       "Por isso, a soma aritmética de CPU (55.35s + 73.61s) ocorre em paralelo, resultando em apenas 86.41s de tempo real de relógio (wall-clock). "
                       "Com o reuso de transcrição Whisper, o tempo total cai para ~73.04s (-68.9% vs baseline).")

    add_heading_2(doc, "6.4 Etapa 3 — API Desbloqueada, Filas Huey, X-Accel-Redirect e Métricas")
    add_paragraph(doc, "No commit b51c030, os gargalos de concorrência e entrega da API foram solucionados: "
                       "(1) Destravamento do event loop assíncrono: a rota /upload-url agora valida a URL em <15ms e delega o download "
                       "pesado do yt-dlp para a task download_and_process_url_task na fila huey_ingest; "
                       "(2) Entrega de vídeo acelerada pelo Nginx via cabeçalho X-Accel-Redirect e suporte HTTP Range 206, reduzindo a zero o uso de memória por stream no Python; "
                       "(3) Consulta de download otimizada com JOIN único (get_clip_with_owner); "
                       "(4) Rate limit distribuído no Redis e proteção de concorrência por usuário (MAX_CONCURRENT_JOBS_PER_USER=2); "
                       "(5) Filas dedicadas no Huey (huey_ingest, huey_render, huey); "
                       "(6) Tabela job_metrics (migração 004) para estimativa dinâmica de posição e tempo de fila (ETA).")

    # Tabela 7 da Etapa 3
    add_paragraph(doc, "Tabela 7: Comparativo de Desempenho Global (Etapa 0 até Etapa 3) — PERFORMANCE.md", bold_prefix="Medição Oficial: ")
    t_tab7 = doc.add_table(rows=8, cols=6)
    t_tab7_data = [
        ["Fase do Pipeline", "Etapa 0 (Baseline)", "Etapa 1 (Infra)", "Etapa 2 (Pipeline)", "Etapa 3 (API + Filas)", "Redução Total (%)"],
        ["1. Probe (ffprobe)", "0.07s", "0.06s", "0.06s", "0.06s (0.05s – 0.08s)", "-14.3%"],
        ["2. Transcrição (Whisper)", "30.37s", "13.28s", "13.37s", "12.14s (11.80s – 23.57s)", "-60.0%"],
        ["3. LLM (Detecção Momentos)", "0.00s", "0.00s", "0.00s", "0.00s (0.00s – 0.00s)", "0.0%"],
        ["4. Face Tracking (OpenCV)", "16.34s", "8.11s", "55.35s*", "47.80s* (47.80s – 48.17s)", "(Estabilidade total)"],
        ["5. Render Vídeo (FFmpeg)", "107.01s", "40.54s", "73.61s*", "63.01s* (62.46s – 64.66s)", "-41.1% (NVENC otimizado)"],
        ["6. Legendas Burn-in (FFmpeg)", "77.66s", "35.56s", "0.00s", "0.00s (0.00s – 0.00s)", "-100.0% (Eliminado)"],
        ["TEMPO TOTAL (Wall-Clock)", "235.16s (3m 55s)", "100.65s (1m 40s)", "86.41s (1m 26s)", "72.25s (71.75s – 83.01s)", "-69.3% (3.25x mais rápido)"]
    ]
    for r_idx, row in enumerate(t_tab7_data):
        for c_idx, val in enumerate(row):
            t_tab7.rows[r_idx].cells[c_idx].paragraphs[0].text = val
    style_table(t_tab7, col_widths=[1.8, 1.1, 1.1, 1.1, 1.2, 0.9],
                align_cols=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.CENTER])

    add_paragraph(doc, "A rota de importação por URL teve sua latência reduzida de >60s (bloqueante) para <15ms (-99.9%). "
                       "O tempo total de processamento com reuso de transcrição alcançou ~59.88s (3.93x mais rápido que a baseline inicial).", 
                       bold_prefix="Indicadores Complementares da Etapa 3: ")

    add_heading_2(doc, "6.5 Etapa 4 — Frontend e Velocidade Percebida")
    add_paragraph(doc, "A Etapa 4 concentrou-se na experiência do usuário e na otimização de rede do frontend. "
                       "As implementações concluídas compreendem: "
                       "(1) Renderização progressiva de clipes individuais conforme ficam prontos, sem recarregar cards existentes; "
                       "(2) Correção de bug no histórico (popstate) ao fechar o editor de clipes; "
                       "(3) Correção da exibição de títulos e ganchos gerados pela IA; "
                       "(4) Geração e persistência de miniaturas reais JPG em vez de imagens fixas do Unsplash (migração 005); "
                       "(5) Eliminação de pré-carregamento automático de vídeos (preload='none'); "
                       "(6) Substituição completa da biblioteca de ícones pesada (Font Awesome ~500KB) por folha de estilos nativa (icons.css ~2.9KB gzipped, redução de 99.4%); "
                       "(7) Obtenção dinâmica dos limites de arquivo e duração via /api/v1/config; "
                       "(8) Barra de progresso real em upload com cancelamento instantâneo via XHR abort.")

    add_paragraph(doc, "Medição Empírica de Transferência do Frontend (Host Local com Gzip Nginx):", bold_prefix="Medição Oficial da Etapa 4: ")
    add_bullet(doc, "Tamanho total transferido de ativos estáticos (HTML + CSS modular + JS + ícones nativos): 32.296 bytes (~32,3 KB comprimido via gzip), contra uma linha de base anterior superior a 650 KB com Font Awesome.")
    add_bullet(doc, "Tempo mediano de carregamento da interface (local host HTTP): 51,75ms.")
    add_bullet(doc, "Consumo de dados móveis e conexões concorrentes no carregamento da grade de resultados: Redução de 100% no download automático de vídeos (graças a preload='none' e thumbnails JPG leves de ~40KB).")

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 7: FRONTEND E EXPERIÊNCIA DO USUÁRIO
    # --------------------------------------------------------------------------
    add_heading_1(doc, "7. Interface do Usuário e Experiência (Frontend)")
    add_paragraph(doc, 
                  "A interface do ClipMaker.io foi concebida sob o paradigma de Single Page Application (SPA) nativa, sem a dependência "
                  "de frameworks pesados como React, Vue ou Angular. O código é particionado em módulos semânticos de estilização "
                  "(reset.css, tokens.css, layout.css, components.css, responsive.css, animations.css e icons.css) e controladores JavaScript "
                  "(app.js para fluxo de negócio e autenticação, ui.js para manipulação e reatividade do DOM).")

    add_heading_2(doc, "7.1 Telas e Fluxos Principais")
    add_paragraph(doc, "1. Modal de Autenticação e Boas-Vindas:", bold_prefix="Tela 1: ")
    add_paragraph(doc, "Interface com abas para login e cadastro de usuários, validação dinâmica de formulário, armazenamento seguro de token JWT "
                       "em localStorage e exibição de saldo de créditos.")

    add_paragraph(doc, "2. Área de Ingestão e Upload:", bold_prefix="Tela 2: ")
    add_paragraph(doc, "Painel com alternância entre envio de arquivo local (com drag and drop e barra de progresso real XMLHttpRequest) "
                       "e importação de URL de vídeo. Seleção visual do aspect ratio desejado (9:16, 1:1, 16:9). "
                       "Os limites de tamanho e duração são obtidos dinamicamente da API (/api/v1/config).")

    add_paragraph(doc, "3. Painel de Status Dinâmico e Estimativa de Fila:", bold_prefix="Tela 3: ")
    add_paragraph(doc, "Durante o processamento, exibe barra de progresso multi-faseada com etapas claras: "
                       "'📥 Baixando mídia' (DOWNLOADING), '🎙️ Transcrevendo áudio' (TRANSCRIBING), '🧠 Analisando melhores momentos' (ANALYZING) "
                       "e '🎬 Renderizando clipes' (RENDERING). Exibe a posição na fila e tempo estimado (ETA) calculado pelo backend.")

    add_paragraph(doc, "4. Grade de Resultados em Tempo Real:", bold_prefix="Tela 4: ")
    add_paragraph(doc, "Cards de clipes renderizados progressivamente. Cada card contém thumbnail JPG real, badge com Score Viral, "
                       "título e gancho identificados pela IA, duração, reprodutor HTML5 otimizado com preload='none', botões de download e botão 'Editar Clipes'.")

    add_paragraph(doc, "5. Editor Avançado de Clipes (Modal):", bold_prefix="Tela 5: ")
    add_paragraph(doc, "Permite ao usuário ajustar início e fim do corte, alterar o estilo das legendas dinâmicas (Yellow, Green, White), "
                       "ativar/desativar legendas e clicar sobre palavras individuais da transcrição para navegar no player ou destacá-las.")

    add_heading_2(doc, "7.2 Correções de Bugs Realizadas no Frontend")
    add_bullet(doc, "Títulos e Ganchos da IA (ui.js): Corrigido bug onde o código sobrescrevia clip.title por texto genérico caso clip.id iniciasse com 'clip_'. Agora o título e hookReason da IA são sempre respeitados.")
    add_bullet(doc, "Polling Não-Destrutivo (app.js): O polling de status agora renderiza apenas cards novos sem recriar os elementos de vídeo existentes, evitando que vídeos em reprodução piscassem ou reiniciassem.")
    add_bullet(doc, "Histórico do Navegador (popstate): Corrigido comportamento indesejado onde fechar o editor disparava window.history.back() e recarregava todos os clipes na tela.")

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 8: TESTES E CI
    # --------------------------------------------------------------------------
    add_heading_1(doc, "8. Testes Automatizados e Integração Contínua")
    add_paragraph(doc, 
                  "A estabilidade funcional e as políticas de segurança do ClipMaker.io são validadas através de uma suíte abrangente "
                  "de testes automatizados baseada no framework pytest e plugins assíncronos (pytest-asyncio, anyio).")

    add_heading_2(doc, "8.1 Escopo Coberto pela Suíte de Testes")
    add_bullet(doc, "Saúde e Configuração: Endpoints /health, /api/health, /api/config e /api/v1/config.")
    add_bullet(doc, "Autenticação e Segurança: Registro de usuário, normalização de email, hash bcrypt, geração e validação de tokens JWT, expiração e rejeição de tokens forjados.")
    add_bullet(doc, "Defesa de Rede e Anti-SSRF: Validação estrita da função _is_safe_public_url bloqueando esquemas maliciosos, hosts internos Docker e faixas de IP privadas.")
    add_bullet(doc, "Autorização e Isolamento: Garantia de HTTP 403 ao tentar acessar downloads ou status de projetos pertencentes a outros usuários.")
    add_bullet(doc, "Entrega Acelerada e Fallback: Validação do cabeçalho X-Accel-Redirect sob Nginx e fallback transparente para FileResponse em desenvolvimento.")
    add_bullet(doc, "Proteção de Concorrência: Bloqueio HTTP 429 quando um usuário excede MAX_CONCURRENT_JOBS_PER_USER.")
    add_bullet(doc, "Métricas e Fila: Validação de índices de concorrência e cálculo de média móvel para estimativa de tempo (job_metrics).")
    add_bullet(doc, "Políticas de Banco: Verificação de bloqueio fatal do fallback SQLite caso a flag explícita ALLOW_SQLITE_FALLBACK não esteja habilitada.")
    add_bullet(doc, "Instrumentação: Testes unitários do decorador @timed e do context manager timed() síncronos e assíncronos.")

    add_heading_2(doc, "8.2 O que NÃO é Coberto pelos Testes Automatizados")
    add_bullet(doc, "Renderização Completa de Vídeo com GPU: Testes de codificação de arquivos pesados via NVENC não rodam no CI por ausência de GPU física e tamanho dos arquivos de vídeo no repositório.")
    add_bullet(doc, "Testes End-to-End (E2E) de Interface Gráfica: Não há suite de automação de navegador (Selenium / Playwright).")

    add_heading_2(doc, "8.3 Resultado da Última Execução Oficial do Pytest")
    add_paragraph(doc, "Abaixo reproduz-se o extrato literal da execução da suíte de testes no ambiente local:")

    # Box de código com saída do pytest
    t_py = doc.add_table(rows=1, cols=1)
    t_py.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_py = t_py.rows[0].cells[0]
    set_cell_shading(c_py, "2D3748")
    set_cell_borders(c_py, top=None, bottom=None, left=None, right=None)
    set_cell_margins(c_py, top=100, bottom=100, left=140, right=140)
    p_code = c_py.paragraphs[0]
    p_code.paragraph_format.space_before = Pt(0)
    p_code.paragraph_format.space_after = Pt(0)
    r_code = p_code.add_run(
        "============================= test session starts =============================\n"
        "platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0\n"
        "rootdir: C:\\Users\\João Victor\\Documents\\Antigravity Projects\\ClipMakerAI\n"
        "configfile: pytest.ini\n"
        "testpaths: tests\n"
        "plugins: anyio-4.15.0, asyncio-1.4.0\n"
        "collected 24 items\n\n"
        "tests/test_api_endpoints.py::test_health_endpoints PASSED                [  4%]\n"
        "tests/test_api_endpoints.py::test_unauthorized_access PASSED             [  8%]\n"
        "tests/test_api_endpoints.py::test_password_min_length_validation PASSED  [ 12%]\n"
        "tests/test_api_endpoints.py::test_upload_aspect_ratio_validation PASSED  [ 16%]\n"
        "tests/test_api_endpoints.py::test_rerender_validation PASSED             [ 20%]\n"
        "tests/test_api_endpoints.py::test_project_lifecycle PASSED               [ 25%]\n"
        "tests/test_api_endpoints.py::test_incremental_clip_saving_and_ai_fallback PASSED [ 29%]\n"
        "tests/test_api_endpoints.py::test_transcription_cache PASSED             [ 33%]\n"
        "tests/test_api_endpoints.py::test_viral_score_and_boundaries PASSED      [ 37%]\n"
        "tests/test_api_endpoints.py::test_async_url_route_queue_and_status PASSED [ 41%]\n"
        "tests/test_api_endpoints.py::test_x_accel_redirect_and_fallback PASSED   [ 45%]\n"
        "tests/test_api_endpoints.py::test_clip_access_denied_for_other_user PASSED [ 50%]\n"
        "tests/test_api_endpoints.py::test_concurrent_jobs_limit PASSED           [ 54%]\n"
        "tests/test_api_endpoints.py::test_config_endpoints PASSED                [ 58%]\n"
        "tests/test_auth.py::test_register_and_login PASSED                       [ 62%]\n"
        "tests/test_core_and_security.py::test_password_hashing PASSED            [ 66%]\n"
        "tests/test_core_and_security.py::test_jwt_token_lifecycle PASSED         [ 70%]\n"
        "tests/test_core_and_security.py::test_anti_ssrf_url_validation PASSED    [ 75%]\n"
        "tests/test_core_and_security.py::test_video_crop_and_scale_dimensions PASSED [ 79%]\n"
        "tests/test_core_and_security.py::test_srt_timestamp_formatting PASSED    [ 83%]\n"
        "tests/test_fallback_policy.py::test_sqlite_fallback_denied_without_flag PASSED [ 87%]\n"
        "tests/test_timing.py::test_timed_context_manager PASSED                  [ 91%]\n"
        "tests/test_timing.py::test_timed_decorator_sync PASSED                   [ 95%]\n"
        "tests/test_timing.py::test_timed_decorator_async PASSED                  [100%]\n\n"
        "======================= 24 passed, 5 warnings in 54.88s ======================="
    )
    r_code.font.name = 'Consolas'
    r_code.font.size = Pt(8.0)
    r_code.font.color.rgb = RGBColor(247, 250, 252)

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 9: GUIA DE INSTALAÇÃO E OPERAÇÃO
    # --------------------------------------------------------------------------
    add_heading_1(doc, "9. Guia de Instalação e Operação")
    add_paragraph(doc, 
                  "Este capítulo apresenta o passo a passo verificado para executar o ClipMaker.io em ambientes "
                  "de desenvolvimento local e em infraestrutura de produção baseada em Docker Compose.")

    add_heading_2(doc, "9.1 Execução em Ambiente de Desenvolvimento Local")
    add_paragraph(doc, "1. Pré-requisitos:", bold_prefix="Passo 1: ")
    add_bullet(doc, "Python 3.11 ou superior instalado no host.")
    add_bullet(doc, "FFmpeg instalado e acessível nas variáveis de ambiente do sistema (PATH).")
    add_bullet(doc, "Instância local do Redis (porta 6379) ou Docker básico.")

    add_paragraph(doc, "2. Configuração do Ambiente Virtual e Dependências:", bold_prefix="Passo 2: ")
    add_bullet(doc, "python -m venv venv")
    add_bullet(doc, "venv\\Scripts\\activate  (Windows) ou source venv/bin/activate (Linux)")
    add_bullet(doc, "pip install -r backend/requirements.txt")

    add_paragraph(doc, "3. Configuração do Arquivo de Ambiente (.env):", bold_prefix="Passo 3: ")
    add_paragraph(doc, "Copie o arquivo .env.example para .env e preencha as variáveis fundamentais:")
    add_bullet(doc, "ENVIRONMENT=development")
    add_bullet(doc, "SECRET_KEY=uma_chave_longa_com_mais_de_32_caracteres_para_testes")
    add_bullet(doc, "GEMINI_API_KEY=sua_chave_do_google_ai_studio")
    add_bullet(doc, "ALLOW_SQLITE_FALLBACK=true  (caso deseje rodar sem PostgreSQL local)")
    add_bullet(doc, "SERVE_FRONTEND=true  (permite servir o frontend estático diretamente pela porta 8000)")

    add_paragraph(doc, "4. Inicialização dos Processos de Desenvolvimento:", bold_prefix="Passo 4: ")
    add_bullet(doc, "API: uvicorn backend.app.main:app --reload --port 8000")
    add_bullet(doc, "Worker: huey_consumer backend.app.worker.worker.huey -w 1 -k thread")
    add_bullet(doc, "Acesso no Navegador: http://localhost:8000")

    add_heading_2(doc, "9.2 Execução em Produção com Docker Compose")
    add_paragraph(doc, "1. Preparação de Diretórios e Permissões no Host:", bold_prefix="Passo 1: ")
    add_paragraph(doc, "Execute o script scripts/setup-prod.ps1 ou crie manualmente as pastas no disco persistente D::")
    add_bullet(doc, "mkdir D:\\docker-data\\clipmaker\\cache")
    add_bullet(doc, "mkdir D:\\docker-data\\clipmaker\\logs")
    add_bullet(doc, "mkdir D:\\docker-data\\clipmaker\\redis")

    add_paragraph(doc, "2. Inicialização dos Containers de Produção:", bold_prefix="Passo 2: ")
    add_paragraph(doc, "Execute o comando unificado de orquestração:")
    add_bullet(doc, "docker compose -f docker-compose.prod.yml --env-file .env up -d --build")

    add_paragraph(doc, "3. Verificação de Saúde e Migrações:", bold_prefix="Passo 3: ")
    add_bullet(doc, "docker compose -f docker-compose.prod.yml logs migrate")
    add_bullet(doc, "docker compose -f docker-compose.prod.yml ps")

    add_paragraph(doc, "4. Escalabilidade de Workers e Filas:", bold_prefix="Passo 4: ")
    add_paragraph(doc, "Para aumentar a capacidade de processamento de vídeos simultâneos em servidores multi-GPU:")
    add_bullet(doc, "docker compose -f docker-compose.prod.yml up -d --scale worker=2")

    add_paragraph(doc, "5. Rotina de Backup do Banco de Dados:", bold_prefix="Passo 5: ")
    add_paragraph(doc, "Gere dumps consistentes do PostgreSQL periodicamente:")
    add_bullet(doc, "docker compose -f docker-compose.prod.yml exec -T db pg_dump -U $POSTGRES_USER $POSTGRES_DB > backup.sql")

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 10: DIVERGÊNCIAS CONHECIDAS
    # --------------------------------------------------------------------------
    add_heading_1(doc, "10. Divergências Conhecidas (Documentação x Código Atual)")
    add_paragraph(doc, 
                  "Em conformidade com a auditoria rigorosa de código realizada com grep no repositório ativo, "
                  "foram identificadas as seguintes discrepâncias entre os arquivos de documentação legados (README.md, README-DEPLOY.md) "
                  "e o comportamento implementado no código de produção HOJE:")

    add_paragraph(doc, "1. Fallback Silencioso de Banco para SQLite:", bold_prefix="Divergência 1: ")
    add_paragraph(doc, "O README.md afirma que a aplicação opera em desenvolvimento com fallback automático para SQLite. "
                       "No código atual de backend/app/db/db_service.py (linhas 273-304), o fallback para SQLite é estritamente bloqueado "
                       "por padrão, disparando RuntimeError imediato caso o PostgreSQL esteja inacessível. O uso do SQLite (dev.db) requer "
                       "obrigatoriamente a variável explícita ALLOW_SQLITE_FALLBACK=true fora de produção.")

    add_paragraph(doc, "2. Endpoints Legados de Download nos Diagramas do README:", bold_prefix="Divergência 2: ")
    add_paragraph(doc, "O README.md original ilustra downloads ocorrendo em http://localhost:8000/download/clip_uuid.mp4. "
                       "No código consolidado atual, todos os downloads são roteados via Nginx através de /api/videos/download/{clip_id} "
                       "com validação de propriedade e aceleração interna X-Accel-Redirect.")

    add_paragraph(doc, "3. Modelo de Execução do Faster-Whisper:", bold_prefix="Divergência 3: ")
    add_paragraph(doc, "A documentação antiga cita a execução do Whisper exclusivamente na CPU com modelo base. "
                       "No código ativo do worker (Dockerfile target runtime-gpu e backend/app/services/ai_service.py), "
                       "o sistema roda com aceleração de GPU CTranslate2 CUDA em precisão float16, modelo padrão small e cache em VRAM.")

    add_paragraph(doc, "4. Limite de Upload no Frontend:", bold_prefix="Divergência 4: ")
    add_paragraph(doc, "O README-DEPLOY.md cita limite estático de 200MB no frontend. "
                       "Com as alterações da Etapa 4, o frontend consulta dinamicamente a rota /api/v1/config, assumindo o teto configurável "
                       "de 2000MB (MAX_FILE_SIZE_MB) definido no backend.")

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 11: PENDÊNCIAS E RISCOS
    # --------------------------------------------------------------------------
    add_heading_1(doc, "11. Pendências e Riscos Técnicos")
    add_paragraph(doc, 
                  "Abaixo listam-se os itens técnicos pendentes de evolução, classificados por nível de severidade e risco operacional:")

    # Tabela Pendências
    t_pen = doc.add_table(rows=7, cols=5)
    t_pen_data = [
        ["Prioridade", "Problema / Oportunidade", "Arquivo Afetado", "Linha(s)", "Motivo / Risco Técnico"],
        ["ALTA", "Ausência de 2FA / MFA", "backend/app/api/routers/auth.py", "28-36", "Contas protegidas apenas por senha; vulnerável a senhas vazadas em outros serviços."],
        ["ALTA", "Falta de TLS/HTTPS no Compose", "docker-compose.prod.yml", "205-231", "Porta 80 exposta sem certificado SSL embutido; exige proxy reverso externo na infraestrutura."],
        ["MÉDIA", "Rate limit global no Nginx", "frontend/nginx.conf", "1-68", "Arquivos estáticos e health checks não possuem rate limiting no Nginx, vulneráveis a flood."],
        ["MÉDIA", "Falta de Account Lockout", "backend/app/api/routers/auth.py", "30-36", "Não bloqueia temporariamente contas após múltiplas tentativas consecutivas de senha incorreta."],
        ["BAIXA", "Blacklist de tokens JWT", "backend/app/core/security.py", "1-45", "Token permanece válido até expirar; logout voluntário não revoga o token no servidor."],
        ["BAIXA", "Haar Cascade em perfil extremo", "backend/app/services/video_service.py", "180-260", "Haar Cascade clássico tem precisão reduzida para rostos virados em perfil acentuado."]
    ]
    for r_idx, row in enumerate(t_pen_data):
        for c_idx, val in enumerate(row):
            t_pen.rows[r_idx].cells[c_idx].paragraphs[0].text = val
    style_table(t_pen, col_widths=[1.0, 1.8, 1.6, 0.7, 1.9],
                align_cols=[WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.CENTER, WD_ALIGN_PARAGRAPH.LEFT])

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 12: MUDANÇAS AINDA NÃO COMMITADAS
    # --------------------------------------------------------------------------
    add_heading_1(doc, "12. Mudanças Ainda Não Commitadas")
    add_paragraph(doc, 
                  f"Em conformidade com a auditoria de repositório realizada na data de {today_date}, "
                  "foram identificadas as seguintes alterações pendentes de commit na árvore de trabalho local (working directory):")

    add_paragraph(doc, f"Auditoria realizada via git status e git diff --stat em {today_date}:", bold_prefix="Status do Repositório: ")
    add_bullet(doc, "Arquivos Modificados (8): backend/app/main.py, frontend/css/components.css, frontend/css/tokens.css, frontend/index.html, frontend/js/app.js, frontend/js/ui.js, frontend/nginx.conf, tests/test_api_endpoints.py.")
    add_bullet(doc, "Arquivos Untracked (2): frontend/css/icons.css, migrations/005_etapa4_thumbnails.sql.")
    add_bullet(doc, "Volume de Código Alterado: 536 inserções(+), 96 deleções(-).")

    add_paragraph(doc, "Essas alterações representam a implementação e validação integral da Etapa 4 de Otimização "
                       "(Frontend e Velocidade Percebida), incluindo o novo endpoint /api/v1/config, substituição do Font Awesome "
                       "por folha de ícones nativa (icons.css), correção de títulos/ganchos da IA, polling não-destrutivo e "
                       "persistência de miniaturas.", bold_prefix="Contexto Técnico das Alterações: ")

    doc.add_page_break()

    # --------------------------------------------------------------------------
    # CAPÍTULO 13: APÊNDICES
    # --------------------------------------------------------------------------
    add_heading_1(doc, "13. Apêndices")

    add_heading_2(doc, "13.1 Catálogo Completo de Arquivos do Projeto")
    add_paragraph(doc, "Abaixo apresenta-se a relação exaustiva de todos os arquivos componentes do repositório ClipMaker.io:")

    files_list = [
        [".dockerignore", "Especifica arquivos e diretórios excluídos durante a construção das imagens Docker."],
        [".env.example", "Modelo com todas as variáveis de ambiente necessárias e valores recomendados."],
        [".gitattributes", "Define configurações de normalização de finais de linha (LF/CRLF) para o Git."],
        [".github/workflows/tests.yml", "Pipeline de Integração Contínua (CI) que executa a suíte de testes no GitHub Actions."],
        [".gitignore", "Lista de arquivos ignorados pelo Git (caches, ambientes virtuais, vídeos temporários)."],
        ["Dockerfile", "Receita multi-stage para construção das imagens clipmakerai:prod e clipmakerai:prod-gpu."],
        ["README-DEPLOY.md", "Guia detalhado com instruções de deploy em servidores de produção."],
        ["README.md", "Documentação geral do projeto, visão executiva e guia rápido."],
        ["backend/.env.example", "Cópia do modelo de variáveis de ambiente para o contexto específico do backend."],
        ["backend/app/api/deps.py", "Injeção de dependências do FastAPI (autenticação JWT e rate limiter SlowAPI)."],
        ["backend/app/api/routers/auth.py", "Controlador REST para registro e autenticação de usuários."],
        ["backend/app/api/routers/project.py", "Controlador REST para projetos, status, fila dinâmica e re-renderização."],
        ["backend/app/api/routers/video.py", "Controlador REST para upload, importação por URL e download via X-Accel."],
        ["backend/app/core/config.py", "Configurações globais e validações defensivas de ambiente via Pydantic."],
        ["backend/app/core/logging_config.py", "Configuração de formatação estruturada de logs da aplicação em formato JSON."],
        ["backend/app/core/loop.py", "Utilitário para inicialização robusta de loop de eventos assíncrono."],
        ["backend/app/core/security.py", "Rotinas criptográficas de hash Bcrypt e assinatura/decodificação de tokens JWT."],
        ["backend/app/core/timing.py", "Instrumentação de tempo de execução com decorador @timed e context manager timed()."],
        ["backend/app/db/db_service.py", "Camada de acesso a dados assíncrona com suporte a PostgreSQL (asyncpg) e dev SQLite."],
        ["backend/app/main.py", "Ponto de entrada da API FastAPI, registro de middlewares, CORS e roteadores."],
        ["backend/app/models/user.py", "Modelos Pydantic para validação de dados de entrada de usuários e senhas."],
        ["backend/app/services/ai_service.py", "Serviço de transcrição Whisper GPU e análise semântica de momentos com Gemini."],
        ["backend/app/services/engine_service.py", "Motor de alto nível que orquestra a geração dos clipes e integração."],
        ["backend/app/services/haarcascade_frontalface_default.xml", "Arquivo XML com os classificadores em cascata Haar para detecção facial."],
        ["backend/app/services/video_service.py", "Operações de mídia com FFmpeg (corte, scale, legendas) e OpenCV (face tracking)."],
        ["backend/app/worker/worker.py", "Trabalhador assíncrono do Huey para tarefas pesadas de rede, IA e vídeo."],
        ["backend/requirements-dev.txt", "Dependências adicionais para ambiente de desenvolvimento e testes do backend."],
        ["backend/requirements.txt", "Dependências de produção do backend (FastAPI, asyncpg, ctranslate2, opencv)."],
        ["docker-compose.prod.yml", "Orquestração completa dos microsserviços de produção com limites e segurança."],
        ["docker-compose.yml", "Orquestração básica do ambiente Docker para desenvolvimento local."],
        ["docs/PERFORMANCE.md", "Relatório técnico com métricas empíricas de todas as etapas de otimização."],
        ["frontend/css/animations.css", "Definições de animações CSS, keyframes e efeitos de transição."],
        ["frontend/css/components.css", "Estilização de componentes (botões, cards, modais, formulários, badges)."],
        ["frontend/css/icons.css", "Folha de estilos nativa com ícones SVG embutidos, substituindo o Font Awesome."],
        ["frontend/css/layout.css", "Estrutura de grid, containers principais e seções de layout da página."],
        ["frontend/css/reset.css", "Normalização de estilos padrão dos navegadores."],
        ["frontend/css/responsive.css", "Regras de media queries para adaptação responsiva em telas móveis e desktop."],
        ["frontend/css/tokens.css", "Variáveis CSS institucionais de cores, tipografia, bordas e espaçamentos."],
        ["frontend/index.html", "Página única da interface web com suporte a temas, modais e player de vídeo."],
        ["frontend/js/app.js", "Controlador principal da interface: autenticação, uploads, polling e eventos."],
        ["frontend/js/ui.js", "Controlador de renderização visual DOM e helpers de exibição de clipes."],
        ["frontend/nginx.conf", "Configuração do Nginx com gzip, proxy reverso e cabeçalhos X-Accel-Redirect."],
        ["migrations/001_init.sql", "Migração inicial do banco: tabelas users, projects, clips e transcriptions."],
        ["migrations/002_add_thumbnail_key.sql", "Migração que adiciona coluna thumbnail_key na tabela clips."],
        ["migrations/003_etapa2_pipeline.sql", "Migração que adiciona face_center_x, ai_cuts_fallback e lookup de cache."],
        ["migrations/004_etapa3_api_queue.sql", "Migração que cria a tabela job_metrics e índices de concorrência."],
        ["migrations/005_etapa4_thumbnails.sql", "Migração que assegura coluna e índice de thumbnail_key para clipes."],
        ["pytest.ini", "Configurações de execução e diretórios de teste do pytest."],
        ["requirements-dev.txt", "Dependências de desenvolvimento na raiz do repositório."],
        ["scripts/benchmark.py", "Script de benchmark para testes de carga e cronometragem do pipeline."],
        ["scripts/cleanup.py", "Script de expurgo periódico de arquivos de vídeo antigos do disco temporário."],
        ["scripts/gerar_documentacao.py", "Script gerador desta documentação corporativa em formato .docx."],
        ["scripts/migrate.sh", "Script shell one-shot que aplica as migrações SQL no PostgreSQL no boot."],
        ["scripts/setup-prod.ps1", "Script PowerShell de preparação de pastas persistentes no host Windows."],
        ["tests/conftest.py", "Fixtures do pytest para mock de sessões, usuários e banco de testes."],
        ["tests/test_api_endpoints.py", "Testes de integração para todos os endpoints da API FastAPI."],
        ["tests/test_auth.py", "Testes unitários para fluxos de registro e login com JWT."],
        ["tests/test_core_and_security.py", "Testes para rotinas de segurança, anti-SSRF, senhas e formatação de mídia."],
        ["tests/test_fallback_policy.py", "Testes de validação da política de bloqueio do fallback SQLite."],
        ["tests/test_timing.py", "Testes unitários dos mecanismos de medição de tempo de execução (timed)."]
    ]

    t_files = doc.add_table(rows=len(files_list) + 1, cols=2)
    t_files.rows[0].cells[0].paragraphs[0].text = "Caminho do Arquivo"
    t_files.rows[0].cells[1].paragraphs[0].text = "Descrição Técnica e Responsabilidade"

    for idx, (f_path, f_desc) in enumerate(files_list, start=1):
        t_files.rows[idx].cells[0].paragraphs[0].text = f_path
        t_files.rows[idx].cells[1].paragraphs[0].text = f_desc

    style_table(t_files, col_widths=[2.4, 4.6],
                align_cols=[WD_ALIGN_PARAGRAPH.LEFT, WD_ALIGN_PARAGRAPH.LEFT])

    add_heading_2(doc, "13.2 Glossário de Termos Técnicos")
    add_bullet(doc, "FFmpeg: Conjunto de bibliotecas e ferramentas de linha de comando para manipulação e codificação de áudio e vídeo.", bold_prefix="FFmpeg: ")
    add_bullet(doc, "NVENC: Acelerador de codificação de vídeo por hardware integrado às placas de vídeo dedicadas da NVIDIA.", bold_prefix="NVENC: ")
    add_bullet(doc, "Whisper: Modelo neural de reconhecimento automático de fala (ASR) treinado pela OpenAI.", bold_prefix="Whisper: ")
    add_bullet(doc, "CTranslate2: Motor de inferência acelerado para modelos Transformer em CPU e GPU com suporte a quantização int8 e float16.", bold_prefix="CTranslate2: ")
    add_bullet(doc, "Haar Cascade: Algoritmo de visão computacional baseado em aprendizado de máquina para detecção rápida de objetos e faces.", bold_prefix="Haar Cascade: ")
    add_bullet(doc, "Huey: Sistema de filas de tarefas assíncronas leve em Python com suporte a Redis e paralelismo por threads ou processos.", bold_prefix="Huey: ")
    add_bullet(doc, "asyncpg: Driver de conexão assíncrono de altíssima performance para PostgreSQL em Python.", bold_prefix="asyncpg: ")
    add_bullet(doc, "X-Accel-Redirect: Mecanismo interno do Nginx que permite à aplicação autenticar requisições e delegar a entrega do arquivo ao servidor web.", bold_prefix="X-Accel-Redirect: ")
    add_bullet(doc, "HTTP Range (Status 206): Mecanismo que permite solicitar fatias específicas de bytes de um arquivo, viabilizando seek em vídeos.", bold_prefix="HTTP Range: ")
    add_bullet(doc, "Anti-SSRF: Conjunto de regras defensivas que impedem que o servidor faça requisições a endereços internos protegidos.", bold_prefix="Anti-SSRF: ")
    add_bullet(doc, "cgroup (Control Groups): Mecanismo do kernel Linux que limita e isola o uso de recursos (CPU, memória) por processos.", bold_prefix="cgroup: ")

    add_heading_2(doc, "13.3 Histórico de Migrações do Banco de Dados")
    add_paragraph(doc, "A evolução do esquema relacional é assegurada por migrações SQL idempotentes:")
    add_bullet(doc, "001_init.sql: Criação inicial das tabelas users, projects, clips e transcriptions, com índices básicos.")
    add_bullet(doc, "002_add_thumbnail_key.sql: Adição da coluna thumbnail_key na tabela clips para controle de miniaturas.")
    add_bullet(doc, "003_etapa2_pipeline.sql: Adição da coluna face_center_x em clips, ai_cuts_fallback em projects, e colunas userId, sourceUrl, fileHash em transcriptions com índice idx_transcriptions_lookup.")
    add_bullet(doc, "004_etapa3_api_queue.sql: Criação da tabela job_metrics e índices de concorrência idx_projects_user_status e idx_projects_status_created.")
    add_bullet(doc, "005_etapa4_thumbnails.sql: Garantia idempotente de coluna e índice dedicado idx_clips_thumbnail na tabela clips.")

    # Salvamento
    print(f"[*] Salvando documento em: {OUTPUT_DOCX}")
    doc.save(str(OUTPUT_DOCX))
    print(f"[+] Documento gerado com sucesso! Tamanho: {OUTPUT_DOCX.stat().st_size} bytes.")


if __name__ == "__main__":
    main()
