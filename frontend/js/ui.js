// UI Controller and rendering helpers
window.API_BASE_URL = window.API_BASE_URL || (window.location.protocol === 'file:' ? 'http://localhost' : '');
var API_BASE_URL = window.API_BASE_URL;
var API_BASE = `${window.API_BASE_URL}/api`;

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function showToast(message, type = 'info', duration = 4500) {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    const isError = type === 'error';
    const roleAttr = isError ? 'alert' : 'status';
    const ariaLive = isError ? 'assertive' : 'polite';
    
    toast.className = `toast toast-${type}`;
    toast.setAttribute('role', roleAttr);
    toast.setAttribute('aria-live', ariaLive);

    let iconHtml = '<i class="fa-solid fa-circle-info"></i>';
    if (type === 'success') {
        iconHtml = '<i class="fa-solid fa-circle-check"></i>';
    } else if (type === 'error') {
        iconHtml = '<i class="fa-solid fa-circle-exclamation"></i>';
    }

    toast.innerHTML = `
        <span class="toast-icon">${iconHtml}</span>
        <div class="toast-message">${escapeHtml(message)}</div>
        <button type="button" class="toast-close-btn" aria-label="Fechar notificação">&times;</button>
    `;

    let closed = false;
    let timer = null;

    const removeToast = () => {
        if (closed) return;
        closed = true;
        if (timer) clearTimeout(timer);
        toast.classList.add('toast-hiding');
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 220);
    };

    const closeBtn = toast.querySelector('.toast-close-btn');
    if (closeBtn) {
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            removeToast();
        });
    }

    if (duration > 0) {
        timer = setTimeout(removeToast, duration);
    }

    container.appendChild(toast);
    return toast;
}

window.showToast = showToast;

async function fetchSignedUrl(clipId) {
    const token = localStorage.getItem('clipmaker_token') || '';
    const res = await fetch(`${API_BASE}/videos/${encodeURIComponent(clipId)}/signed-url`, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    if (!res.ok) throw new Error('Falha ao obter URL assinada.');
    return await res.json();
}

function resolveMediaUrl(url) {
    if (!url) return '';
    if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('blob:') || url.startsWith('data:')) {
        return url;
    }
    const base = window.API_BASE_URL || '';
    if (url.startsWith('/')) {
        return `${base}${url}`;
    }
    return `${base}/${url}`;
}

function getClipVideoUrl(clipId, extraParam = '') {
    const parts = [];
    if (extraParam) parts.push(extraParam);
    const qs = parts.length ? `?${parts.join('&')}` : '';
    const base = window.API_BASE_URL || '';
    return `${base}/api/videos/download/${encodeURIComponent(clipId)}${qs}`;
}

function getClipThumbnailUrl(clipId, extraParam = '') {
    const parts = [];
    if (extraParam) parts.push(extraParam);
    const qs = parts.length ? `?${parts.join('&')}` : '';
    const base = window.API_BASE_URL || '';
    return `${base}/api/videos/thumbnail/${encodeURIComponent(clipId)}${qs}`;
}

