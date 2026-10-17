// UI Controller and rendering helpers

function escapeHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function getClipVideoUrl(clipId, extraParam = '') {
    const token = localStorage.getItem('clipmaker_token') || '';
    const parts = [];
    if (token) parts.push(`token=${encodeURIComponent(token)}`);
    if (extraParam) parts.push(extraParam);
    const qs = parts.length ? `?${parts.join('&')}` : '';
    return `/api/videos/download/${encodeURIComponent(clipId)}${qs}`;
}

function getClipThumbnailUrl(clipId) {
    const token = localStorage.getItem('clipmaker_token') || '';
    const qs = token ? `?token=${encodeURIComponent(token)}` : '';
    return `/api/videos/thumbnail/${encodeURIComponent(clipId)}${qs}`;
}

const UI = {
    currentClip: null,
    playbackTimer: null,
    simulatedCurrentTime: 0,

    renderClips(clips) {
        const container = document.getElementById('clips-container');
        if (!container) return;

        container.innerHTML = '';

        clips.forEach((clip) => {
            const card = document.createElement('div');
            card.className = 'clip-card';
            
            const scoreClass = (clip.viralScore || 0) >= 90 ? 'viral-score-high' : 'viral-score-med';
            const cardRatio = clip.aspectRatio === '16:9' ? '16/9' : (clip.aspectRatio === '1:1' ? '1/1' : '9/16');
            
            const titleSafe = escapeHtml(clip.title || 'Clipe Gerado (IA)');
            const hookSafe = escapeHtml(clip.hookReason || '');
            
            const clipIdentifier = clip.clipId || clip.id;
            const videoUrl = getClipVideoUrl(clipIdentifier);
            const thumbnailUrl = getClipThumbnailUrl(clipIdentifier);
            const mediaContent = `<video src="${videoUrl}" poster="${thumbnailUrl}" controls style="width: 100%; height: 100%; object-fit: contain; background: #000;"></video>`;

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
        });

        // Bind clicks for edit and preview
        container.querySelectorAll('.btn-edit').forEach(el => {
            el.addEventListener('click', () => {
                const clipId = el.getAttribute('data-id');
                const clip = clips.find(c => (c.clipId === clipId || c.id === clipId));
                if (clip) {
                    UI.openEditorModal(clip);
                }
            });
        });

        container.querySelectorAll('.btn-download').forEach(el => {
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                const clipId = el.getAttribute('data-id');
                if (!clipId) return;
                window.location.href = getClipVideoUrl(clipId);
            });
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
        const videoUrl = getClipVideoUrl(clipIdentifier);
        const thumbnailUrl = getClipThumbnailUrl(clipIdentifier);
        videoContainer.innerHTML = `
            <div id="editor-video-wrapper" style="width: 100%; border-radius: var(--radius-md); overflow: hidden; background: #000; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border-subtle); transition: aspect-ratio 0.3s ease;">
                <video id="editor-video-player" src="${videoUrl}" poster="${thumbnailUrl}" style="width: 100%; height: 100%; object-fit: contain;" autoplay controls loop></video>
            </div>
        `;
        updatePlayerAspect(currentRatio);

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
                    const res = await fetch(`/api/projects/clip/${clipIdentifier}/re-render`, {
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
                        const statusRes = await fetch(`/api/projects/clip/${clipIdentifier}/status`, {
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
                    
                    const refreshedUrl = getClipVideoUrl(clipIdentifier, `t=${Date.now()}`);
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
                    alert('Falha ao renderizar clipe: ' + err.message);
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
        const modal = document.getElementById('editor-modal');
        if (modal && !modal.classList.contains('hidden')) {
            modal.classList.add('hidden');
        }
        
        const videoEl = document.getElementById('editor-video-player');
        if (videoEl) videoEl.pause();

        if (history.state && history.state.page === 'editor') {
            history.back();
        }
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
