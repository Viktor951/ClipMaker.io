# Regras Permanentes de Trabalho para Agentes de IA (AGENTS.md)
**Repositório:** `ClipMakerAI`
**Aplicação:** Obrigatório para qualquer agente de IA, desenvolvedor ou subagente trabalhando neste repositório.

---

### 1. Pacote de Revisão Obrigatório
Ao concluir QUALQUER tarefa que altere código, arquivos de configuração, migrações SQL, Dockerfile ou docker-compose, execute obrigatoriamente:
```bash
python scripts/revisao/gerar_pacote.py --descricao "<resumo detalhado da tarefa e do que foi feito>" --testes
```
Informe sempre ao usuário os caminhos exatos dos arquivos gerados em `revisao_saida/` (`.md` e `.patch`).

---

### 2. Critério de Conclusão de Tarefa
Uma tarefa **SÓ CONTA COMO CONCLUÍDA** após:
1. O pacote de revisão ter sido gerado com sucesso em `revisao_saida/`.
2. O patch ter sido validado automaticamente pelo script com aplicação limpa (`git apply`).
3. O `pytest` ter sido executado, exibindo o resumo completo (total, aprovados, falhas e versão do Python).

---

### 3. Evidência Obrigatória para Afirmações
- **NUNCA** escreva "testado", "verificado" ou "funciona" sem colar a saída real do comando executado, trecho de log ou captura de tela correspondente.
- Toda afirmação de sucesso ou diagnóstico deve conter evidência rastreável.

---

### 4. Proteção Absoluta contra Vazamento de Segredos
- **NUNCA** imprima, copie ou versione valores reais de segredos, senhas, chaves de API (`AIza...`, `sk-...`, `AQ....`), tokens JWT (`eyJ...`) ou hashes.
- **NUNCA** imprima o conteúdo de arquivos `.env*`.
- Não versione arquivos de credenciais (`*.pem`, `*.key`, `*.pfx`, etc.).

---

### 5. Transparência no Relato da IA
Registre explicitamente no bloco **"Relato da IA"** do pacote de revisão:
- O que foi feito (apontando arquivo e função alterados);
- O que **NÃO** foi feito;
- O que **NÃO foi testado** e a justificativa técnica;
- Qualquer dúvida, limitação ou risco associado.

---

### 6. Integridade do Git
- **PROIBIDO** usar `git push --force`, `git reset --hard`, `git rebase` ou comandos que reescrevam o histórico.
- **UM commit por assunto/fase**, utilizando o padrão de Conventional Commits em português: `tipo(escopo): descrição`.
