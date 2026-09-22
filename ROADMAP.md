# Roadmap

Prioridades são discutidas nas [issues](https://github.com/davidogral/candidatador/issues)
e no [Discussions](https://github.com/davidogral/candidatador/discussions). Quer pegar algum item?
Comente na issue correspondente.

## v0.2 — Mais fontes no Brasil 🇧🇷
- [ ] Fontes: Catho, InfoJobs, Vagas.com.br, Solides (Jobs), Trampos, Programathor, GeekHunter
- [ ] Aplicador **Gupy** (requer login; usar perfil persistente do navegador)
- [ ] Aplicadores Ashby e Workable
- [ ] Busca agendada (`candidatador watch`) com notificação de vagas novas acima de X pontos

## v0.3 — Interface web local
- [ ] `candidatador ui`: painel local (FastAPI + front leve) para revisar vagas, arrastar para
      "quero aplicar" e acompanhar o funil (aplicado → entrevista → proposta)
- [ ] Upload de documentos pela interface
- [ ] Kanban de candidaturas com status atualizáveis e lembretes de follow-up

## v0.4 — Inteligência
- [ ] Parser de currículo → preenche `profile.yaml` automaticamente
- [ ] Gerar versão do currículo adaptada à vaga (sem inventar experiência)
- [ ] Provedores de IA plugáveis (modelos locais via Ollama, etc.)
- [ ] Aprendizado com feedback: "gostei/não gostei" ajusta a pontuação

## Contínuo
- [ ] i18n da CLI (pt-BR, en, es)
- [ ] Mais aplicadores: Workday, SmartRecruiters, iCIMS, LinkedIn Easy Apply (opt-in, com avisos)
- [ ] Empacotamento: PyPI, Homebrew, instalador Windows
- [ ] Testes de contrato semanais contra os sites reais (workflow agendado) para detectar quebras
