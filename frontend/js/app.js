// Main application logic and orchestrator
document.addEventListener('DOMContentLoaded', () => {

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
                alert("Você saiu da sua conta.");
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
                        if (item.type === "string_too_short") return "A senha deve ter no mínimo 6 caracteres.";
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
                    alert("Conta criada com sucesso! Faça login agora.");
                    isLoginMode = true;
                    updateAuthModalUI();
                }
            } catch (err) {
                alert(err.message || "Ocorreu um erro inesperado.");
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
            if (!url) { alert('Insira um link válido.'); videoUrlInput.focus(); return; }
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

    function stopPolling() {
        if (pollingInterval) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
    }

    function resetUIState() {
        isProcessing = false;
        if (btnGenerateUrl) {
            btnGenerateUrl.disabled = false;
            btnGenerateUrl.innerHTML = 'Processar Link';
        }
        if (fileInput) fileInput.disabled = false;
        if (btnBrowse) btnBrowse.disabled = false;
    }

    async function startProcessingPipeline(fileOrUrl, isFile) {
        if (isProcessing) return;
        
        if (!authToken) {
            alert("Por favor, faça login ou cadastre-se para gerar clipes!");
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

        const formData = new FormData();
        const uploadRatio = document.querySelector('input[name="upload-ratio"]:checked')?.value || '9:16';
        formData.append("aspect_ratio", uploadRatio);

        let endpoint = "";
        if (isFile) {
            formData.append("file", fileOrUrl);
            endpoint = `${API_BASE}/videos/upload-and-process/`;
            if (percentageEl) percentageEl.innerText = "Enviando arquivo...";
        } else {
            formData.append("url", fileOrUrl);
            endpoint = `${API_BASE}/videos/upload-url/`;
            if (percentageEl) percentageEl.innerText = "Baixando vídeo (yt-dlp)...";
        }

        try {
            const response = await fetch(endpoint, {
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
                    alert("Sua sessão expirou. Faça login novamente.");
                    authModal.classList.remove('hidden');
                    switchView('home');
                    resetUIState();
                    return;
                }
                throw new Error(errDetail);
            }
            
            const data = await response.json();
            
            if (data.status === "processing" && data.project_id) {
                const sourceName = isFile ? fileOrUrl.name : fileOrUrl;
                localStorage.setItem('clipmaker_active_project', data.project_id);
                localStorage.setItem('clipmaker_active_source_name', sourceName);

                const url = new URL(window.location.href);
                url.searchParams.set('project', data.project_id);
                history.pushState({ page: 'processing', projectId: data.project_id, sourceName }, '', url.toString());

                updateStepUI(1);
                if (percentageEl) percentageEl.innerText = "Na Fila...";
                pollProjectStatus(data.project_id, sourceName);
            } else {
                throw new Error("Resposta inesperada do servidor.");
            }
        } catch (error) {
            alert("Erro: " + error.message);
            switchView('home');
            resetUIState();
        }
    }

    async function pollProjectStatus(projectId, sourceName) {
        stopPolling();
        const percentageEl = document.getElementById('processing-percentage');
        const progressFill = document.getElementById('progress-fill');
        let consecutiveFailures = 0;

        const checkStatus = async () => {
            try {
                const res = await fetch(`${API_BASE}/projects/${projectId}/status?_t=${Date.now()}`, {
                    headers: { "Authorization": `Bearer ${authToken}` }
                });

                if (!res.ok) {
                    if (res.status === 401) {
                        stopPolling();
                        alert("Sessão expirada durante o processamento. Faça login novamente.");
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
                const data = await res.json();
                const finalTitle = data.title || sourceName || "Projeto Salvo";

                if (data.status === 'READY') {
                    stopPolling();
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

                    UI.renderClips(data.clips || []);
                    resetUIState();
                } else if (data.status === 'FAILED') {
                    stopPolling();
                    if (percentageEl) percentageEl.classList.remove('pulse-animation');
                    alert("Erro no processamento: " + (data.error || "Desconhecido"));
                    localStorage.removeItem('clipmaker_active_project');
                    localStorage.removeItem('clipmaker_active_source_name');
                    const url = new URL(window.location.href);
                    url.searchParams.delete('project');
                    history.replaceState({ page: 'home' }, '', url.pathname);
                    switchView('home');
                    resetUIState();
                } else {
                    if (percentageEl) percentageEl.classList.add('pulse-animation');
                    
                    if (data.status === 'TRANSCRIBING') {
                        updateStepUI(1);
                        if (percentageEl) percentageEl.innerText = "🧠 Extraindo áudio e transcrevendo com IA...";
                        if (progressFill) progressFill.style.width = '35%';
                    } else if (data.status === 'ANALYZING') {
                        updateStepUI(2);
                        if (percentageEl) percentageEl.innerText = "🔍 Detectando momentos virais com Gemini Pro...";
                        if (progressFill) progressFill.style.width = '65%';
                    } else if (data.status === 'RENDERING') {
                        updateStepUI(3);
                        if (percentageEl) percentageEl.innerText = "✂️ Renderizando cortes no formato vertical 9:16...";
                        if (progressFill) progressFill.style.width = '85%';
                    } else {
                        updateStepUI(0);
                        if (percentageEl) {
                            if (percentageEl.innerText === "Na Fila..." || percentageEl.innerText === "0%") {
                                percentageEl.innerText = "15%";
                            } else if (!isNaN(parseInt(percentageEl.innerText)) && parseInt(percentageEl.innerText) < 95) {
                                percentageEl.innerText = parseInt(percentageEl.innerText) + 5 + "%";
                            }
                        }
                        if (progressFill) progressFill.style.width = '20%';
                    }
                }
            } catch (err) {
                console.error(err);
                consecutiveFailures++;
                if (consecutiveFailures >= 5) {
                    stopPolling();
                    if (percentageEl) percentageEl.classList.remove('pulse-animation');
                    alert("Conexão instável com o servidor. O vídeo continua processando em segundo plano.");
                }
            }
        };

        await checkStatus();
        if (pollingInterval === null && isProcessing) {
            pollingInterval = setInterval(checkStatus, 3000);
        }
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
            const res = await fetch(`${API_BASE}/projects/${projectId}/status?_t=${Date.now()}`, {
                headers: { "Authorization": `Bearer ${authToken}` }
            });

            if (!res.ok) {
                if (res.status === 401) {
                    authToken = null;
                    localStorage.removeItem('clipmaker_token');
                    updateNav();
                    alert("Sua sessão expirou. Faça login novamente.");
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

                UI.renderClips(data.clips || []);
                resetUIState();
                return true;
            } else if (data.status === 'FAILED') {
                stopPolling();
                alert("Erro no processamento do vídeo: " + (data.error || "Desconhecido"));
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
    window.addEventListener('popstate', (e) => {
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
