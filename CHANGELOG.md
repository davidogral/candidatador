# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
[Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

## [0.1.0] - 2026-09-22

### Adicionado
- CLI `candidatador` com `init`, `profile`, `docs`, `sources`, `search`, `jobs`, `show`,
  `mark`, `apply`, `apply-batch` e `applications`.
- Cofre local de documentos com versões de currículo, cartas, certificados e cursos, com
  extração de texto de PDF/DOCX/TXT.
- Fontes: Gupy, Remotive, Greenhouse, Lever, Ashby e JobSpy (LinkedIn/Indeed/Glassdoor/Google, opt-in).
- Filtros por perfil, deduplicação entre fontes e pontuação explicável (0–100).
- Aplicadores Greenhouse e Lever via Playwright, com modo `review`, modo `auto`, `--dry-run`,
  limite diário e intervalo entre envios.
- Recursos de IA opcionais com Claude: avaliação de vagas, escolha de currículo, respostas de
  formulário e carta de apresentação.
- Sistema de plugins via entry points (`candidatador.sources`, `candidatador.appliers`).
