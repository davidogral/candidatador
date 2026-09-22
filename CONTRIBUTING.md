# Como contribuir

Obrigado por querer ajudar! 💜 O candidatador só cobre muitos sites porque a comunidade
contribui com fontes e aplicadores novos.

## Formas de ajudar

- 🐛 **Reportar bugs** — principalmente quando um site muda o formulário e o aplicador quebra.
- 🔌 **Adicionar uma fonte de vagas** — [docs/nova-fonte.md](docs/nova-fonte.md).
- 🤖 **Adicionar um aplicador** (preenchimento automático) — [docs/novo-aplicador.md](docs/novo-aplicador.md).
- 📝 **Documentação e traduções** — README em outros idiomas, i18n da CLI.
- 💡 **Ideias** — abra uma issue de sugestão antes de mudanças grandes.

## Ambiente de desenvolvimento

```bash
git clone https://github.com/<seu-usuario>/candidatador.git
cd candidatador
uv sync --all-extras            # cria .venv com tudo
uv run pre-commit install       # lint/format automáticos antes de cada commit
uv run playwright install chromium   # só se for mexer em aplicadores
```

Rodando as verificações (as mesmas da CI):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

> Dica: use `CANDIDATADOR_HOME=/tmp/cand-dev uv run candidatador ...` para testar sem
> mexer nos seus dados reais.

## Regras do jogo

1. **Testes sem internet.** Toda fonte nova precisa de testes com respostas simuladas
   (usamos [respx](https://lundberg.github.io/respx/)). A CI não acessa sites reais.
2. **Nada de dados pessoais** em testes, fixtures, issues ou prints. Use dados fictícios.
3. **Respeite os termos de uso.** Prefira APIs públicas. Fontes que dependem de scraping
   devem ser opt-in e declarar `terms_note`. Veja [docs/uso-responsavel.md](docs/uso-responsavel.md).
4. **O usuário no controle.** Nenhum aplicador pode enviar candidatura sem passar pelo
   fluxo de revisão/confirmação de `BrowserApplier` (ou equivalente).
5. **Commits** no formato [Conventional Commits](https://www.conventionalcommits.org/pt-br/)
   (`feat: fonte Catho`, `fix(lever): novo seletor do botão`).
6. **PRs pequenos** e focados. Atualize o `CHANGELOG.md` na seção *Não lançado*.

## Idioma

Código, nomes e comentários em **inglês** (facilita contribuições do mundo todo).
Mensagens da CLI e documentação em **português** por enquanto — i18n está no roadmap.

## Código de conduta

Ao participar você concorda com o nosso [Código de Conduta](CODE_OF_CONDUCT.md).
