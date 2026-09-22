<div align="center">

# 🎯 Candidatador

**Seu assistente open source de candidaturas.**
Guarde seus currículos e certificados, encontre vagas em vários sites de uma vez
e deixe o candidatador preencher (e, se você quiser, enviar) as candidaturas por você.

[![CI](https://github.com/davidogral/candidatador/actions/workflows/ci.yml/badge.svg)](https://github.com/davidogral/candidatador/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/licença-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![PRs welcome](https://img.shields.io/badge/PRs-bem--vindos-brightgreen.svg)](CONTRIBUTING.md)

[English](README.en.md) · [Documentação](docs/) · [Roadmap](ROADMAP.md) · [Como contribuir](CONTRIBUTING.md)

</div>

---

## Por que existe?

Procurar emprego é repetitivo: os mesmos dados digitados em dezenas de formulários, vagas
espalhadas por Gupy, LinkedIn, Indeed, páginas de carreira... O **candidatador** junta tudo
isso em uma ferramenta **local, gratuita e aberta**:

| | |
|---|---|
| 📁 **Cofre de documentos** | Várias versões de currículo (por idioma, área, senioridade), cartas, certificados, cursos e diplomas. |
| 🔎 **Busca em várias fontes** | Gupy, Remotive, Greenhouse, Lever, Ashby e — opcionalmente — LinkedIn, Indeed, Glassdoor e Google Jobs. |
| 🎛️ **Filtros do seu perfil** | Cargos, habilidades, senioridade, remoto/local, palavras proibidas, empresas excluídas, data de publicação. |
| 📊 **Pontuação explicável** | Cada vaga recebe uma nota de 0 a 100 com os motivos. Com IA (opcional), a análise fica mais profunda. |
| 🤖 **Candidatura automática** | Abre o formulário, anexa o currículo certo, preenche seus dados e responde perguntas. Você revisa e confirma. |
| 🗂️ **Histórico** | Tudo que foi enviado (inclusive as respostas) fica registrado para você acompanhar. |
| 🔒 **Privacidade** | Seus dados ficam **só na sua máquina**. Nada de servidor, conta ou telemetria. |

## Instalação

Requer Python 3.11+. Recomendamos [uv](https://docs.astral.sh/uv/) ou [pipx](https://pipx.pypa.io):

```bash
# direto do GitHub (o pacote no PyPI chega na primeira release)
uv tool install "candidatador[all] @ git+https://github.com/davidogral/candidatador"
uvx playwright install chromium         # navegador usado para preencher formulários
```

Extras disponíveis: `ai` (Claude), `apply` (Playwright), `jobspy` (LinkedIn/Indeed/Glassdoor),
`all` (tudo). Sem extras você já tem busca, filtros, pontuação e cofre de documentos.

Para desenvolver:

```bash
git clone https://github.com/davidogral/candidatador.git
cd candidatador
uv sync --all-extras
uv run candidatador --help
```

## Início rápido

```bash
# 1. cria a pasta de dados local (profile.yaml + config.yaml)
candidatador init

# 2. preencha seu perfil: dados pessoais, habilidades, cargos desejados, respostas padrão
candidatador profile edit

# 3. suba seus documentos
candidatador docs add curriculo-backend.pdf --kind resume --tags python,backend --default
candidatador docs add resume-en.pdf        --kind resume --lang en --tags python,english
candidatador docs add aws-cert.pdf         --kind certificate --issued-by "AWS" --issued-at 2025-03
candidatador docs list

# 4. busque vagas em todas as fontes ativas
candidatador search -k python -k "backend" --remote --days 7

# 5. veja, selecione e candidate-se
candidatador show greenhouse:gitlab-8773006002
candidatador mark greenhouse:gitlab-8773006002 shortlisted
candidatador apply greenhouse:gitlab-8773006002            # preenche e pede sua confirmação
candidatador apply-batch --min-score 70 --max 5            # várias em sequência

# 6. acompanhe
candidatador applications
```

## Fontes de vagas

| Fonte | Região | Como funciona | Status |
|---|---|---|---|
| **Gupy** | 🇧🇷 | Portal público de vagas | ✅ busca |
| **Remotive** | 🌎 remoto | API pública | ✅ busca |
| **Greenhouse** | 🌎 | API pública por empresa (`boards`) | ✅ busca · ✅ candidatura |
| **Lever** | 🌎 | API pública por empresa (`companies`) | ✅ busca · ✅ candidatura |
| **Ashby** | 🌎 | API pública por empresa (`organizations`) | ✅ busca |
| **LinkedIn, Indeed, Glassdoor, Google Jobs** | 🌎 🇧🇷 | via [JobSpy](https://github.com/speedyapply/JobSpy) (scraping) — opt-in | ⚠️ busca |
| Catho, InfoJobs, Vagas.com, Solides, Workday... | 🇧🇷 🌎 | — | 🗺️ [roadmap](ROADMAP.md) — contribuições bem-vindas! |

Quer outra fonte? Veja [docs/nova-fonte.md](docs/nova-fonte.md): uma fonte nova é **uma
classe com um método**, e pode até ser publicada como plugin separado.

## Como a candidatura automática funciona

```
vaga ──► escolhe o aplicador (Greenhouse, Lever, ...) ──► abre o navegador
     ──► anexa o currículo mais adequado à vaga
     ──► preenche: perfil → respostas padrão → IA (opcional) → pergunta para você
     ──► modo review (padrão): você confere no navegador e confirma o envio
         modo auto: envia sozinho, mas PARA se houver captcha ou resposta incerta
     ──► registra tudo no histórico
```

Salvaguardas embutidas: modo `review` por padrão, limite diário (`max_per_day`), intervalo
entre envios (`delay_seconds`), `--dry-run` para preencher sem enviar e registro de cada
resposta enviada. Leia [docs/uso-responsavel.md](docs/uso-responsavel.md).

## IA (opcional)

Com `pip install "candidatador[ai]"` e a variável `ANTHROPIC_API_KEY`, o candidatador usa o
Claude para:

- analisar a compatibilidade da vaga com seu perfil e **escolher a melhor versão do currículo**;
- responder perguntas abertas dos formulários **usando apenas fatos do seu perfil**
  (respostas incertas são marcadas para revisão);
- gerar cartas de apresentação específicas para cada vaga (`--cover-letter`).

Ative com `--ai` nos comandos ou `matching.use_ai: true` no `config.yaml`. Seu e-mail e
telefone nunca são enviados para a IA.

## Arquitetura em 30 segundos

```
src/candidatador/
├── cli.py            # comandos (Typer)
├── config.py         # profile.yaml + config.yaml
├── models.py, db.py  # SQLite local (documentos, vagas, candidaturas)
├── documents/        # cofre: cópia, hash, extração de texto (PDF/DOCX/TXT)
├── sources/          # 🔌 fontes de vagas (plugins)
├── matching/         # filtros + pontuação explicável
├── llm/              # recursos de IA (opcionais)
├── apply/            # 🔌 aplicadores via navegador (plugins)
└── pipeline.py       # busca → filtra → deduplica → pontua → salva
```

Detalhes em [docs/arquitetura.md](docs/arquitetura.md).

## Contribuindo

Este projeto é feito pela comunidade — cada fonte de vagas e cada aplicador novo ajuda
milhares de pessoas. Comece por [CONTRIBUTING.md](CONTRIBUTING.md) e pelas issues marcadas
com [`good first issue`](https://github.com/davidogral/candidatador/labels/good%20first%20issue).

## Aviso

O candidatador é uma ferramenta pessoal. Você é responsável pelo uso que faz dela e por
respeitar os termos de uso de cada site. Os mantenedores não têm vínculo com Gupy,
LinkedIn, Indeed, Greenhouse, Lever, Ashby ou qualquer outra plataforma citada.

## Licença

[MIT](LICENSE)
