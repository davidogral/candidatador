# Uso responsável

O candidatador existe para **poupar o seu tempo**, não para fazer spam de candidaturas.
Recrutadores percebem candidaturas em massa sem aderência — e isso prejudica você.

## Recomendações

- Use `min_score` e `apply-batch --min-score` para candidatar-se só ao que faz sentido.
- Mantenha o modo `review` enquanto não confiar nas respostas geradas.
- Mantenha `max_per_day` e `delay_seconds` razoáveis.
- Revise respostas marcadas como incertas pela IA — elas nunca devem conter informação falsa.

## Termos de uso dos sites

| Fonte | Método | Observação |
|---|---|---|
| Gupy | endpoint JSON do portal público | uso pessoal, baixo volume |
| Remotive | API pública | pede atribuição; não republicar vagas |
| Greenhouse / Lever / Ashby | APIs públicas de job boards | feitas para serem consumidas |
| LinkedIn / Indeed / Glassdoor | scraping via JobSpy | **os termos proíbem coleta automatizada**; risco de bloqueio da conta/IP. Desativado por padrão |

Automatizar o envio de formulários pode violar os termos de alguns sites. **A responsabilidade
pelo uso é de quem executa a ferramenta.** Na dúvida, use `--dry-run` e envie manualmente.

## O que o projeto não aceita

- Burlar captchas ou mecanismos anti-bot
- Criar contas falsas ou automatizar login com credenciais de terceiros
- Gerar informações falsas em currículos ou respostas
