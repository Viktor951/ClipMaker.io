# Scripts de Auditoria de Segurança — ClipMakerAI

Este diretório contém os scripts automatizados e reprodutíveis desenvolvidos para a auditoria de segurança pré-produção do ClipMakerAI.

## Estrutura de Arquivos

- `achados.json`: Base de dados estruturada de todos os 27 achados, severidades, evidências e remediações concretas.
- `gerar_relatorio.py`: Script gerador dos relatórios oficiais (`docs/AUDITORIA_SEGURANCA.md` e `docs/AUDITORIA_SEGURANCA.docx`).
- `canary_server.py`: Servidor HTTP canário local para auditoria não destrutiva de SSRF e protocolos FFmpeg.
- `audit_git_secrets.py`: Scanner de histórico completo do repositório (`git log -p --all`) com detecção e mascaramento obrigatório de segredos.
- `test_s1_jwt.py`: Testes dinâmicos de integridade de JWT, `alg: none`, tokens expirados e ausência de claim `exp`.
- `test_s2_race_condition.py`: Simulação de condições de corrida em concorrência de jobs.
- `test_s3_ffmpeg_ssrf.py` & `test_s3_ffmpeg_concat.py`: Testes dinâmicos de restrição de protocolo (`-protocol_whitelist`) no FFmpeg.
- `test_s4_ssrf.py`: Suíte de 20 vetores de injeção de URL para validação do `_is_safe_public_url`.
- `test_s6_rate_limit_spoof.py`: Teste dinâmico de contorno de rate limiter através de injeção de `X-Forwarded-For`.

## Como Executar Novamente a Geração do Relatório

```bash
python scripts/security/gerar_relatorio.py
```
