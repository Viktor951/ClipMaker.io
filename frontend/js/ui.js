// UI Controller and rendering helpers
const API_BASE_URL = window.API_BASE_URL || (window.location.protocol === 'file:' ? 'http://localhost:8000' : '');
window.API_BASE_URL = API_BASE_URL;
const API_BASE = `${API_BASE_URL}/api`;

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

function getClipVideoUrl(clipId, extraParam = '') {
    const parts = [];
    if (extraParam) parts.push(extraParam);
    const qs = parts.length ? `?${parts.join('&')}` : '';
    return `/api/videos/download/${encodeURIComponent(clipId)}${qs}`;
}

function getClipThumbnailUrl(clipId) {
    return `/api/videos/thumbnail/${encodeURIComponent(clipId)}`;
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
            
            const videoUrl = clip.videoUrl || getClipVideoUrl(clipIdentifier);
            const thumbnailUrl = clip.thumbnailUrl || getClipThumbnailUrl(clipIdentifier);
            // Item 4: poster com miniatura real e preload="none"
            const mediaContent = `<video src="${videoUrl}" poster="${thumbnailUrl}" preload="none" controls class="clip-card-video"></video>`;

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

            // Vincula eventos especificamente para este novo card
            const editBtn = card.querySelector('.btn-edit');
            if (editBtn) {
                editBtn.addEventListener('click', () => {
                    UI.openEditorModal(clip);
                });
            }

            const downloadBtn = card.querySelector('.btn-download');
            if (downloadBtn) {
                downloadBtn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    try {
                        const data = await fetchSignedUrl(clipIdentifier);
                        window.location.href = data.download_url;
                    } catch (err) {
                        if (clip.videoUrl) {
                            window.location.href = clip.videoUrl;
                        } else {
                            window.location.href = getClipVideoUrl(clipIdentifier);
                        }
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

        // Reconstruir o video preview real
        const videoUrl = clip.videoUrl || getClipVideoUrl(clipIdentifier);
        const thumbnailUrl = clip.thumbnailUrl || getClipThumbnailUrl(clipIdentifier);
        videoContainer.innerHTML = `
            <div id="editor-video-wrapper" style="width: 100%; border-radius: var(--radius-md); overflow: hidden; background: #000; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border-subtle); transition: aspect-ratio 0.3s ease;">
                <video id="editor-video-player" src="${videoUrl}" poster="${thumbnailUrl}" style="width: 100%; height: 100%; object-fit: contain;" autoplay controls loop></video>
            </div>
        `;
        updatePlayerAspect(currentRatio);

        // Atualiza para URL assinada recente se necessário
        if (!clip.videoUrl) {
            fetchSignedUrl(clipIdentifier).then(data => {
                const player = document.getElementById('editor-video-player');
                if (player) player.src = data.download_url;
            }).catch(() => {});
        }

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
                    
                    let refreshedUrl = getClipVideoUrl(clipIdentifier, `t=${Date.now()}`);
                    try {
                        const signedData = await fetchSignedUrl(clipIdentifier);
                        refreshedUrl = signedData.download_url;
                    } catch (e) {}

                    // Baixar automaticamente apenas após conclusão confirmada
                    window.location.href = refreshedUrl;
                    
                    // Recarregar preview
                    const currentVideoEl = document.getElementById('editor-video-player');
                    if (currentVideoEl) {
                        currentVideoEl.src = refreshedUrl;
                        currentVideoEl.play();
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
