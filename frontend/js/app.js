// Main application logic and orchestrator
document.addEventListener('DOMContentLoaded', () => {

    const showToast = (msg, type = 'info', duration = 4500) => {
        if (typeof window.showToast === 'function') {
            return window.showToast(msg, type, duration);
        }
        console.warn(`[Toast ${type}]: ${msg}`);
    };

    const API_BASE = '/api';
    let authToken = localStorage.getItem('clipmaker_token') || null;

    // --- Auth UI Logic ---
    const authModal = document.getElementById('auth-modal');
    const btnLoginNav = document.getElementById('btn-login-nav');
    const btnRegisterNav = document.getElementById('btn-register-nav');
    const btnCloseAuth = document.getElementById('btn-close-auth');
    const authForm = document.getElementById('auth-form');
    const authToggleMode = document.getElementById('auth-toggle-mode');
    const authTitle = document.getElementById('auth-title');
    const authEmail = document.getElementById('auth-email');
    const authPassword = document.getElementById('auth-password');
    const btnSubmitAuth = document.getElementById('btn-submit-auth');
    let isLoginMode = true;

    function updateNav() {
        if (authToken) {
            if (btnLoginNav) btnLoginNav.innerText = "Sair";
            if (btnRegisterNav) btnRegisterNav.style.display = "none";
        } else {
            if (btnLoginNav) btnLoginNav.innerText = "Login";
            if (btnRegisterNav) btnRegisterNav.style.display = "inline-flex";
        }
    }
    updateNav();

    if (btnLoginNav) {
        btnLoginNav.addEventListener('click', (e) => {
            e.preventDefault();
            if (authToken) {
                authToken = null;
                localStorage.removeItem('clipmaker_token');
                localStorage.removeItem('clipmaker_active_project');
                localStorage.removeItem('clipmaker_active_source_name');
                if (typeof stopPolling === 'function') stopPolling();
                updateNav();
                if (typeof switchView === 'function') switchView('home');
                const url = new URL(window.location.href);
                url.searchParams.delete('project');
                history.replaceState({ page: 'home' }, '', url.pathname);
                showToast("Você saiu da sua conta.", "info");
            } else {
                isLoginMode = true;
                updateAuthModalUI();
                authModal.classList.remove('hidden');
            }
        });
    }

    if (btnRegisterNav) {
        btnRegisterNav.addEventListener('click', (e) => {
            e.preventDefault();
            isLoginMode = false;
            updateAuthModalUI();
            authModal.classList.remove('hidden');
        });
    }

    if (btnCloseAuth) {
        btnCloseAuth.addEventListener('click', () => authModal.classList.add('hidden'));
    }

    if (authToggleMode) {
        authToggleMode.addEventListener('click', (e) => {
            e.preventDefault();
            isLoginMode = !isLoginMode;
            updateAuthModalUI();
        });
    }

    function updateAuthModalUI() {
        if (isLoginMode) {
            authTitle.innerText = "Entrar";
            btnSubmitAuth.innerText = "Entrar";
            authToggleMode.innerText = "Não tem uma conta? Cadastre-se";
        } else {
            authTitle.innerText = "Cadastrar";
            btnSubmitAuth.innerText = "Criar Conta";
            authToggleMode.innerText = "Já tem uma conta? Entrar";
        }
    }

    function parseApiError(errorData, defaultMessage) {
        if (!errorData) return defaultMessage;
        if (typeof errorData === "string") return errorData;
        if (typeof errorData.detail === "string") return errorData.detail;
        if (Array.isArray(errorData.detail)) {
            return errorData.detail.map(item => {
                if (typeof item === "string") return item;
                if (item && item.loc) {
                    const field = item.loc[item.loc.length - 1];
                    if (field === "password") {
                        if (item.type === "string_too_short") {
                            const minLen = appConfig.min_password_length || 8;
                            return `A senha deve ter no mínimo ${minLen} caracteres.`;
                        }
                        return `Senha: ${item.msg || "inválida"}`;
                    }
                    if (field === "email") return "Por favor, digite um endereço de e-mail válido.";
                    return `${field}: ${item.msg || "inválido"}`;
                }
                return item.msg || JSON.stringify(item);
            }).join("\n");
        }
        if (errorData.detail && typeof errorData.detail === "object") {
            return JSON.stringify(errorData.detail);
        }
        return defaultMessage;
    }

    if (authForm) {
        authForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = authEmail.value.trim();
            const password = authPassword.value;
            btnSubmitAuth.disabled = true;
            btnSubmitAuth.innerText = "Aguarde...";

            try {
                if (isLoginMode) {
                    const formData = new URLSearchParams();
                    formData.append("username", email);
                    formData.append("password", password);

                    const res = await fetch(`${API_BASE}/auth/login`, {
                        method: "POST",
                        headers: { "Content-Type": "application/x-www-form-urlencoded" },
                        body: formData
                    });
                    
                    const resData = await res.json().catch(() => null);
                    if (!res.ok) {
                        throw new Error(parseApiError(resData, "Erro ao entrar"));
                    }
                    authToken = resData.access_token;
                    localStorage.setItem('clipmaker_token', authToken);
                    updateNav();
                    authModal.classList.add('hidden');

                    const pendingProject = new URLSearchParams(window.location.search).get('project') || localStorage.getItem('clipmaker_active_project');
                    if (pendingProject && typeof loadProject === 'function') {
                        const storedSourceName = localStorage.getItem('clipmaker_active_source_name') || 'Vídeo';
                        loadProject(pendingProject, storedSourceName, { replaceHistory: true });
                    }
                } else {
                    const res = await fetch(`${API_BASE}/auth/register`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ email, password, name: email.split('@')[0] })
                    });
                    const resData = await res.json().catch(() => null);
                    if (!res.ok) {
                        throw new Error(parseApiError(resData, "Erro ao cadastrar"));
                    }
                    showToast("Conta criada com sucesso! Faça login agora.", "success");
                    isLoginMode = true;
                    updateAuthModalUI();
                }
            } catch (err) {
                showToast(err.message || "Ocorreu um erro inesperado.", "error");
            } finally {
                btnSubmitAuth.disabled = false;
                updateAuthModalUI();
            }
        });
    }

    // --- End Auth ---

    window.addEventListener('scroll', () => {
        const nav = document.querySelector('.navbar');
        if (window.scrollY > 30) nav.classList.add('scrolled');
        else nav.classList.remove('scrolled');
    });

    const tabButtons = document.querySelectorAll('.tab-btn');
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            tabButtons.forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            const targetId = `tab-${btn.dataset.tab}`;
            const targetContent = document.getElementById(targetId);
            if (targetContent) targetContent.classList.add('active');
        });
    });

    const ratioPills = document.querySelectorAll('.ratio-pill');
    ratioPills.forEach(pill => {
        pill.addEventListener('click', () => {
            ratioPills.forEach(p => {
                p.classList.remove('active');
                p.style.borderColor = 'var(--border-subtle)';
                p.style.color = 'var(--text-300)';
                const input = p.querySelector('input');
                if (input) input.checked = false;
            });
            pill.classList.add('active');
            pill.style.borderColor = 'var(--accent-ai)';
            pill.style.color = 'var(--text-100)';
            const input = pill.querySelector('input');
            if (input) input.checked = true;
        });
    });

    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const btnBrowse = document.getElementById('btn-browse');

    if (btnBrowse && fileInput) btnBrowse.addEventListener('click', (e) => { e.stopPropagation(); fileInput.click(); });

    if (dropZone) {
        dropZone.addEventListener('click', () => fileInput.click());
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => { e.preventDefault(); e.stopPropagation(); dropZone.classList.add('drag-over'); });
        });
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, (e) => { e.preventDefault(); e.stopPropagation(); dropZone.classList.remove('drag-over'); });
        });
        dropZone.addEventListener('drop', (e) => {
            if (e.dataTransfer.files.length > 0) startProcessingPipeline(e.dataTransfer.files[0], true);
        });
    }

    if (fileInput) fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) startProcessingPipeline(e.target.files[0], true);
    });

    const btnGenerateUrl = document.getElementById('btn-generate-url');
    const videoUrlInput = document.getElementById('video-url');

    if (btnGenerateUrl) {
        btnGenerateUrl.addEventListener('click', () => {
            const url = videoUrlInput.value.trim();
            if (!url) { showToast('Insira um link válido.', 'error'); videoUrlInput.focus(); return; }
            startProcessingPipeline(url, false);
        });
    }

    // --- View Navigation & State Management ---
    function switchView(viewName) {
        const heroSection = document.getElementById('hero-section');
        const processingSection = document.getElementById('processing-section');
        const resultsSection = document.getElementById('results-section');

        if (heroSection) heroSection.classList.toggle('hidden', viewName !== 'home');
        if (processingSection) processingSection.classList.toggle('hidden', viewName !== 'processing');
        if (resultsSection) resultsSection.classList.toggle('hidden', viewName !== 'results');
    }

    const stepLabels = [
        "Baixando mídia",
        "Transcrevendo áudio com IA",
        "Detectando momentos virais",
        "Renderizando cortes e legendas"
    ];

    function updateStepUI(stepIndex) {
        ['step-1', 'step-2', 'step-3', 'step-4'].forEach((id, idx) => {
            const el = document.getElementById(id);
            if (!el) return;
            const label = stepLabels[idx];
            if (idx < stepIndex) {
                el.className = 'step done';
                el.innerHTML = `<i class="fa-solid fa-check"></i> ${label}`;
            } else if (idx === stepIndex) {
                el.className = 'step active';
                el.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${label}`;
            } else {
                el.className = 'step pending';
                el.innerHTML = `<i class="fa-solid fa-circle" style="font-size: 0.5rem;"></i> ${label}`;
            }
        });
    }

    let isProcessing = false;
    let pollingInterval = null;
    let pollingTimeout = null;
    let currentRenderedProjectId = null;
    let currentUploadXhr = null;
    let appConfig = { max_file_size_mb: 2000, max_duration_sec: 14400, min_password_length: 8 };

    async function loadAppConfig() {
        try {
            const res = await fetch(`${API_BASE}/v1/config`);
            if (res.ok) {
                appConfig = await res.json();
                const limitEl = document.getElementById('upload-limit-text');
                if (limitEl && appConfig.max_file_size_mb) {
                    const mb = appConfig.max_file_size_mb;
                    const text = mb >= 1000 ? `${(mb / 1000).toFixed(mb % 1000 === 0 ? 0 : 1)}GB` : `${mb}MB`;
                    limitEl.innerText = `MP4, MOV ou WEBM — até ${text}`;
                }
                if (authPassword && appConfig.min_password_length) {
                    authPassword.minLength = appConfig.min_password_length;
                    authPassword.placeholder = `Sua senha (mínimo ${appConfig.min_password_length} caracteres)`;
                }
            }
        } catch (e) {
            console.warn("Não foi possível carregar config dinâmico da API:", e);
        }
    }
    loadAppConfig();

    function stopPolling() {
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
        if (pollingTimeout) {
            clearTimeout(pollingTimeout);
            pollingTimeout = null;
        }
        const errContainer = document.getElementById('polling-error-container');
        if (errContainer) errContainer.remove();
    }

    function resetUIState() {
        isProcessing = false;
        if (currentUploadXhr) {
            try { currentUploadXhr.abort(); } catch (e) {}
            currentUploadXhr = null;
        }
        const cancelBtn = document.getElementById('btn-cancel-upload');
        if (cancelBtn) cancelBtn.classList.add('hidden');
        if (btnGenerateUrl) {
            btnGenerateUrl.disabled = false;
            btnGenerateUrl.innerHTML = 'Processar Link';
        }
        if (fileInput) fileInput.disabled = false;
        if (btnBrowse) btnBrowse.disabled = false;
    }

    function uploadWithRealProgress(file, uploadRatio, onProgress, onSuccess, onError) {
        const xhr = new XMLHttpRequest();
        currentUploadXhr = xhr;

        xhr.upload.addEventListener('progress', (e) => {
            if (e.lengthComputable) {
                const percent = Math.round((e.loaded / e.total) * 100);
                const loadedMB = (e.loaded / (1024 * 1024)).toFixed(1);
                const totalMB = (e.total / (1024 * 1024)).toFixed(1);
                onProgress(percent, loadedMB, totalMB);
            }
        });

        xhr.addEventListener('load', () => {
            currentUploadXhr = null;
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    const data = JSON.parse(xhr.responseText);
                    onSuccess(data);
                } catch(e) {
                    onError(new Error("Resposta inválida do servidor."));
                }
            } else {
                let detail = xhr.statusText;
                try {
                    const err = JSON.parse(xhr.responseText);
                    if (err.detail) detail = err.detail;
                } catch(e) {}
                onError(new Error(detail || `Erro no upload (${xhr.status})`));
            }
        });

        xhr.addEventListener('error', () => {
            currentUploadXhr = null;
            onError(new Error("Falha de conexão durante o upload do vídeo."));
        });

        xhr.addEventListener('abort', () => {
            currentUploadXhr = null;
            onError(new Error("Upload cancelado pelo usuário."));
        });

        const formData = new FormData();
        formData.append("file", file);
        formData.append("aspect_ratio", uploadRatio);

        xhr.open("POST", `${API_BASE}/videos/upload-and-process/`);
        xhr.setRequestHeader("Authorization", `Bearer ${authToken}`);
        xhr.send(formData);
    }

    const btnCancelUpload = document.getElementById('btn-cancel-upload');
    if (btnCancelUpload) {
        btnCancelUpload.addEventListener('click', () => {
            if (currentUploadXhr) {
                currentUploadXhr.abort();
                currentUploadXhr = null;
            }
            btnCancelUpload.classList.add('hidden');
            stopPolling();
            switchView('home');
            resetUIState();
        });
    }

    function updateRenderingBanner(data) {
        const resultsSection = document.getElementById('results-section');
        if (!resultsSection) return;
        let banner = document.getElementById('results-rendering-banner');
        const queuePos = data.queuePosition || 1;
        const etaSec = data.estimatedTimeSec || 30;
        const queueSuffix = queuePos > 1 ? ` (Fila #${queuePos} • ~${etaSec}s)` : ` (~${etaSec}s restantes)`;
        const clipCount = (data.clips && data.clips.length) || 0;

        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'results-rendering-banner';
            banner.className = 'rendering-banner';
            const clipsContainer = document.getElementById('clips-container');
            if (clipsContainer && clipsContainer.parentNode) {
                clipsContainer.parentNode.insertBefore(banner, clipsContainer);
            }
        }

        banner.innerHTML = `
            <div class="rendering-banner-content">
                <i class="fa-solid fa-spinner fa-spin"></i>
                <span>Gerando cortes adicionais com IA... (${clipCount} clipe(s) pronto(s)) • ~${etaSec}s restantes</span>
            </div>
            <div style="font-size: 0.8rem; color: var(--accent-ai); font-weight: 600;">Ao vivo</div>
        `;
    }

    function removeRenderingBanner() {
        const banner = document.getElementById('results-rendering-banner');
        if (banner) banner.remove();
    }

    async function startProcessingPipeline(fileOrUrl, isFile) {
        if (isProcessing) return;
        
        if (!authToken) {
            showToast("Por favor, faça login ou cadastre-se para gerar clipes!", "info");
            authModal.classList.remove('hidden');
            return;
        }

        isProcessing = true;
        
        if (btnGenerateUrl) {
            btnGenerateUrl.disabled = true;
            btnGenerateUrl.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Processando...';
        }
        if (fileInput) fileInput.disabled = true;
        if (btnBrowse) btnBrowse.disabled = true;

        switchView('processing');
        updateStepUI(0);

        const percentageEl = document.getElementById('processing-percentage');
        const progressFill = document.getElementById('progress-fill');
        if (percentageEl) percentageEl.innerText = "0%";
        if (progressFill) progressFill.style.width = "5%";

        const uploadRatio = document.querySelector('input[name="upload-ratio"]:checked')?.value || '9:16';

        // Item 7: Upload real com XMLHttpRequest, barra de progresso e botão de cancelar
        if (isFile) {
            const maxMB = appConfig.max_file_size_mb || 2000;
            if (fileOrUrl.size > maxMB * 1024 * 1024) {
                const sizeMB = (fileOrUrl.size / (1024 * 1024)).toFixed(1);
                showToast(`O arquivo selecionado (${sizeMB}MB) ultrapassa o limite máximo de ${maxMB}MB suportado pelo servidor.`, "error");
                switchView('home');
                resetUIState();
                return;
            }

            if (percentageEl) percentageEl.innerText = "Preparando upload...";
            const cancelBtn = document.getElementById('btn-cancel-upload');
            if (cancelBtn) cancelBtn.classList.remove('hidden');

            uploadWithRealProgress(
                fileOrUrl,
                uploadRatio,
                (percent, loadedMB, totalMB) => {
                    if (progressFill) progressFill.style.width = `${Math.max(5, percent)}%`;
                    if (percentageEl) percentageEl.innerText = `Enviando vídeo: ${percent}% (${loadedMB}MB de ${totalMB}MB)`;
                    if (percent >= 100) {
                        if (cancelBtn) cancelBtn.classList.add('hidden');
                        if (percentageEl) percentageEl.innerText = "Upload concluído! Iniciando processamento com IA...";
                    }
                },
                (data) => {
                    if (cancelBtn) cancelBtn.classList.add('hidden');
                    if (data.status === "processing" && data.project_id) {
                        const sourceName = fileOrUrl.name;
                        localStorage.setItem('clipmaker_active_project', data.project_id);
                        localStorage.setItem('clipmaker_active_source_name', sourceName);

                        const url = new URL(window.location.href);
                        url.searchParams.set('project', data.project_id);
                        history.pushState({ page: 'processing', projectId: data.project_id, sourceName }, '', url.toString());

                        updateStepUI(0);
                        if (percentageEl) percentageEl.innerText = "Iniciando processamento na fila...";
                        pollProjectStatus(data.project_id, sourceName);
                    } else {
                        throw new Error("Resposta inesperada do servidor.");
                    }
                },
                (error) => {
                    if (cancelBtn) cancelBtn.classList.add('hidden');
                    if (error.message !== "Upload cancelado pelo usuário.") {
                        showToast("Erro: " + error.message, "error");
                    }
                    switchView('home');
                    resetUIState();
                }
            );
            return;
        }

        // Processamento de link de vídeo por URL
        const formData = new FormData();
        formData.append("aspect_ratio", uploadRatio);
        formData.append("url", fileOrUrl);
        if (percentageEl) percentageEl.innerText = "Enviando solicitação de download...";

        try {
            const response = await fetch(`${API_BASE}/videos/upload-url/`, {
                method: "POST",
                headers: { "Authorization": `Bearer ${authToken}` },
                body: formData,
            });

            if (!response.ok) {
                let errDetail = response.statusText;
                try {
                    const errData = await response.json();
                    if (errData.detail) errDetail = errData.detail;
                } catch(e) {}
                
                if (response.status === 401) {
                    authToken = null;
                    localStorage.removeItem('clipmaker_token');
                    updateNav();
                    authModal.classList.remove('hidden');
                    switchView('home');
                    resetUIState();
                    return;
                }
                throw new Error(errDetail);
            }
            
            const data = await response.json();
            
            if (data.status === "processing" && data.project_id) {
                const sourceName = fileOrUrl;
                localStorage.setItem('clipmaker_active_project', data.project_id);
                localStorage.setItem('clipmaker_active_source_name', sourceName);

                const url = new URL(window.location.href);
                url.searchParams.set('project', data.project_id);
                history.pushState({ page: 'processing', projectId: data.project_id, sourceName }, '', url.toString());

                updateStepUI(0);
                if (percentageEl) percentageEl.innerText = "Baixando mídia via fila...";
                pollProjectStatus(data.project_id, sourceName);
            } else {
                throw new Error("Resposta inesperada do servidor.");
            }
        } catch (error) {
            showToast("Erro: " + error.message, "error");
            switchView('home');
            resetUIState();
        }
    }

    async function pollProjectStatus(projectId, sourceName) {
        stopPolling();
        const percentageEl = document.getElementById('processing-percentage');
        const progressFill = document.getElementById('progress-fill');
        const processingSection = document.getElementById('processing-section');
        let consecutiveFailures = 0;
        let pollCount = 0;

        const scheduleNext = () => {
            if (!isProcessing) return;
            pollCount++;
            // Item 5: Polling com backoff progressivo (3s -> 5s -> 10s)
            let delayMs = 3000;
            if (pollCount === 1) delayMs = 3000;
            else if (pollCount === 2) delayMs = 5000;
            else delayMs = 10000;

            pollingTimeout = setTimeout(checkStatus, delayMs);
        };

        const checkStatus = async () => {
            if (!isProcessing) return;
            try {
                // Item 5: Removido ?_t=Date.now() (Nginx já responde com Cache-Control: no-store)
                const res = await fetch(`${API_BASE}/projects/${projectId}/status`, {
                    headers: { "Authorization": `Bearer ${authToken}` }
                });

                if (!res.ok) {
                    if (res.status === 401) {
                        stopPolling();
                        authToken = null;
                        localStorage.removeItem('clipmaker_token');
                        updateNav();
                        authModal.classList.remove('hidden');
                        switchView('home');
                        resetUIState();
                        return;
                    }
                    throw new Error(`Falha ao checar status (${res.status})`);
                }

                consecutiveFailures = 0;
                const existingErr = document.getElementById('polling-error-container');
                if (existingErr) existingErr.remove();

                const data = await res.json();
                const finalTitle = data.title || sourceName || "Projeto Salvo";

                // Item 1: Mostre cada clipe assim que ficar pronto sem esperar o projeto inteiro!
                if (data.clips && data.clips.length > 0 && data.status !== 'FAILED') {
                    const sourceEl = document.querySelector('.source-name');
                    if (sourceEl) sourceEl.innerText = finalTitle;
                    localStorage.setItem('clipmaker_active_project', projectId);
                    localStorage.setItem('clipmaker_active_source_name', finalTitle);

                    switchView('results');
                    UI.renderClips(data.clips, projectId);

                    if (data.status !== 'READY') {
                        updateRenderingBanner(data);
                    }
                }

                if (data.status === 'READY') {
                    stopPolling();
                    currentRenderedProjectId = projectId;
                    removeRenderingBanner();
                    if (percentageEl) {
                        percentageEl.classList.remove('pulse-animation');
                        percentageEl.innerText = "100%";
                    }
                    if (progressFill) progressFill.style.width = '100%';
                    updateStepUI(4);

                    switchView('results');
                    const sourceEl = document.querySelector('.source-name');
                    if (sourceEl) sourceEl.innerText = finalTitle;

                    localStorage.setItem('clipmaker_active_project', projectId);
                    localStorage.setItem('clipmaker_active_source_name', finalTitle);

                    const url = new URL(window.location.href);
                    url.searchParams.set('project', projectId);
                    history.replaceState({ page: 'results', projectId, sourceName: finalTitle }, '', url.toString());

                    UI.renderClips(data.clips || [], projectId);
                    resetUIState();
                } else if (data.status === 'FAILED') {
                    stopPolling();
                    removeRenderingBanner();
                    if (percentageEl) percentageEl.classList.remove('pulse-animation');
                    showToast("Erro no processamento: " + (data.error || "Desconhecido"), "error");
                    localStorage.removeItem('clipmaker_active_project');
                    localStorage.removeItem('clipmaker_active_source_name');
                    const url = new URL(window.location.href);
                    url.searchParams.delete('project');
                    history.replaceState({ page: 'home' }, '', url.pathname);
                    switchView('home');
                    resetUIState();
                } else {
                    if (percentageEl) percentageEl.classList.add('pulse-animation');
                    
                    const queuePos = data.queuePosition || 1;
                    const etaSec = data.estimatedTimeSec || 30;
                    const queueSuffix = queuePos > 1 ? ` (Fila #${queuePos} • ~${etaSec}s)` : ` (~${etaSec}s restantes)`;

                    // Progresso real derivado da API (sem incrementos simulados de +5%)
                    if (data.status === 'DOWNLOADING') {
                        updateStepUI(0);
                        if (percentageEl) percentageEl.innerText = `Baixando vídeo por URL via fila...${queueSuffix}`;
                        if (progressFill) progressFill.style.width = '15%';
                    } else if (data.status === 'TRANSCRIBING') {
                        updateStepUI(1);
                        if (percentageEl) percentageEl.innerText = `Extraindo áudio e transcrevendo com IA...${queueSuffix}`;
                        if (progressFill) progressFill.style.width = '35%';
                    } else if (data.status === 'ANALYZING') {
                        updateStepUI(2);
                        if (percentageEl) percentageEl.innerText = `Detectando momentos virais com IA...${queueSuffix}`;
                        if (progressFill) progressFill.style.width = '65%';
                    } else if (data.status === 'RENDERING') {
                        updateStepUI(3);
                        if (percentageEl) percentageEl.innerText = `Renderizando cortes no formato vertical...${queueSuffix}`;
                        if (progressFill) progressFill.style.width = '85%';
                    } else {
                        updateStepUI(0);
                        if (percentageEl) percentageEl.innerText = `Na fila de processamento...${queueSuffix}`;
                        if (progressFill) progressFill.style.width = '10%';
                    }
                    scheduleNext();
                }
            } catch (err) {
                console.error("Falha no polling:", err);
                consecutiveFailures++;
                if (consecutiveFailures >= 5) {
                    stopPolling();
                    if (percentageEl) {
                        percentageEl.classList.remove('pulse-animation');
                        percentageEl.innerText = "Falha de conexão";
                    }
                    let errContainer = document.getElementById('polling-error-container');
                    if (!errContainer && processingSection) {
                        errContainer = document.createElement('div');
                        errContainer.id = 'polling-error-container';
                        errContainer.style.cssText = 'text-align: center; margin-top: 1.5rem; padding: 1.25rem; background: rgba(239, 68, 68, 0.1); border-radius: var(--radius-md); border: 1px solid var(--danger, #ef4444);';
                        errContainer.innerHTML = `
                            <p style="color: var(--danger, #ef4444); font-weight: 500; margin-bottom: 1rem;">
                                Conexão instável. Não foi possível consultar o status do projeto após 5 tentativas consecutivas.
                            </p>
                            <div style="display: flex; gap: 0.75rem; justify-content: center;">
                                <button id="btn-retry-poll" class="btn-primary btn-sm">Tentar novamente</button>
                                <button id="btn-cancel-poll" class="btn-secondary btn-sm">Voltar ao início</button>
                            </div>
                        `;
                        processingSection.appendChild(errContainer);

                        document.getElementById('btn-retry-poll')?.addEventListener('click', () => {
                            errContainer.remove();
                            isProcessing = true;
                            pollProjectStatus(projectId, sourceName);
                        });

                        document.getElementById('btn-cancel-poll')?.addEventListener('click', () => {
                            errContainer.remove();
                            stopPolling();
                            switchView('home');
                            resetUIState();
                        });
                    }
                } else {
                    pollingTimeout = setTimeout(checkStatus, Math.min(15000, 2000 * Math.pow(1.5, consecutiveFailures)));
                }
            }
        };

        checkStatus();
    }

    async function loadProject(projectId, sourceName, options = { pushHistory: false, replaceHistory: false }) {
        if (!projectId || !authToken) return false;

        const resultsSection = document.getElementById('results-section');
        const isResultsAlreadyVisible = resultsSection && !resultsSection.classList.contains('hidden');

        if (!isResultsAlreadyVisible) {
            switchView('processing');
            const percentageEl = document.getElementById('processing-percentage');
            if (percentageEl) percentageEl.innerText = "Recuperando projeto...";
        }

        try {
            const res = await fetch(`${API_BASE}/projects/${projectId}/status`, {
                headers: { "Authorization": `Bearer ${authToken}` }
            });

            if (!res.ok) {
                if (res.status === 401) {
                    authToken = null;
                    localStorage.removeItem('clipmaker_token');
                    updateNav();
                    authModal.classList.remove('hidden');
                    switchView('home');
                    resetUIState();
                    return false;
                }
                if (res.status === 404 || res.status === 403) {
                    localStorage.removeItem('clipmaker_active_project');
                    localStorage.removeItem('clipmaker_active_source_name');
                    const url = new URL(window.location.href);
                    url.searchParams.delete('project');
                    history.replaceState({ page: 'home' }, '', url.pathname);
                    switchView('home');
                    resetUIState();
                    return false;
                }
                throw new Error(`Falha ao obter status (${res.status})`);
            }

            const data = await res.json();
            const finalTitle = data.title || sourceName || "Projeto Salvo";

            if (data.status === 'READY') {
                stopPolling();
                currentRenderedProjectId = projectId;
                switchView('results');
                const sourceEl = document.querySelector('.source-name');
                if (sourceEl) sourceEl.innerText = finalTitle;

                localStorage.setItem('clipmaker_active_project', projectId);
                localStorage.setItem('clipmaker_active_source_name', finalTitle);

                const url = new URL(window.location.href);
                url.searchParams.set('project', projectId);
                if (options.pushHistory) {
                    history.pushState({ page: 'results', projectId, sourceName: finalTitle }, '', url.toString());
                } else if (options.replaceHistory || url.searchParams.get('project') !== projectId) {
                    history.replaceState({ page: 'results', projectId, sourceName: finalTitle }, '', url.toString());
                }

                UI.renderClips(data.clips || [], projectId);
                resetUIState();
                return true;
            } else if (data.status === 'FAILED') {
                stopPolling();
                showToast("Erro no processamento do vídeo: " + (data.error || "Desconhecido"), "error");
                localStorage.removeItem('clipmaker_active_project');
                localStorage.removeItem('clipmaker_active_source_name');
                const url = new URL(window.location.href);
                url.searchParams.delete('project');
                history.replaceState({ page: 'home' }, '', url.pathname);
                switchView('home');
                resetUIState();
                return false;
            } else {
                isProcessing = true;
                switchView('processing');
                localStorage.setItem('clipmaker_active_project', projectId);
                localStorage.setItem('clipmaker_active_source_name', finalTitle);

                const url = new URL(window.location.href);
                url.searchParams.set('project', projectId);
                if (options.pushHistory) {
                    history.pushState({ page: 'processing', projectId, sourceName: finalTitle }, '', url.toString());
                } else if (options.replaceHistory) {
                    history.replaceState({ page: 'processing', projectId, sourceName: finalTitle }, '', url.toString());
                }

                pollProjectStatus(projectId, finalTitle);
                return true;
            }
        } catch (err) {
            console.error("Erro ao recuperar projeto:", err);
            switchView('home');
            resetUIState();
            return false;
        }
    }

    const btnNewVideo = document.getElementById('btn-new-video');
    if (btnNewVideo) {
        btnNewVideo.addEventListener('click', () => {
            stopPolling();
            localStorage.removeItem('clipmaker_active_project');
            localStorage.removeItem('clipmaker_active_source_name');

            const url = new URL(window.location.href);
            url.searchParams.delete('project');
            history.pushState({ page: 'home' }, '', url.pathname);

            switchView('home');
            if (videoUrlInput) videoUrlInput.value = '';
            if (fileInput) fileInput.value = '';
            resetUIState();
        });
    }

    // Modal navigation handling
    const btnCloseModal = document.getElementById('btn-close-modal');
    const editorModal = document.getElementById('editor-modal');
    if (btnCloseModal) btnCloseModal.addEventListener('click', () => UI.closeEditorModal());
    if (editorModal) editorModal.addEventListener('click', (e) => { if (e.target === editorModal) UI.closeEditorModal(); });

    // History Back / Forward (popstate)
    // Item 2: Ignora a transição editor -> results e nunca re-renderiza se o projeto já estiver visível e inalterado
    window.addEventListener('popstate', (e) => {
        if (UI.isClosingEditor) {
            UI.isClosingEditor = false;
            return;
        }

        if (editorModal && !editorModal.classList.contains('hidden')) {
            editorModal.classList.add('hidden');
            const videoEl = document.getElementById('editor-video-player');
            if (videoEl) videoEl.pause();
            return;
        }
        if (authModal && !authModal.classList.contains('hidden')) {
            authModal.classList.add('hidden');
            return;
        }

        const state = e.state;
        const urlParams = new URLSearchParams(window.location.search);
        const projectIdFromUrl = urlParams.get('project');
        const activeProject = projectIdFromUrl || (state && state.projectId);

        const resultsSection = document.getElementById('results-section');
        const isResultsVisible = resultsSection && !resultsSection.classList.contains('hidden');

        // Ignora transição editor -> results se o projeto já estiver carregado e exibido
        if (activeProject && isResultsVisible && (currentRenderedProjectId === activeProject || UI.renderedProjectId === activeProject)) {
            return;
        }

        if (activeProject) {
            const sourceName = (state && state.sourceName) || localStorage.getItem('clipmaker_active_source_name') || 'Vídeo';
            loadProject(activeProject, sourceName, { replaceHistory: false });
        } else {
            stopPolling();
            switchView('home');
            resetUIState();
        }
    });

    // Check initial history state or URL or localStorage
    const initialUrlParams = new URLSearchParams(window.location.search);
    const initialProjectId = initialUrlParams.get('project') || localStorage.getItem('clipmaker_active_project');
    const initialSourceName = localStorage.getItem('clipmaker_active_source_name') || 'Vídeo';

    if (authToken && initialProjectId) {
        loadProject(initialProjectId, initialSourceName, { replaceHistory: true });
    } else {
        if (!history.state) {
            history.replaceState({ page: 'home' }, '', window.location.href);
        }
        switchView('home');
    }
});
