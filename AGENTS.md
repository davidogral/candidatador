# Guia para agentes de IA e contribuidores

Contexto rápido para quem (pessoa ou agente de código) vai mexer neste repositório.

- Python 3.11+, gerenciado com `uv`. Código em `src/candidatador`, testes em `tests/`.
- Antes de concluir qualquer mudança: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.
- Testes nunca acessam a internet: use `respx` para HTTP e clientes falsos para a IA.
- Identificadores e comentários em inglês; mensagens de CLI e docs em pt-BR.
- Fontes novas: `docs/nova-fonte.md`. Aplicadores novos: `docs/novo-aplicador.md`.
- Invariantes que não podem quebrar:
  - Nenhum aplicador envia candidatura fora de `submit()`; o modo `review` exige confirmação.
  - E-mail e telefone não entram em prompts de IA (`llm._profile_block`).
  - Backends de IA via CLI nunca recebem ferramentas (`claude --tools ""`); se um backend não puder
    ser isolado, marque `untrusted_tools = True` para que as respostas passem por revisão humana.
  - Uma fonte com erro não interrompe a busca (`pipeline.run_search`).
  - Datas são sempre timezone-aware (`sources.base.parse_datetime`).
- A interface (`web/`) é só uma camada sobre `service.py`/`pipeline.py`; regra de negócio fica fora dela.
  Todo texto vindo de vagas é escapado (`esc()`) no front-end; mutações exigem o cabeçalho `X-Candidatador`.
- Nunca versionar dados pessoais (`profile.yaml`, `vault/`, `*.db`).
