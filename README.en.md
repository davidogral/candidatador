# 🎯 Candidatador

**Open source job-application assistant** (the name means "applier" in Portuguese).

- 📁 **Document vault** — multiple resume versions (by language/field/seniority), cover letters, certificates, courses.
- 🔎 **Multi-source search** — Gupy (Brazil), Remotive, Greenhouse, Lever, Ashby and, opt-in, LinkedIn/Indeed/Glassdoor/Google Jobs via JobSpy.
- 🎛️ **Profile-based filters** and an **explainable 0-100 score** for every job.
- 🤖 **Auto-apply** — opens the form, attaches the best resume, fills your data, answers questions (profile → saved answers → optional AI → asks you). Review mode by default; auto mode pauses on captchas or uncertain answers.
- 🔒 **Local-first** — everything stays on your machine. No server, no account, no telemetry.

```bash
uv tool install "candidatador[all] @ git+https://github.com/davidogral/candidatador"
uvx playwright install chromium

candidatador init
candidatador profile edit
candidatador docs add resume.pdf --kind resume --lang en --default
candidatador search -k python --remote --days 7
candidatador apply <job-id>
```

The CLI and docs are currently in Brazilian Portuguese; English i18n is on the [roadmap](ROADMAP.md).
Contributions are very welcome — see [CONTRIBUTING.md](CONTRIBUTING.md). Adding a job source is a
single class with one method ([docs/nova-fonte.md](docs/nova-fonte.md)), and it can be shipped as a
separate plugin package via entry points.

License: MIT.
