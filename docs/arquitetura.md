# Arquitetura

```
                ┌────────────── profile.yaml / config.yaml ──────────────┐
                │                                                        │
 candidatador search                                                     │
   │                                                                     ▼
   ├─► sources/*  (Gupy, Remotive, Greenhouse, Lever, Ashby, JobSpy, plugins)
   │        └─► JobPosting (modelo normalizado)
   ├─► matching/filters.py   descarta o que não serve (palavras, remoto, data...)
   ├─► dedupe por fingerprint (título + empresa normalizados)
   ├─► matching/scorer.py    nota 0–100 + motivos      ┐
   ├─► llm (opcional)        nota refinada pela IA     ┘
   └─► SQLite (models.Job)

 candidatador apply <vaga>
   ├─► documents.pick_resume     escolhe a versão do currículo (tags x texto da vaga)
   ├─► apply.find_applier(url)   Greenhouse, Lever, plugins... (ou abre o link manualmente)
   ├─► AnswerProvider            perfil → respostas padrão → IA → pergunta para você
   ├─► BrowserApplier            Playwright: abre, preenche, revisão/confirmação, envia
   └─► SQLite (models.Application) com todas as respostas enviadas
```

## Princípios

1. **Local-first.** Não existe backend. Tudo fica em `CANDIDATADOR_HOME`
   (padrão: pasta de dados do usuário do sistema operacional).
2. **Plugins em vez de forks.** Fontes e aplicadores são descobertos via
   [entry points](https://packaging.python.org/en/latest/specifications/entry-points/):
   `candidatador.sources` e `candidatador.appliers`.
3. **Falha isolada.** Uma fonte fora do ar não derruba a busca; o erro é reportado e o resto continua.
4. **Explicável.** Toda nota tem motivos; toda resposta enviada tem origem registrada
   (`profile`, `answers`, `ai`, `user`).
5. **Humano no controle.** Modo `review` é o padrão; o modo `auto` pausa diante de captcha
   ou respostas incertas.

## Modelos de dados

| Tabela | Para quê |
|---|---|
| `Document` | arquivos do cofre: tipo, versão/título, idioma, tags, texto extraído, padrão |
| `Job` | vaga normalizada + nota, motivos, status (`new`, `shortlisted`, `ignored`, `applied`) |
| `Application` | cada tentativa de candidatura: aplicador, modo, status, respostas, erros |

Enquanto estivermos em `0.x`, o esquema pode mudar; migrações (Alembic) entram antes da `1.0`.
