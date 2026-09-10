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
            
            let mediaContent = `<img src="${clip.thumbnail}" alt="${clip.title}">
                                <div class="clip-overlay-play"><i class="fa-solid fa-play"></i></div>`;
            
            if (clip.id.startsWith('clip_')) {
                // Vídeo real processado
                mediaContent = `<video src="/api/v1/video/download/${clip.id}" controls style="width: 100%; height: 100%; object-fit: cover;"></video>`;
            }

            card.innerHTML = `
                <div class="clip-preview-container" data-id="${clip.id}">
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

        // Limpar e reconstruir o video preview
        if (clip.id.startsWith('clip_')) {
            videoContainer.innerHTML = `
                <video id="editor-video-player" src="/api/v1/video/download/${clip.id}" style="width: 100%; height: 100%; object-fit: cover;" autoplay controls loop></video>
            `;
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
                
                try {
                    const res = await fetch(`/api/v1/project/clip/${clip.id}/re-render`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            words: clip.words,
                            style: style
                        })
                    });
                    
                    if (!res.ok) throw new Error('Erro na renderização');
                    
                    // Baixar automaticamente
                    window.location.href = `/api/v1/video/download/${clip.id}?t=${Date.now()}`;
                    
                    // Recarregar preview
                    if (videoEl) {
                        videoEl.src = `/api/v1/video/download/${clip.id}?t=${Date.now()}`;
                        videoEl.play();
                    }
                    
                    clip.captionConfig = style; // sync state locally
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
