// UI Controller and rendering helpers
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
            
            const scoreClass = clip.viralScore >= 90 ? 'viral-score-high' : 'viral-score-med';
            const cardRatio = clip.aspectRatio === '16:9' ? '16/9' : (clip.aspectRatio === '1:1' ? '1/1' : '9/16');
            
            let mediaContent = `<img src="${clip.thumbnail}" alt="${clip.title}">
                                <div class="clip-overlay-play"><i class="fa-solid fa-play"></i></div>`;
            
            if (clip.id.startsWith('clip_')) {
                // Vídeo real processado
                mediaContent = `<video src="/api/v1/video/download/${clip.id}" controls style="width: 100%; height: 100%; object-fit: contain; background: #000;"></video>`;
            }

            card.innerHTML = `
                <div class="clip-preview-container" data-id="${clip.id}" style="aspect-ratio: ${cardRatio};">
                    ${mediaContent}
                    <div class="clip-badges">
                        <div class="viral-badge ${scoreClass}">
                            <i class="fa-solid fa-fire"></i> ${clip.viralScore}/100
                        </div>
                        <div class="clip-duration">${clip.duration}</div>
                    </div>
                </div>
                <div class="clip-details">
                    <div>
                        <h3 class="clip-card-title">${clip.id.startsWith('clip_') ? 'Seu Clipe Gerado (IA)' : clip.title}</h3>
                        <p class="clip-card-hook">${clip.id.startsWith('clip_') ? 'Gancho otimizado e cortes precisos feitos pela inteligência artificial.' : clip.hookReason}</p>
                    </div>
                    <div class="clip-card-actions">
                        <button class="btn-secondary btn-sm block btn-edit" data-id="${clip.id}">
                            <i class="fa-solid fa-pen-to-square"></i> Editar Clipe
                        </button>
                        <button class="btn-primary btn-sm block btn-download" data-id="${clip.id}">
                            <i class="fa-solid fa-download"></i> Baixar
                        </button>
                    </div>
                </div>
            `;

            container.appendChild(card);
        });

        // Bind clicks for edit and preview
        container.querySelectorAll('.btn-edit').forEach(el => {
            el.addEventListener('click', (e) => {
                const clipId = el.getAttribute('data-id');
                const clip = clips.find(c => c.id === clipId);
                if (clip) {
                    UI.openEditorModal(clip);
                }
            });
        });

        container.querySelectorAll('.btn-download').forEach(el => {
            el.addEventListener('click', (e) => {
                e.stopPropagation();
                const clipId = el.getAttribute('data-id');
                
                // Previne mock downloads
                if (!clipId.startsWith('clip_')) {
                    alert('Este é apenas um clipe de demonstração (mock). Faça upload de um vídeo real para baixar o arquivo gerado!');
                    return;
                }

                // Dispara o download diretamente pelo navegador
                window.location.href = `/api/v1/video/download/${clipId}`;
            });
        });
    },

    openEditorModal(clip) {
        UI.currentClip = clip;
        const modal = document.getElementById('editor-modal');
        const transcriptContainer = document.getElementById('transcript-container');
        const videoContainer = document.querySelector('.video-preview-container');
        
        if (!modal || !transcriptContainer) return;

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

        // Limpar e reconstruir o video preview
        if (clip.id.startsWith('clip_')) {
            videoContainer.innerHTML = `
                <div id="editor-video-wrapper" style="width: 100%; border-radius: var(--radius-md); overflow: hidden; background: #000; display: flex; align-items: center; justify-content: center; border: 1px solid var(--border-subtle); transition: aspect-ratio 0.3s ease;">
                    <video id="editor-video-player" src="/api/v1/video/download/${clip.id}" style="width: 100%; height: 100%; object-fit: contain;" autoplay controls loop></video>
                </div>
            `;
            updatePlayerAspect(currentRatio);
        } else {
            // Mock preview format (fallback)
            videoContainer.innerHTML = `
                <div class="video-player-mock">
                    <i class="fa-solid fa-play play-icon"></i>
                    <div class="mock-captions">Cole um link <span>acima</span></div>
                </div>
            `;
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
            // Duração do mock normalmente é string "12s"
            const durationSec = clip.duration ? parseFloat(clip.duration.toString().replace('s', '')) : 0;
            trimEndInput.value = clip.endTime || durationSec;
        }

        const words = clip.words || [];
        words.forEach((w, idx) => {
            const wordEl = document.createElement('div');
            wordEl.className = `transcript-word ${w.highlighted ? 'highlighted' : ''}`;
            wordEl.setAttribute('data-index', idx);
            wordEl.innerHTML = `
                <span contenteditable="true" class="editable-word">${w.text}</span>
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

        // Export logic
        const btnExport = document.getElementById('btn-export-clip');
        if (btnExport) {
            // Removendo listeners antigos (clonando)
            const newBtn = btnExport.cloneNode(true);
            btnExport.parentNode.replaceChild(newBtn, btnExport);
            
            newBtn.addEventListener('click', async () => {
                if (!clip.id.startsWith('clip_')) {
                    alert('Este é um clipe mockado. Para exportar, use um clipe real.');
                    return;
                }
                
                const originalText = newBtn.innerHTML;
                newBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Renderizando...';
                newBtn.disabled = true;
                
                const style = document.getElementById('caption-style-select').value || 'Yellow';
                const trimStart = parseFloat(document.getElementById('trim-start').value || 0);
                const trimEnd = parseFloat(document.getElementById('trim-end').value || 0);
                const aspectRatio = document.getElementById('aspect-ratio-select').value || '9:16';
                const addSubtitles = document.getElementById('toggle-subtitles').checked;
                const quality = document.getElementById('quality-select').value || '1080p';
                
                try {
                    const res = await fetch(`/api/v1/project/clip/${clip.clipId || clip.id}/re-render`, {
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
                    
                    if (!res.ok) throw new Error('Erro na renderização');
                    
                    // Baixar automaticamente
                    window.location.href = `/api/v1/video/download/${clip.id}?t=${Date.now()}`;
                    
                    // Recarregar preview
                    const currentVideoEl = document.getElementById('editor-video-player');
                    if (currentVideoEl) {
                        currentVideoEl.src = `/api/v1/video/download/${clip.id}?t=${Date.now()}`;
                        currentVideoEl.play();
                    }
                    
                    clip.captionConfig = style; // sync state locally
                    clip.aspectRatio = aspectRatio; // sync aspect ratio
                    clip.startTime = trimStart;
                    clip.endTime = trimEnd;
                    updatePlayerAspect(aspectRatio);

                    // Atualiza o card de preview na listagem principal
                    const cardPreview = document.querySelector(`.clip-preview-container[data-id="${clip.id}"]`);
                    if (cardPreview) {
                        const newCardRatio = aspectRatio === '16:9' ? '16/9' : (aspectRatio === '1:1' ? '1/1' : '9/16');
                        cardPreview.style.aspectRatio = newCardRatio;
                        const cardVideo = cardPreview.querySelector('video');
                        if (cardVideo) {
                            cardVideo.src = `/api/v1/video/download/${clip.id}?t=${Date.now()}`;
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
    },

    closeEditorModal() {
        const modal = document.getElementById('editor-modal');
        if (modal) modal.classList.add('hidden');
        
        const videoEl = document.getElementById('editor-video-player');
        if (videoEl) videoEl.pause();
    },

    highlightActiveWord(index) {
        const words = document.querySelectorAll('.transcript-word');
        words.forEach((el, idx) => {
            if (idx === index) {
                el.classList.add('active');
                // Scroll only if it's not fully visible to avoid jumpy UI
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
