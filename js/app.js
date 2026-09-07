// Main application logic and orchestrator
document.addEventListener('DOMContentLoaded', () => {

    const API_BASE = 'http://localhost:8000';
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
                updateNav();
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

    if (authForm) {
        authForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = authEmail.value;
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
                    
                    if (!res.ok) throw new Error((await res.json()).detail || "Erro ao entrar");
                    const data = await res.json();
                    authToken = data.access_token;
                    localStorage.setItem('clipmaker_token', authToken);
                    updateNav();
                    authModal.classList.add('hidden');
                } else {
                    const res = await fetch(`${API_BASE}/auth/register`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ email, password, name: email.split('@')[0] })
                    });
                    if (!res.ok) throw new Error((await res.json()).detail || "Erro ao cadastrar");
                    alert("Conta criada com sucesso! Faça login agora.");
                    isLoginMode = true;
                    updateAuthModalUI();
                }
            } catch (err) {
                alert(err.message);
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

    let isProcessing = false;

    async function startProcessingPipeline(fileOrUrl, isFile) {
        if (isProcessing) return; // Previne múltiplos disparos
        
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

        const heroSection = document.getElementById('hero-section');
        const processingSection = document.getElementById('processing-section');
        const resultsSection = document.getElementById('results-section');
        const percentageEl = document.getElementById('processing-percentage');

        heroSection.classList.add('hidden');
        resultsSection.classList.add('hidden');
        processingSection.classList.remove('hidden');

        const updateStepUI = (stepIndex) => {
            ['step-1', 'step-2', 'step-3', 'step-4'].forEach((id, idx) => {
                const el = document.getElementById(id);
                if (!el) return;
                if (idx < stepIndex) {
                    el.className = 'step done'; el.innerHTML = `<i class="fa-solid fa-check"></i> Finalizado`;
                } else if (idx === stepIndex) {
                    el.className = 'step active'; el.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Processando...`;
                } else {
                    el.className = 'step pending'; el.innerHTML = `<i class="fa-solid fa-circle"></i> Pendente`;
                }
            });
        };

        updateStepUI(0);
        percentageEl.innerText = "0%";

        const formData = new FormData();
        let endpoint = "";
        if (isFile) {
            formData.append("file", fileOrUrl);
            endpoint = `${API_BASE}/upload-and-process/`;
            percentageEl.innerText = "Enviando arquivo pesado...";
        } else {
            formData.append("url", fileOrUrl);
            endpoint = `${API_BASE}/upload-url/`;
            percentageEl.innerText = "Baixando vídeo (yt-dlp)...";
        }

        try {
            // Upload Initial Request
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
                // Token expirado ou inválido — forçar re-login
                if (response.status === 401) {
                    authToken = null;
                    localStorage.removeItem('clipmaker_token');
                    updateNav();
                    alert("Sua sessão expirou. Faça login novamente.");
                    authModal.classList.remove('hidden');
                    processingSection.classList.add('hidden');
                    heroSection.classList.remove('hidden');
                    resetUIState();
                    return;
                }
                throw new Error(errDetail);
            }
            
            const data = await response.json();
            
            if (data.status === "processing" && data.project_id) {
                updateStepUI(1);
                percentageEl.innerText = "Na Fila...";
                pollProjectStatus(data.project_id, isFile ? fileOrUrl.name : fileOrUrl);
            } else {
                throw new Error("Resposta inesperada do servidor.");
            }
        } catch (error) {
            alert("Erro: " + error.message);
            processingSection.classList.add('hidden');
            heroSection.classList.remove('hidden');
            resetUIState();
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

    async function pollProjectStatus(projectId, sourceName) {
        const percentageEl = document.getElementById('processing-percentage');
        let consecutiveFailures = 0;
        let pollingInterval = setInterval(async () => {
            try {
                const res = await fetch(`${API_BASE}/project/${projectId}/status`, {
                    headers: { "Authorization": `Bearer ${authToken}` }
                });
                
                if (!res.ok) {
                    if (res.status === 401) {
                        clearInterval(pollingInterval);
                        alert("Sessão expirada durante o processamento. Faça login novamente.");
                        authToken = null;
                        localStorage.removeItem('clipmaker_token');
                        updateNav();
                        authModal.classList.remove('hidden');
                        document.getElementById('processing-section').classList.add('hidden');
                        document.getElementById('hero-section').classList.remove('hidden');
                        resetUIState();
                        return;
                    }
                    throw new Error(`Falha ao checar status (${res.status})`);
                }
                consecutiveFailures = 0; // reset on success
                const data = await res.json();
                
                if (data.status === 'READY') {
                    clearInterval(pollingInterval);
                    percentageEl.classList.remove('pulse-animation');
                    percentageEl.innerText = "100%";
                    document.getElementById('processing-section').classList.add('hidden');
                    document.getElementById('results-section').classList.remove('hidden');
                    document.querySelector('.source-name').innerText = sourceName;
                    UI.renderClips(data.clips);
                    resetUIState();
                } else if (data.status === 'FAILED') {
                    clearInterval(pollingInterval);
                    percentageEl.classList.remove('pulse-animation');
                    alert("Erro no processamento: " + (data.error || "Desconhecido"));
                    document.getElementById('processing-section').classList.add('hidden');
                    document.getElementById('hero-section').classList.remove('hidden');
                    resetUIState();
                } else {
                    // Update UI lightly
                    percentageEl.classList.add('pulse-animation');
                    
                    if (data.status === 'TRANSCRIBING') {
                        percentageEl.innerText = "🧠 Extraindo áudio e transcrevendo com IA...";
                    } else if (data.status === 'ANALYZING') {
                        percentageEl.innerText = "🔍 Procurando os melhores cortes...";
                    } else if (data.status === 'RENDERING') {
                        percentageEl.innerText = "✂️ Renderizando cortes no formato 9:16...";
                    } else {
                        if(percentageEl.innerText === "Na Fila...") percentageEl.innerText = "15%";
                        else if (!isNaN(parseInt(percentageEl.innerText)) && parseInt(percentageEl.innerText) < 95) {
                            percentageEl.innerText = parseInt(percentageEl.innerText) + 5 + "%";
                        }
                    }
                }
            } catch (err) {
                console.error(err);
                consecutiveFailures++;
                if (consecutiveFailures >= 5) {
                    clearInterval(pollingInterval);
                    percentageEl.classList.remove('pulse-animation');
                    alert("Conexão perdida com o servidor. O vídeo pode ainda estar processando.");
                    document.getElementById('processing-section').classList.add('hidden');
                    document.getElementById('hero-section').classList.remove('hidden');
                    resetUIState();
                }
            }
        }, 3000);
    }

    const btnNewVideo = document.getElementById('btn-new-video');
    if (btnNewVideo) {
        btnNewVideo.addEventListener('click', () => {
            document.getElementById('results-section').classList.add('hidden');
            document.getElementById('hero-section').classList.remove('hidden');
            if (videoUrlInput) videoUrlInput.value = '';
            if (fileInput) fileInput.value = '';
        });
    }

    const btnCloseModal = document.getElementById('btn-close-modal');
    const editorModal = document.getElementById('editor-modal');
    if (btnCloseModal) btnCloseModal.addEventListener('click', () => UI.closeEditorModal());
    if (editorModal) editorModal.addEventListener('click', (e) => { if (e.target === editorModal) UI.closeEditorModal(); });
});