function triggerFileDownload(downloadUrl, filename = 'clip.mp4') {
    const separator = downloadUrl.includes('?') ? '&' : '?';
    const finalUrl = `${downloadUrl}${separator}download=1`;
    const link = document.createElement('a');
    link.href = finalUrl;
    link.setAttribute('download', filename);
    link.setAttribute('target', '_blank');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

const UI = {
    currentClip: null,
    playbackTimer: null,
    simulatedCurrentTime: 0,
    renderedProjectId: null,
    isClosingEditor: false,

    renderClips(clips, projectId = null) {
        const container = document.getElementById('clips-container');
        if (!container) return;

        // Se mudou de projeto, limpa os cards anteriores
        if (projectId && UI.renderedProjectId !== projectId) {
            container.innerHTML = '';
            UI.renderedProjectId = projectId;
        }

        if (!Array.isArray(clips) || clips.length === 0) return;

        clips.forEach((clip) => {
            const clipIdentifier = clip.clipId || clip.id;
            if (!clipIdentifier) return;

            // Se o card já está na tela, não recria nem recarrega o vídeo
            if (container.querySelector(`.clip-preview-container[data-id="${escapeHtml(clipIdentifier)}"]`)) {
                return;
            }

            const card = document.createElement('div');
            card.className = 'clip-card';
            
            const scoreClass = (clip.viralScore || 0) >= 90 ? 'viral-score-high' : 'viral-score-med';
            const cardRatio = clip.aspectRatio === '16:9' ? '16/9' : (clip.aspectRatio === '1:1' ? '1/1' : '9/16');
            
            // Item 3: Exibe sempre o título e o gancho reais da IA
            const titleSafe = escapeHtml(clip.title || 'Corte Viral (IA)');
            const hookSafe = escapeHtml(clip.hookReason || '');
            
            const videoUrl = resolveMediaUrl(clip.videoUrl || getClipVideoUrl(clipIdentifier));
            const thumbnailUrl = resolveMediaUrl(clip.thumbnailUrl || getClipThumbnailUrl(clipIdentifier));
            // Card com vídeo HTML5 e overlay de play
            const mediaContent = `
                <video src="${videoUrl}" poster="${thumbnailUrl}" preload="metadata" playsinline controls class="clip-card-video"></video>
                <div class="clip-overlay-play" title="Assistir e Editar Clipe">
                    <i class="fa-solid fa-play"></i>
                </div>
            `;

            card.innerHTML = `
                <div class="clip-preview-container" data-id="${escapeHtml(clipIdentifier)}" style="aspect-ratio: ${cardRatio};">
                    ${mediaContent}
                    <div class="clip-badges">
                        <div class="viral-badge ${scoreClass}">
                            <i class="fa-solid fa-fire"></i> ${Number(clip.viralScore || 0)}/100
                        </div>
                        <div class="clip-duration">${escapeHtml(clip.duration || '')}</div>
                    </div>
                </div>
                <div class="clip-details">
                    <div>
                        <h3 class="clip-card-title">${titleSafe}</h3>
                        <p class="clip-card-hook">${hookSafe}</p>
                    </div>
                    <div class="clip-card-actions">
                        <button class="btn-secondary btn-sm block btn-edit" data-id="${escapeHtml(clipIdentifier)}">
                            <i class="fa-solid fa-pen-to-square"></i> Editar Clipe
                        </button>
                        <button class="btn-primary btn-sm block btn-download" data-id="${escapeHtml(clipIdentifier)}">
                            <i class="fa-solid fa-download"></i> Baixar
                        </button>
                    </div>
                </div>
            `;

            container.appendChild(card);

            // Clique na miniatura abre o modal de edição e reprodução completa
            const previewContainer = card.querySelector('.clip-preview-container');
            if (previewContainer) {
                previewContainer.addEventListener('click', (e) => {
                    if (e.target.closest('button') || e.target.closest('.clip-card-actions')) {
                        return;
                    }
                    UI.openEditorModal(clip);
                });
            }

            // Tratamento de renovação automática se o vídeo der erro (ex: URL expirada)
            const cardVideo = card.querySelector('video');
            if (cardVideo) {
                cardVideo.addEventListener('error', async () => {
                    try {
                        const data = await fetchSignedUrl(clipIdentifier);
                        if (data && data.download_url) {
                            const freshUrl = resolveMediaUrl(data.download_url);
                            clip.videoUrl = freshUrl;
                            cardVideo.src = freshUrl;
                        }
                    } catch (e) {}
                });
            }

            // Vincula eventos especificamente para este novo card
            const editBtn = card.querySelector('.btn-edit');
            if (editBtn) {
                editBtn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    UI.openEditorModal(clip);
                });
            }

            const downloadBtn = card.querySelector('.btn-download');
            if (downloadBtn) {
                downloadBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    const origHtml = downloadBtn.innerHTML;
                    downloadBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Baixando...';
                    downloadBtn.disabled = true;

                    try {
                        let downloadUrl = '';
                        try {
                            const data = await fetchSignedUrl(clipIdentifier);
                            downloadUrl = resolveMediaUrl(data.download_url);
                        } catch (err) {
                            downloadUrl = resolveMediaUrl(clip.videoUrl || getClipVideoUrl(clipIdentifier));
                        }

                        const safeTitle = (clip.title || 'clipe')
                            .replace(/[\\/*?:"<>|]/g, '')
                            .trim()
                            .replace(/\s+/g, '_');
                        triggerFileDownload(downloadUrl, `${safeTitle}.mp4`);
                        showToast('Download do clipe iniciado!', 'success', 3500);
                    } catch (err) {
                        showToast('Falha ao baixar clipe: ' + err.message, 'error');
                    } finally {
                        downloadBtn.innerHTML = origHtml;
                        downloadBtn.disabled = false;
                    }
                });
            }
        });
    },

    openEditorModal(clip) {
        UI.currentClip = clip;
        const modal = document.getElementById('editor-modal');
        const transcriptContainer = document.getElementById('transcript-container');
        const videoContainer = document.querySelector('.video-preview-container');
        
        if (!modal || !transcriptContainer) return;

        const clipIdentifier = clip.clipId || clip.id;

        // Configuração de Aspect Ratio
        const aspectSelect = document.getElementById('aspect-ratio-select');
        const currentRatio = clip.aspectRatio || '9:16';
        if (aspectSelect) {
            aspectSelect.value = currentRatio;
        }

        const updatePlayerAspect = (ratio) => {
            const wrapper = document.getElementById('editor-video-wrapper');
            if (wrapper) {
                if (ratio === '16:9') {
                    wrapper.style.aspectRatio = '16/9';
                    wrapper.style.maxHeight = '320px';
                } else if (ratio === '1:1') {
                    wrapper.style.aspectRatio = '1/1';
                    wrapper.style.maxHeight = '360px';
                } else {
                    wrapper.style.aspectRatio = '9/16';
                    wrapper.style.maxHeight = '480px';
                }
            }
        };

        if (aspectSelect) {
            aspectSelect.onchange = () => {
                updatePlayerAspect(aspectSelect.value);
            };
        }

        // Reconstruir o video preview real com URL resolvida
        const videoUrl = resolveMediaUrl(clip.videoUrl || getClipVideoUrl(clipIdentifier));
        const thumbnailUrl = resolveMediaUrl(clip.thumbnailUrl || getClipThumbnailUrl(clipIdentifier));
        videoContainer.innerHTML = `
            <div id="editor-video-wrapper" style="width: 100%; border-radius: var(--radius-md); overflow: hidden; background: #000; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border-subtle); transition: aspect-ratio 0.3s ease;">
                <video id="editor-video-player" src="${videoUrl}" poster="${thumbnailUrl}" style="width: 100%; height: 100%; object-fit: contain;" autoplay playsinline controls loop></video>
            </div>
        `;
        updatePlayerAspect(currentRatio);

        // Sempre renova para URL assinada recente para garantir reprodução fluida no editor
        fetchSignedUrl(clipIdentifier).then(data => {
            const player = document.getElementById('editor-video-player');
            if (player && data && data.download_url) {
                const freshUrl = resolveMediaUrl(data.download_url);
                clip.videoUrl = freshUrl;
                player.src = freshUrl;
                player.play().catch(() => {});
            }
        }).catch(() => {});

        transcriptContainer.innerHTML = '';

        // Definir o select de estilo com base no atual
        const styleSelect = document.getElementById('caption-style-select');
        if (styleSelect && clip.captionConfig) {
            styleSelect.value = clip.captionConfig;
        }

        // Preencher inputs de trim
        const trimStartInput = document.getElementById('trim-start');
        const trimEndInput = document.getElementById('trim-end');
        if (trimStartInput && trimEndInput) {
            trimStartInput.value = clip.startTime || 0;
            const durationSec = clip.duration ? parseFloat(clip.duration.toString().replace('s', '')) : 0;
            trimEndInput.value = clip.endTime || durationSec;
        }

        const words = clip.words || [];
        words.forEach((w, idx) => {
            const wordEl = document.createElement('div');
            wordEl.className = `transcript-word ${w.highlighted ? 'highlighted' : ''}`;
            wordEl.setAttribute('data-index', idx);
            const safeText = escapeHtml(w.text);
            wordEl.innerHTML = `
                <span contenteditable="true" class="editable-word">${safeText}</span>
                <i class="fa-solid fa-star star-btn ${w.highlighted ? 'text-yellow' : ''}" title="Destacar palavra"></i>
            `;

            wordEl.addEventListener('click', (e) => {
                if (e.target.classList.contains('star-btn')) {
                    w.highlighted = !w.highlighted;
                    wordEl.classList.toggle('highlighted', w.highlighted);
                } else if (!e.target.classList.contains('editable-word')) {
                    const videoEl = document.getElementById('editor-video-player');
                    if (videoEl && w.start !== undefined) {
                        videoEl.currentTime = w.start;
                        videoEl.play();
                    }
                    UI.highlightActiveWord(idx);
                }
            });

            const spanEditable = wordEl.querySelector('.editable-word');
            spanEditable.addEventListener('blur', () => {
                w.text = spanEditable.innerText.trim();
            });

            transcriptContainer.appendChild(wordEl);
        });

        // Sync transcript with real video
        const videoEl = document.getElementById('editor-video-player');
        if (videoEl) {
            videoEl.addEventListener('timeupdate', () => {
                const ct = videoEl.currentTime;
                const activeIdx = words.findIndex(w => ct >= w.start && ct <= w.end);
                if (activeIdx !== -1) {
                    UI.highlightActiveWord(activeIdx);
                }
            });
        }

        // Export logic com polling de conclusão
        const btnExport = document.getElementById('btn-export-clip');
        if (btnExport) {
            const newBtn = btnExport.cloneNode(true);
            btnExport.parentNode.replaceChild(newBtn, btnExport);
            
            newBtn.addEventListener('click', async () => {
                const originalText = newBtn.innerHTML;
                newBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Solicitando re-render...';
                newBtn.disabled = true;
                
                const style = document.getElementById('caption-style-select').value || 'Yellow';
                const trimStart = parseFloat(document.getElementById('trim-start').value || 0);
                const trimEnd = parseFloat(document.getElementById('trim-end').value || 0);
                const aspectRatio = document.getElementById('aspect-ratio-select').value || '9:16';
                const addSubtitles = document.getElementById('toggle-subtitles').checked;
                const quality = document.getElementById('quality-select').value || '1080p';
                
                try {
                    const res = await fetch(`${API_BASE}/projects/clip/${clipIdentifier}/re-render`, {
                        method: 'POST',
                        headers: { 
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${localStorage.getItem('clipmaker_token')}`
                        },
                        body: JSON.stringify({
                            words: clip.words,
                            style: style,
                            start_time: trimStart,
                            end_time: trimEnd,
                            aspect_ratio: aspectRatio,
                            add_subtitles: addSubtitles,
                            quality: quality
                        })
                    });
                    
                    if (!res.ok) {
                        let errDetail = 'Erro na solicitação de renderização';
                        try {
                            const errData = await res.json();
                            if (errData.detail) errDetail = errData.detail;
                        } catch (e) {}
                        throw new Error(errDetail);
                    }
                    
                    newBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Renderizando vídeo...';

                    // Polling do status do clipe até COMPLETED
                    let pollSuccess = false;
                    for (let attempt = 0; attempt < 60; attempt++) {
                        await new Promise(resolve => setTimeout(resolve, 2000));
                        const statusRes = await fetch(`${API_BASE}/projects/clip/${clipIdentifier}/status`, {
                            headers: { 'Authorization': `Bearer ${localStorage.getItem('clipmaker_token')}` }
                        });
                        if (!statusRes.ok) continue;
                        const statusData = await statusRes.json();
                        if (statusData.status === 'COMPLETED') {
                            pollSuccess = true;
                            break;
                        }
                        if (statusData.status === 'FAILED') {
                            throw new Error(statusData.error || 'Falha durante o processamento do clipe.');
                        }
                    }

                    if (!pollSuccess) {
                        throw new Error('Tempo limite de renderização atingido. Tente novamente mais tarde.');
                    }
                    
                    let refreshedUrl = resolveMediaUrl(getClipVideoUrl(clipIdentifier, `t=${Date.now()}`));
                    try {
                        const signedData = await fetchSignedUrl(clipIdentifier);
                        refreshedUrl = resolveMediaUrl(signedData.download_url);
                    } catch (e) {}

                    // Baixar automaticamente apenas após conclusão confirmada sem navegar para fora da página
                    const safeExportTitle = (clip.title || 'clipe_exportado')
                        .replace(/[\\/*?:"<>|]/g, '')
                        .trim()
                        .replace(/\s+/g, '_');
                    triggerFileDownload(refreshedUrl, `${safeExportTitle}.mp4`);
                    showToast('Exportação concluída! Download iniciado.', 'success');
                    
                    // Recarregar preview
                    const currentVideoEl = document.getElementById('editor-video-player');
                    if (currentVideoEl) {
                        currentVideoEl.src = refreshedUrl;
                        currentVideoEl.play().catch(() => {});
                    }
                    
                    clip.captionConfig = style;
                    clip.aspectRatio = aspectRatio;
                    clip.startTime = trimStart;
                    clip.endTime = trimEnd;
                    updatePlayerAspect(aspectRatio);

                    // Atualiza o card de preview na listagem principal
                    const cardPreview = document.querySelector(`.clip-preview-container[data-id="${clipIdentifier}"]`);
                    if (cardPreview) {
                        const newCardRatio = aspectRatio === '16:9' ? '16/9' : (aspectRatio === '1:1' ? '1/1' : '9/16');
                        cardPreview.style.aspectRatio = newCardRatio;
                        const cardVideo = cardPreview.querySelector('video');
                        if (cardVideo) {
                            cardVideo.src = refreshedUrl;
                        }
                    }
                } catch (err) {
                    showToast('Falha ao renderizar clipe: ' + err.message, 'error');
                } finally {
                    newBtn.innerHTML = originalText;
                    newBtn.disabled = false;
                }
            });
        }

        modal.classList.remove('hidden');
        if (!history.state || history.state.page !== 'editor') {
            const currentUrl = new URL(window.location.href);
            history.pushState({ page: 'editor', clipId: clipIdentifier }, '', currentUrl.toString());
        }
    },

    closeEditorModal() {
        UI.isClosingEditor = true;
        const modal = document.getElementById('editor-modal');
        if (modal && !modal.classList.contains('hidden')) {
            modal.classList.add('hidden');
        }
        
        const videoEl = document.getElementById('editor-video-player');
        if (videoEl) videoEl.pause();

        if (history.state && history.state.page === 'editor') {
            history.back();
        }
        setTimeout(() => {
            UI.isClosingEditor = false;
        }, 300);
    },

    highlightActiveWord(index) {
        const words = document.querySelectorAll('.transcript-word');
        words.forEach((el, idx) => {
            if (idx === index) {
                el.classList.add('active');
                const rect = el.getBoundingClientRect();
                const container = el.parentElement.getBoundingClientRect();
                if (rect.top < container.top || rect.bottom > container.bottom) {
                    el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            } else {
                el.classList.remove('active');
            }
        });
    }
};
