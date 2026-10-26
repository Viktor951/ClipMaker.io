import json
import os
import sys
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ACHADOS_PATH = BASE_DIR / "scripts" / "security" / "achados.json"
OUTPUT_MD = BASE_DIR / "docs" / "AUDITORIA_SEGURANCA.md"
OUTPUT_DOCX = BASE_DIR / "docs" / "AUDITORIA_SEGURANCA.docx"

# Helper para colorir células de tabela em python-docx
def set_cell_background(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = parse_xml(f'''
        <w:tcMar {nsdecls("w")}>
            <w:top w:w="{top}" w:type="dxa"/>
            <w:bottom w:w="{bottom}" w:type="dxa"/>
            <w:left w:w="{left}" w:type="dxa"/>
            <w:right w:w="{right}" w:type="dxa"/>
        </w:tcMar>
    ''')
    tcPr.append(tcMar)

SEVERITY_COLORS = {
    "Crítica": "990000",     # Dark Red
    "Alta": "CC3300",        # Orange Red
    "Média": "D97706",       # Amber
    "Baixa": "2563EB",       # Blue
    "Informativa": "4B5563"  # Gray
}

def sanitize_text(text: str) -> str:
    if not text:
        return ""
    t = text.replace("C:\\Users\\João Victor\\Documents\\Antigravity Projects\\ClipMakerAI", "<projeto>")
    t = t.replace("c:\\Users\\João Victor\\Documents\\Antigravity Projects\\ClipMakerAI", "<projeto>")
    t = t.replace("C:/Users/João Victor/Documents/Antigravity Projects/ClipMakerAI", "<projeto>")
    t = t.replace("João Victor", "<auditor_responsavel>")
    return t

def generate_markdown(data):
    meta = data["audit_metadata"]
    findings = data["findings"]
    controls = data["verified_secure_controls"]

    from collections import Counter
    sevs = Counter(f["severity"] for f in findings)
    confs = Counter(f["confidence"] for f in findings)

    md = []
    md.append("# RELATÓRIO DE AUDITORIA DE SEGURANÇA COMPLETA — CLIPMAKER (PRÉ-PRODUÇÃO)")
    md.append("")
    md.append(f"**Data da Auditoria:** {meta['date']}  ")
    md.append(f"**Alvo:** {meta['target']} (v{meta['version']})  ")
    md.append(f"**Ambiente Previsto de Hospedagem:** {meta['hosting_environment']}  ")
    md.append(f"**Veredito de Prontidão:** **{meta['verdict']}**  ")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 1. Veredito de Prontidão e Síntese Executiva")
    md.append("")
    md.append(f"### Veredito: **{meta['verdict']}** para Lançamento Público")
    md.append("")
    md.append("**Justificativa Técnica (5 pontos cardeais):**")
    for j in meta["verdict_justification"]:
        md.append(f"1. {j}")
    md.append("")
    md.append("### Contagem Consolidada de Achados")
    md.append("")
    md.append("| Métrica | Total | Detalhamento |")
    md.append("| :--- | :---: | :--- |")
    md.append(f"| **Total de Achados Identificados** | **{len(findings)}** | 2 Críticas, 11 Altas, 8 Médias, 4 Baixas, 2 Informativas |")
    md.append(f"| **Gravidade Crítica** | **{sevs['Crítica']}** | Bombas de descompressão (DoS de RAM no worker) e cadastro livre ilimitado |")
    md.append(f"| **Gravidade Alta** | **{sevs['Alta']}** | Bypass de rate limit (X-Forwarded-For), SSRF redirect no yt-dlp, -protocol_whitelist FFmpeg, etc. |")
    md.append(f"| **Gravidade Média** | **{sevs['Média']}** | Enumeração de usuários, CORS permissivo, XSS potencial em atributos, Prompt Injection |")
    md.append(f"| **Gravidade Baixa / Info** | **{sevs['Baixa'] + sevs['Informativa']}** | Métricas globais de fila, expiração de URLs assinadas (24h), CRLF potencial |")
    md.append(f"| **Controles Verificados e Seguros** | **{len(controls)}** | SQL Injection 100% mitigado, BOLA/IDOR mitigado, Isolamento por usuário, etc. |")
    md.append("")
    md.append("#### Nível de Confiança das Evidências:")
    md.append(f"- **CONFIRMADO-POR-TESTE:** {confs['CONFIRMADO-POR-TESTE']} achados (explorados e comprovados dinamicamente em ambiente isolado)")
    md.append(f"- **CONFIRMADO-NO-CÓDIGO:** {confs['CONFIRMADO-NO-CÓDIGO']} achados (validados por auditoria estática rigorosa arquivo:linha)")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 2. Resumo Executivo para Gestão (Linguagem Não Técnica)")
    md.append("")
    md.append("O **ClipMakerAI** é uma solução robusta e com excelente fundação em autenticação e isolamento de banco de dados (não possui brechas de SQL Injection nem vazamento direto de vídeos entre usuários). No entanto, como a aplicação realiza processamento intensivo de **vídeos e áudio com IA e GPU**, ela apresenta superfícies de ataque que **podem paralisar a empresa ou gerar custos incontroláveis** se for publicada para a internet aberta sem as correções da Fase A:")
    md.append("")
    md.append("1. **Risco de Paralisação por Vídeo Malicioso (Decompression Bomb):** Um invasor pode enviar um arquivo de vídeo com dimensões artificiais gigantes (ex: 8K ou 16K). Quando a ferramenta tentar rastrear o rosto das pessoas no vídeo, o servidor tentará alocar dezenas de gigabytes de memória de uma só vez, acionando o protetor de memória do Linux que derruba o serviço e derruba os vídeos de todos os outros clientes.")
    md.append("2. **Risco de Conta Gratuita Infinita e Custo Abusivo de IA:** Como o cadastro hoje não exige validação de e-mail nem CAPTCHA, e o limitador de velocidade pode ser enganado com cabeçalhos de rede falsos, um robô pode criar centenas de contas por minuto. Cada conta ganha créditos gratuitos que disparam análises com a inteligência artificial do Google (Gemini) e uso de GPU, estourando sua cota e sua conta bancária em poucas horas.")
    md.append("3. **Risco de Acesso a Redes Internas (SSRF no Download por Link):** Embora links com endereços de rede locais sejam bloqueados inicialmente, o componente de download (yt-dlp) aceita redirecionamentos automáticos. Se alguém colocar um link que redireciona para a máquina interna, o servidor pode vazar dados de credenciais da nuvem da VPS.")
    md.append("4. **Risco Legal e LGPD:** A plataforma não apaga automaticamente os textos transcritos dos vídeos salvos no banco de dados e não possui botão de 'Excluir minha conta'. Isso descumpre a LGPD e pode acarretar multas caso dados pessoais permaneçam no sistema indefinidamente.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 3. Modelo de Ameaças (Threat Model)")
    md.append("")
    md.append("### Ativos Protegidos")
    md.append("- **Contas e Credenciais:** E-mails, senhas (bcrypt), tokens de autenticação JWT.")
    md.append("- **Privacidade de Conteúdo:** Vídeos originais, clipes renderizados, transcrições de áudio com falas confidenciais dos usuários.")
    md.append("- **Recursos Computacionais:** Tempo de GPU NVIDIA / CPU, memória RAM do host, espaço em disco SSD da VPS.")
    md.append("- **Cotas de Terceiros e Finanças:** Chave de API da Google Gemini (faturamento por token), créditos concedidos aos usuários.")
    md.append("- **Infraestrutura Host:** Container runtime Docker, base PostgreSQL, instância Redis, servidor Nginx.")
    md.append("")
    md.append("### Atores de Ameaça")
    md.append("1. **Anônimo da Internet (Bot / Script Kiddie):** Dispara scraping, força bruta em login, criação massiva de contas gratuitas e contorno de rate limits.")
    md.append("2. **Usuário Autenticado Malicioso:** Tenta acessar clipes de outras contas (IDOR), submete bombas de descompressão para exaustão de GPU/RAM, injeta comandos em filtros de legenda.")
    md.append("3. **Usuário Vítima:** Tem seus links interceptados ou sofre ataques de XSS se acessar conteúdos compartilhados manipulados.")
    md.append("4. **Conteúdo Não Confiável (Vídeo/Áudio Externo):** Vídeos com áudio hostil instruindo o modelo Gemini (Prompt Injection) ou playlists HLS/M3U8 contatando canais internos.")
    md.append("")
    md.append("### Fronteiras de Confiança e Fluxo")
    md.append("```")
    md.append("Internet -> [Cloudflare Edge / WAF]")
    md.append("           |")
    md.append("           v")
    md.append("      [Nginx (Port 80/443)] -> Proxy reverso e entrega estática")
    md.append("           |")
    md.append("           v")
    md.append("      [FastAPI (Port 8000)] -> Autenticação JWT, DB queries, enfileiramento")
    md.append("           |")
    md.append("           +---> [Redis (6379)] -> Fila de tarefas Huey (AOF)")
    md.append("           +---> [PostgreSQL (5432)] -> Dados relacionais")
    md.append("           |")
    md.append("           v")
    md.append("      [Worker Process] -> yt-dlp, FFmpeg, Whisper, Gemini API (Egress)")
    md.append("```")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 4. Achados Detalhados da Auditoria (Ordenados por Severidade)")
    md.append("")

    for f in findings:
        md.append(f"### [{f['id']}] {f['title']}")
        md.append("")
        md.append(f"- **Severidade:** **{f['severity']}**  ")
        md.append(f"- **Nível de Confiança:** `{f['confidence']}`  ")
        md.append(f"- **Status:** `{f['status']}`  ")
        md.append(f"- **Mapeamento:** `{f['owasp']}` | `{f['cwe']}`  ")
        md.append(f"- **Localização:** `{sanitize_text(f['location'])}`  ")
        md.append(f"- **Esforço de Correção:** {f['effort']} ({f['phase']})  ")
        md.append("")
        md.append(f"**Descrição Técnica:**  \n{sanitize_text(f['description'])}")
        md.append("")
        md.append(f"**Evidência / Passos de Reprodução:**  \n{sanitize_text(f['evidence'])}")
        md.append("")
        md.append(f"**Impacto:**  \n{sanitize_text(f['impact'])}")
        md.append("")
        md.append(f"**Remediação Recomendada:**  \n{sanitize_text(f['remediation'])}")
        if f.get("remediation_code"):
            md.append("")
            md.append("```python")
            md.append(sanitize_text(f["remediation_code"]))
            md.append("```")
        md.append("")
        md.append("---")
        md.append("")

    md.append("## 5. Controles Verificados e Seguros (Manter Inalterados)")
    md.append("")
    md.append("Os seguintes controles foram testados, validados e considerados adequados para o padrão de produção. **Não modifique ou remova estes mecanismos:**")
    md.append("")
    for c in controls:
        md.append(f"### [OK] {c['id']}: {c['title']}")
        md.append(f"- **Status:** `{c['status']}`")
        md.append(f"- **Evidência Comprovada:** {sanitize_text(c['evidence'])}")
        md.append("")

    md.append("---")
    md.append("")
    md.append("## 6. Itens Não Testados Dinamicamente e Justificativa")
    md.append("")
    md.append("1. **Teste de Carga Destrutivo (DoS em Massa):** Não foram disparadas dezenas de milhares de requisições simultâneas contra o host para evitar indisponibilidade física ou travamento do ambiente operacional de desenvolvimento.")
    md.append("2. **Varredura Ativa contra Endpoints Externos do Google (Gemini API) ou YouTube:** Conforme as regras mandatórias da auditoria, nenhuma requisição foi enviada a provedores de nuvem ou APIs públicas de terceiros para não gerar custos ou violações de termos.")
    md.append("3. **Exploração de Corrupção de Memória em Bibliotecas Nativas (libass/OpenCV):** Não foram injetados binários com fuzzing agressivo para corrupção de ponteiros em baixo nível na libass ou ffmpeg, preservando a estabilidade da máquina.")
    md.append("4. **Alta Disponibilidade Distribuída (Multi-Node HA):** O ambiente do projeto foi concebido para uma única VPS Linux; testes de partição de rede entre múltiplos nós não se aplicam à arquitetura atual.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 7. Plano de Remediação em 3 Fases")
    md.append("")
    md.append("### FASE A: BLOQUEADORES CRÍTICOS (Antes de Liberar para Usuários Externos)")
    md.append("*Meta: Proteger o servidor contra colapso de recursos, invasão de rate limit e abusos orçamentários.*")
    md.append("")
    md.append("1. **[S3.4] Validação Rígida de Resolução de Vídeo:** Adicionar checagem de largura e altura máximas (máx. 1920x1080 ou 3840x2160) no upload antes de invocar cv2.VideoCapture.")
    md.append("2. **[S6.1] Correção de Headers de Proxy e Rate Limiter:** Ajustar o Nginx para usar `$remote_addr` (ou `$http_cf_connecting_ip` com Cloudflare) e limitar `--forwarded-allow-ips` no Uvicorn.")
    md.append("3. **[S8.1] Proteção Anti-Bot no Cadastro:** Implementar Cloudflare Turnstile no front e validação de token no POST /register.")
    md.append("4. **[S3.2] Proteção de Protocolo no FFmpeg:** Incluir `-protocol_whitelist \"file,crypto,data\"` em `_ffmpeg_base()` e `get_video_info()`.")
    md.append("5. **[S3.5] Limite de Tamanho no yt-dlp:** Incluir `--max-filesize 500M` e `--no-playlist` nas chamadas do yt-dlp.")
    md.append("6. **[S1.1] Exigência de 'exp' no JWT:** Adicionar `options={\"require\": [\"exp\"]}` no `jwt.decode`.")
    md.append("7. **[S5.5] Configuração de CSP no Nginx:** Adicionar cabeçalho `Content-Security-Policy` bloqueando scripts e conexões não autorizadas.")
    md.append("8. **[S5.2] Escapamento de Atributos no Frontend:** Aplicar `escapeHtml()` nas propriedades `videoUrl` e `thumbnailUrl` no HTML.")
    md.append("9. **[S6.2] Remoção de 'null' no CORS:** Remover a origem `'null'` da lista de origens em ambiente de produção.")
    md.append("")
    md.append("### FASE B: PRÉ-MONETIZAÇÃO (Antes do Primeiro Cliente Pagante)")
    md.append("*Meta: Conformidade legal (LGPD), proteção contra enumeração e qualidade de serviço.*")
    md.append("")
    md.append("1. **[S7.6 & S9.1] Limpeza de Banco e Exclusão de Conta (LGPD):** Criar endpoint de exclusão de conta pelo usuário e rotina de expurgo de transcrições e projetos antigos (> 30 dias).")
    md.append("2. **[S1.3] Mitigação de Enumeração de Usuários:** Padronizar mensagens de erro e implementar hash falso em tempo constante no login.")
    md.append("3. **[S5.3] Blindagem de Prompt Injection:** Delimitar transcrições no prompt do Gemini com tags `<transcription>` e truncar títulos da IA.")
    md.append("4. **[S6.3] Hardening de Rotas no Nginx:** Isolar `client_max_body_size` grande apenas na rota de upload e ativar `server_tokens off;`.")
    md.append("5. **[S7.2] Hardening do Redis:** Renomear comandos `CONFIG`, `FLUSHALL` e `FLUSHDB` no redis-server.")
    md.append("6. **[S9.3 & S9.4] Termos de Uso e Canal de Denúncia:** Publicar Termos de Uso com declaração de titularidade de direitos e canal de abuso.")
    md.append("")
    md.append("### FASE C: ENDURECIMENTO CONTÍNUO (Operação e Escala)")
    md.append("*Meta: Resiliência operacional, observabilidade profunda e melhoria de arquitetura.*")
    md.append("")
    md.append("1. **[S8.3] Escalonamento Justo de Fila (Fair-Share):** Fila com balanceamento por tenant para evitar que um usuário monopolize o worker.")
    md.append("2. **[S6.5] Paginação na API:** Implementar paginação com limit/offset na listagem de projetos.")
    md.append("3. **[S8.5] Observabilidade de Segurança:** Middleware de X-Request-ID unificado e alertas para anomalias de 401/429.")
    md.append("4. **[S7.1] Imagens Docker com Digest Imutável:** Atualizar Dockerfile para referenciar SHAs exatos das imagens base.")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 8. Checklist de Go-Live para Hospedagem VPS Linux + Cloudflare Edge")
    md.append("")
    md.append("| Etapa | Item de Verificação | Como Configurar / Validar |")
    md.append("| :--- | :--- | :--- |")
    md.append("| **Borda (Cloudflare)** | SSL/TLS Full (Strict) | Ativar Cloudflare Origin CA Certificate no Nginx da VPS para tráfego 100% criptografado ponta-a-ponta. |")
    md.append("| **Borda (Cloudflare)** | WAF & Bot Fight Mode | Habilitar 'Bot Fight Mode' e regras de WAF para mitigar requisições automatizadas maliciosas. |")
    md.append("| **Borda (Cloudflare)** | Rate Limiting de Borda | Configurar regra no Cloudflare limitando requisições por IP em `/api/auth/*` a 10 req/min. |")
    md.append("| **Host (VPS Linux)** | Firewall UFW Restrito | `ufw default deny incoming`, abrir exclusivamente portas 22 (SSH), 80 (HTTP) e 443 (HTTPS). |")
    md.append("| **Host (VPS Linux)** | Acesso SSH Blindado | Desativar login de root (`PermitRootLogin no`), desativar autenticação por senha (`PasswordAuthentication no`), usar chaves Ed25519. |")
    md.append("| **Host (VPS Linux)** | Fail2ban Ativo | Proteger a porta SSH contra ataques de força bruta com banimento automático. |")
    md.append("| **Host (VPS Linux)** | Atualizações de SO | Configurar `unattended-upgrades` no Ubuntu/Debian para patches de segurança do kernel e pacotes. |")
    md.append("| **Docker Host** | Firewall Egress | Regra de iptables bloqueando pacotes do Docker para redes internas privadas (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.169.254). |")
    md.append("| **Backup** | Backup Cifrado Off-Site | Cron job executando `pg_dump` cifrado com GPG e transferido via rclone para bucket S3 / B2 isolado. |")
    md.append("| **Backup** | Teste de Restauração | Validar mensalmente a restauração de um dump em container descartável para comprovar RTO/RPO. |")
    md.append("| **Resposta a Incidentes** | Plano de Vazamento | Procedimento documentado: isolamento da máquina, revogação imediata de SECRET_KEY e GEMINI_API_KEY, notificação da ANPD em até 3 dias úteis. |")
    md.append("")
    md.append("---")
    md.append("")
    md.append("## 9. Apêndices e Limitações da Auditoria")
    md.append("")
    md.append("### Ferramentas e Scripts Utilizados")
    md.append("- `scripts/security/audit_git_secrets.py`: Scanner de histórico completo do repositório (`git log -p --all`) com mascaramento obrigatório de segredos.")
    md.append("- `scripts/security/canary_server.py`: Servidor HTTP canário local para auditoria de conexões de SSRF e protocolos FFmpeg.")
    md.append("- `scripts/security/test_s1_jwt.py`: Testes dinâmicos de validação de algoritmos, assinaturas e expiração de tokens JWT.")
    md.append("- `scripts/security/test_s3_ffmpeg_concat.py`: Teste de restrição de protocolos com `-protocol_whitelist` no FFmpeg.")
    md.append("- `scripts/security/test_s4_ssrf.py`: Suíte de 20 vetores de injeção de URL para validação de escape Anti-SSRF.")
    md.append("- `scripts/security/test_s6_rate_limit_spoof.py`: Validação de extração de IP e contorno do SlowAPI via `X-Forwarded-For`.")
    md.append("")
    md.append("### Ressalva Legal e Técnica")
    md.append("> [!IMPORTANT]")
    md.append("> Esta auditoria foi conduzida em ambiente local isolado e representa uma revisão detalhada do código-fonte, arquitetura e configurações do projeto. Uma auditoria de segurança pré-produção **não substitui** um Teste de Intrusão (Penetration Test) profissional realizado por especialistas humanos independentes contra a infraestrutura em produção antes de processar transações financeiras ou armazenar dados sensíveis de alta criticidade.")
    md.append("")

    return "\n".join(md)

def generate_docx(data):
    doc = docx.Document()

    # Configuração de Margens (2.0 cm)
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    meta = data["audit_metadata"]
    findings = data["findings"]
    controls = data["verified_secure_controls"]

    from collections import Counter
    sevs = Counter(f["severity"] for f in findings)
    confs = Counter(f["confidence"] for f in findings)

    # Título do Documento
    title = doc.add_paragraph()
    title_run = title.add_run("RELATÓRIO DE AUDITORIA DE SEGURANÇA COMPLETA\nCLIPMAKER (PRÉ-PRODUÇÃO)")
    title_run.font.name = "Calibri"
    title_run.font.size = Pt(22)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(15, 23, 42)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    sub = doc.add_paragraph()
    sub_run = sub.add_run("Avaliação de Vulnerabilidades, Modelo de Ameaças e Plano de Remediação")
    sub_run.font.size = Pt(13)
    sub_run.font.italic = True
    sub_run.font.color.rgb = RGBColor(71, 85, 105)
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph().paragraph_format.space_after = Pt(12)

    # Box de Veredito
    tbl_v = doc.add_table(rows=1, cols=1)
    tbl_v.alignment = WD_TABLE_ALIGNMENT.CENTER
    c_v = tbl_v.rows[0].cells[0]
    set_cell_background(c_v, "FEF2F2")
    set_cell_margins(c_v, 200, 200, 300, 300)
    
    pv = c_v.paragraphs[0]
    rv1 = pv.add_run("VEREDITO DE PRONTIDÃO: ")
    rv1.font.bold = True
    rv1.font.size = Pt(12)
    rv2 = pv.add_run(f"{meta['verdict']} PARA RECEBER CLIENTES EXTERNOS\n")
    rv2.font.bold = True
    rv2.font.size = Pt(14)
    rv2.font.color.rgb = RGBColor(185, 28, 28)

    rv3 = pv.add_run(
        "A aplicação exibe excelente maturidade em isolamento de banco de dados e prevenção a SQL Injection, "
        "mas apresenta 2 vulnerabilidades Críticas e 11 de Severidade Alta que permitem negação de serviço (DoS) via vídeos "
        "com dimensões arbitrárias, contorno integral do rate limit por falsificação de IP e esgotamento orçamentário por bots de cadastro. "
        "O lançamento público deve ser condicionado à implementação das mitigações da Fase A."
    )
    rv3.font.size = Pt(10.5)

    doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # 1. Resumo Executivo
    h1 = doc.add_heading("1. Resumo Executivo para Gestão", level=1)
    h1.paragraph_format.space_before = Pt(16)
    
    p = doc.add_paragraph(
        "O ClipMakerAI está em fase avançada de preparação para lançamento. Esta auditoria técnica e defensiva identificou "
        "que o núcleo de autorização entre contas e proteção a injeções de SQL é sólido. Contudo, devido à natureza pesada de processamento "
        "de arquivos multimídia (FFmpeg, OpenCV, Whisper e chamadas ao LLM Gemini), foram identificadas brechas de esgotamento de recursos "
        "que precisam de contenção imediata antes da abertura pública."
    )
    p.paragraph_format.space_after = Pt(8)

    # Tabela Resumo de Métricas
    tbl_stats = doc.add_table(rows=6, cols=3)
    tbl_stats.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_stats.style = "Table Grid"

    headers = ["Gravidade / Métrica", "Quantidade", "Status & Nível de Confiança"]
    for i, h in enumerate(headers):
        cell = tbl_stats.rows[0].cells[i]
        set_cell_background(cell, "0F172A")
        pr = cell.paragraphs[0].add_run(h)
        pr.font.bold = True
        pr.font.color.rgb = RGBColor(255, 255, 255)
        pr.font.size = Pt(10)

    rows_data = [
        ("Crítica", f"{sevs['Crítica']}", "2 Confirmados no Código (Bomba de RAM e Cadastro livre)"),
        ("Alta", f"{sevs['Alta']}", "4 Confirmados por Teste / 7 Confirmados no Código"),
        ("Média", f"{sevs['Média']}", "2 Confirmados por Teste / 6 Confirmados no Código"),
        ("Baixa / Informativa", f"{sevs['Baixa'] + sevs['Informativa']}", "Métricas de fila, expiração de tokens e logs"),
        ("Controles Verificados e Seguros", f"{len(controls)}", "10 Controles Auditados e Estáveis (Sem brechas)")
    ]

    for idx, (g, q, st) in enumerate(rows_data, 1):
        row = tbl_stats.rows[idx]
        row.cells[0].paragraphs[0].add_run(g).font.bold = True
        row.cells[1].paragraphs[0].add_run(q).font.bold = True
        row.cells[2].paragraphs[0].add_run(st)
        for c in row.cells:
            set_cell_margins(c, 80, 80, 100, 100)

    doc.add_paragraph().paragraph_format.space_after = Pt(16)

    # 2. Modelo de Ameaças
    h2 = doc.add_heading("2. Modelo de Ameaças (Threat Model)", level=1)
    h2.paragraph_format.space_before = Pt(16)

    p_tm = doc.add_paragraph(
        "A arquitetura do sistema foi mapeada identificando os limites de confiança entre tráfego da internet, "
        "proxy reverso (Nginx), API assíncrona (FastAPI), fila persistente (Redis/Huey), banco de dados (PostgreSQL) "
        "e os workers com suporte a hardware (GPU NVIDIA/FFmpeg/Whisper). O conteúdo de mídia enviado por usuários desconhecidos "
        "e URLs públicas foi tratado formalmente como ENTRADA HOSTIL E NÃO CONFIÁVEL."
    )
    p_tm.paragraph_format.space_after = Pt(12)

    # 3. Achados Detalhados
    h3 = doc.add_heading("3. Achados Detalhados da Auditoria", level=1)
    h3.paragraph_format.space_before = Pt(16)

    for f in findings:
        # Tabela individual para cada achado
        tbl_f = doc.add_table(rows=7, cols=2)
        tbl_f.alignment = WD_TABLE_ALIGNMENT.CENTER
        tbl_f.style = "Table Grid"

        # Colunas com larguras fixas (2.0 polegadas e 4.8 polegadas)
        tbl_f.columns[0].width = Inches(1.8)
        tbl_f.columns[1].width = Inches(5.0)

        # Cabeçalho do Card do Achado
        top_cell = tbl_f.rows[0].cells[1]
        sev_color = SEVERITY_COLORS.get(f["severity"], "4B5563")
        set_cell_background(tbl_f.rows[0].cells[0], sev_color)
        set_cell_background(top_cell, "F8FAFC")

        r_id = tbl_f.rows[0].cells[0].paragraphs[0].add_run(f"[{f['id']}]\n{f['severity'].upper()}")
        r_id.font.bold = True
        r_id.font.size = Pt(10)
        r_id.font.color.rgb = RGBColor(255, 255, 255)

        r_title = top_cell.paragraphs[0].add_run(f"{f['title']}")
        r_title.font.bold = True
        r_title.font.size = Pt(11)

        fields = [
            ("Classificação", f"{f['owasp']} | {f['cwe']}"),
            ("Confiança & Local", f"Confiança: {f['confidence']} | {sanitize_text(f['location'])}"),
            ("Descrição Técnica", sanitize_text(f['description'])),
            ("Evidência / Teste", sanitize_text(f['evidence'])),
            ("Impacto", sanitize_text(f['impact'])),
            ("Correção Recomendada", f"{sanitize_text(f['remediation'])}\n\nEsforço: {f['effort']} | Alocação: {f['phase']}")
        ]

        for i, (label, val) in enumerate(fields, 1):
            cell_lbl = tbl_f.rows[i].cells[0]
            cell_val = tbl_f.rows[i].cells[1]
            set_cell_background(cell_lbl, "F1F5F9")
            rl = cell_lbl.paragraphs[0].add_run(label)
            rl.font.bold = True
            rl.font.size = Pt(9.5)
            rv = cell_val.paragraphs[0].add_run(val)
            rv.font.size = Pt(9.5)
            for c in (cell_lbl, cell_val):
                set_cell_margins(c, 70, 70, 100, 100)

        doc.add_paragraph().paragraph_format.space_after = Pt(10)

    # 4. Controles Verificados e Seguros
    h4 = doc.add_heading("4. Controles Auditados e Verificados como SEGUROS", level=1)
    h4.paragraph_format.space_before = Pt(16)

    tbl_c = doc.add_table(rows=len(controls) + 1, cols=3)
    tbl_c.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_c.style = "Table Grid"

    for i, h in enumerate(["ID", "Controle Verificado", "Evidência Comprovada"]):
        cell = tbl_c.rows[0].cells[i]
        set_cell_background(cell, "065F46") # Emerald green
        p_c = cell.paragraphs[0].add_run(h)
        p_c.font.bold = True
        p_c.font.color.rgb = RGBColor(255, 255, 255)
        p_c.font.size = Pt(10)

    for idx, c in enumerate(controls, 1):
        row = tbl_c.rows[idx]
        row.cells[0].paragraphs[0].add_run(c["id"]).font.bold = True
        row.cells[1].paragraphs[0].add_run(c["title"]).font.bold = True
        row.cells[2].paragraphs[0].add_run(sanitize_text(c["evidence"]))
        for cell in row.cells:
            set_cell_margins(cell, 70, 70, 90, 90)

    doc.add_paragraph().paragraph_format.space_after = Pt(14)

    # 5. Plano de Remediação em 3 Fases
    h5 = doc.add_heading("5. Plano de Remediação Priorizado em 3 Fases", level=1)
    h5.paragraph_format.space_before = Pt(16)

    phases = [
        ("FASE A: BLOQUEADORES CRÍTICOS (Antes de Abrir ao Público)", [
            "S3.4: Validar limites de largura e altura de vídeo (máx. 1920x1080) antes do OpenCV.",
            "S6.1: Configurar Nginx com $remote_addr e Uvicorn com --forwarded-allow-ips restrito.",
            "S8.1: Implementar Cloudflare Turnstile no cadastro público para barrar bots.",
            "S3.2: Incluir -protocol_whitelist 'file,crypto,data' no FFmpeg e FFprobe.",
            "S3.5: Adicionar --max-filesize 500M e --no-playlist na invocação do yt-dlp.",
            "S1.1: Exigir a claim 'exp' no decode_access_token (options={'require': ['exp']}).",
            "S5.5: Implementar cabeçalho Content-Security-Policy (CSP) estrito no Nginx.",
            "S5.2: Escapar variáveis videoUrl e thumbnailUrl no HTML do frontend.",
            "S6.2: Remover a origem permissiva 'null' do CORS em produção."
        ]),
        ("FASE B: PRÉ-MONETIZAÇÃO (Antes do Primeiro Cliente Pagante)", [
            "S7.6 & S9.1: Criar rotina de expurgo de dados no banco (LGPD) e endpoint DELETE /me.",
            "S1.3: Eliminar diferencial de tempo no login com verificação em tempo constante.",
            "S5.3: Delimitar transcrições no prompt do Gemini com tags <transcription> rígidas.",
            "S6.3: Configurar client_max_body_size restrito nas rotas não-upload do Nginx.",
            "S7.2: Renomear comandos perigosos do Redis (CONFIG, FLUSHALL).",
            "S9.3 & S9.4: Publicar Termos de Uso com isenção de direitos autorais e canal de denúncia."
        ]),
        ("FASE C: ENDURECIMENTO CONTÍNUO (Operação e Escala)", [
            "S8.3: Implementar fila com algoritmo de justiça entre usuários (Fair-Share).",
            "S6.5: Adicionar paginação (limit/offset) no endpoint GET /api/projects.",
            "S8.5: Unificar cabeçalho X-Request-ID nos logs estruturados para rastreabilidade.",
            "S7.1: Fixar digests criptográficos (@sha256:...) nas imagens base do Dockerfile."
        ])
    ]

    for p_title, items in phases:
        p_ph = doc.add_paragraph()
        run_pt = p_ph.add_run(f"\n{p_title}")
        run_pt.font.bold = True
        run_pt.font.size = Pt(11)
        for it in items:
            p_it = doc.add_paragraph(it, style='List Bullet')
            p_it.paragraph_format.space_after = Pt(3)

    # 6. Checklist de Go-Live
    h6 = doc.add_heading("6. Checklist de Go-Live (VPS Linux + Cloudflare Edge)", level=1)
    h6.paragraph_format.space_before = Pt(16)

    tbl_gl = doc.add_table(rows=12, cols=3)
    tbl_gl.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_gl.style = "Table Grid"

    gl_headers = ["Camada", "Item de Segurança", "Procedimento Obrigatório de Configuração"]
    for i, h in enumerate(gl_headers):
        cell = tbl_gl.rows[0].cells[i]
        set_cell_background(cell, "1E293B")
        pr = cell.paragraphs[0].add_run(h)
        pr.font.bold = True
        pr.font.color.rgb = RGBColor(255, 255, 255)
        pr.font.size = Pt(9.5)

    checklist_items = [
        ("Cloudflare Edge", "SSL/TLS Full (Strict)", "Instalar Cloudflare Origin CA Certificate no Nginx da VPS para garantir TLS fim a fim."),
        ("Cloudflare Edge", "WAF & Bot Fight Mode", "Ativar 'Bot Fight Mode' e regras gerenciadas de proteção contra varreduras."),
        ("Cloudflare Edge", "Rate Limiting de Borda", "Configurar regra de taxa máxima de 10 req/min por IP na rota /api/auth/register."),
        ("VPS Host (Linux)", "Firewall UFW", "Bloquear todas as portas de entrada exceto 22 (SSH), 80 e 443 do Nginx."),
        ("VPS Host (Linux)", "Acesso SSH Endurecido", "Desabilitar login de root (PermitRootLogin no) e exigir autenticação por chaves SSH Ed25519."),
        ("VPS Host (Linux)", "Fail2ban", "Ativar jail para SSH e monitoramento de abusos HTTP na borda."),
        ("VPS Host (Linux)", "Atualizações de SO", "Ativar unattended-upgrades para correções automáticas de vulnerabilidades de kernel."),
        ("Docker Host", "Egress Firewall (Anti-SSRF)", "Iptables bloqueando pacotes dos containers para 169.254.169.254 e sub-redes privadas."),
        ("Banco de Dados", "Rotina de Backup Cifrado", "pg_dump diário criptografado com chave GPG e sincronizado para storage off-site."),
        ("Banco de Dados", "Teste de Restauração", "Validar a restauração completa do banco a cada 30 dias em ambiente descartável."),
        ("Governança", "Plano de Resposta a Incidentes", "Fluxo estabelecido de isolamento de rede, rotação de chaves e notificação da ANPD.")
    ]

    for idx, (c1, c2, c3) in enumerate(checklist_items, 1):
        row = tbl_gl.rows[idx]
        row.cells[0].paragraphs[0].add_run(c1).font.bold = True
        row.cells[1].paragraphs[0].add_run(c2).font.bold = True
        row.cells[2].paragraphs[0].add_run(c3)
        for cell in row.cells:
            set_cell_margins(cell, 60, 60, 80, 80)

    doc.add_paragraph().paragraph_format.space_after = Pt(20)

    # Salva o arquivo .docx
    doc.save(str(OUTPUT_DOCX))
    print(f"[+] Relatório DOCX gerado com sucesso: {OUTPUT_DOCX}")

def main():
    print("[*] Carregando achados estruturados de achados.json...")
    with open(ACHADOS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Gerar Markdown
    print("[*] Gerando docs/AUDITORIA_SEGURANCA.md...")
    md_content = generate_markdown(data)
    OUTPUT_MD.write_text(md_content, encoding="utf-8")
    print(f"[+] Relatório Markdown gerado com sucesso: {OUTPUT_MD}")

    # 2. Gerar DOCX
    print("[*] Gerando docs/AUDITORIA_SEGURANCA.docx via python-docx...")
    generate_docx(data)

if __name__ == "__main__":
    main()
