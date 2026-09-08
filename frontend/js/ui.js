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
                // É um clipe real, renderiza o vídeo!
                mediaContent = `<video src="http://localhost:8000/download/${clip.id}" controls style="width: 100%; height: 100%; object-fit: cover;"></video>`;
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
                window.location.href = `http://localhost:8000/download/${clipId}`;
            });
        });
    },

    openEditorModal(clip) {
        UI.currentClip = clip;
        const modal = document.getElementById('editor-modal');
        const transcriptContainer = document.getElementById('transcript-container');
        const captionDisplay = document.querySelector('.mock-captions');
        
        if (!modal || !transcriptContainer) return;

        transcriptContainer.innerHTML = '';
        captionDisplay.innerHTML = '';

        clip.words.forEach((w, idx) => {
            const wordEl = document.createElement('div');
            wordEl.className = `transcript-word ${w.highlighted ? 'highlighted' : ''}`;
            wordEl.setAttribute('data-index', idx);
            wordEl.innerHTML = `
                <span contenteditable="true" class="editable-word">${w.text}</span>
                <i class="fa-solid fa-star star-btn ${w.highlighted ? 'text-yellow' : ''}" title="Destacar palavra"></i>
            `;

            // Click word to jump playback
            wordEl.addEventListener('click', (e) => {
                if (e.target.classList.contains('star-btn')) {
                    w.highlighted = !w.highlighted;
                    wordEl.classList.toggle('highlighted', w.highlighted);
                    UI.updateLiveCaptions(w.text, w.highlighted);
                } else if (!e.target.classList.contains('editable-word')) {
                    UI.simulatedCurrentTime = w.start;
                    UI.highlightActiveWord(idx);
                    UI.updateLiveCaptions(w.text, w.highlighted);
                }
            });

            // Handle edit change
            const spanEditable = wordEl.querySelector('.editable-word');
            spanEditable.addEventListener('blur', () => {
                w.text = spanEditable.innerText.trim();
                UI.updateLiveCaptions(w.text, w.highlighted);
            });

            transcriptContainer.appendChild(wordEl);
        });

        // Set first word live
        if (clip.words.length > 0) {
            UI.highlightActiveWord(0);
            UI.updateLiveCaptions(clip.words[0].text, clip.words[0].highlighted);
        }

        modal.classList.remove('hidden');
        UI.startSimulatedPlayback();
    },

    closeEditorModal() {
        const modal = document.getElementById('editor-modal');
        if (modal) modal.classList.add('hidden');
        if (UI.playbackTimer) clearInterval(UI.playbackTimer);
    },

    highlightActiveWord(index) {
        const words = document.querySelectorAll('.transcript-word');
        words.forEach((el, idx) => {
            if (idx === index) {
                el.classList.add('active');
                el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            } else {
                el.classList.remove('active');
            }
        });
    },

    updateLiveCaptions(wordText, isHighlighted) {
        const captionDisplay = document.querySelector('.mock-captions');
        if (!captionDisplay) return;
        if (isHighlighted) {
            captionDisplay.innerHTML = `<span>${wordText}</span>`;
        } else {
            captionDisplay.innerHTML = wordText;
        }
    },

    startSimulatedPlayback() {
        if (UI.playbackTimer) clearInterval(UI.playbackTimer);
        let currentWordIdx = 0;

        UI.playbackTimer = setInterval(() => {
            if (!UI.currentClip || !UI.currentClip.words.length) return;

            currentWordIdx = (currentWordIdx + 1) % UI.currentClip.words.length;
            const wordObj = UI.currentClip.words[currentWordIdx];
            
            UI.highlightActiveWord(currentWordIdx);
            UI.updateLiveCaptions(wordObj.text, wordObj.highlighted);

            // Update timeline progress bar
            const timeline = document.querySelector('.timeline-progress');
            if (timeline) {
                const percent = ((currentWordIdx + 1) / UI.currentClip.words.length) * 100;
                timeline.style.width = `${percent}%`;
            }
        }, 650);
    }
};
