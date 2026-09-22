## O que muda

<!-- Descreva a mudança e o motivo. Referencie a issue: "Closes #123" -->

## Tipo

- [ ] 🐛 Correção
- [ ] 🔌 Nova fonte de vagas
- [ ] 🤖 Novo aplicador / ajuste de formulário
- [ ] ✨ Funcionalidade
- [ ] 📝 Documentação
- [ ] 🧹 Refatoração / manutenção

## Checklist

- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` passam
- [ ] Testes novos não acessam a internet (usam `respx` ou mocks)
- [ ] Nenhum dado pessoal real em código, testes ou prints
- [ ] `CHANGELOG.md` atualizado (seção *Não lançado*)
- [ ] Documentação/README atualizados se necessário
- [ ] Aplicadores: testado com `--dry-run` em vaga real (informe qual) e o envio só ocorre em `submit()`
