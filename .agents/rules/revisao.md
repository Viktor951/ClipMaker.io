# Regras Permanentes de Trabalho para Agentes de IA
**Origem:** `AGENTS.md`

Ao concluir QUALQUER tarefa que altere código, configuração, migração, Dockerfile ou compose:
1. Execute: `python scripts/revisao/gerar_pacote.py --descricao "<resumo>" --testes`
2. Uma tarefa só conta como concluída com o pacote gerado e o pytest executado (mostrando o resumo).
3. Nunca escreva "testado" ou "funciona" sem colar a saída do comando ou a evidência.
4. Nunca coloque segredos em código, logs, relatórios ou pacotes; não imprima .env.
5. Registre no "Relato da IA" tudo que foi pulado, adiado ou que não foi possível testar.
6. Sem push e sem force; um commit por assunto/fase.
