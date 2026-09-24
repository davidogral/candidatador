# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e
[Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [Não lançado]

### Adicionado
- Filtros na hora da busca, com padrões salvos no perfil (`target.*`) e botão "Salvar como
  padrão": senioridade (ex.: só Júnior, opcionalmente incluindo vagas sem nível no título),
  país — inclusive para vagas remotas ("Worldwide", "LATAM" e "Americas" contam para o Brasil;
  "Remote, United States" não) —, tipo de contrato (CLT/PJ/estágio…), excluir "banco de
  talentos" e título compatível com o cargo (tolerante a "Engenheiro(a)", "Analista Dados Jr").
- A busca informa quantas vagas cada filtro descartou.
- Lista de vagas: filtro de país e "só da última busca".
- Fontes consultadas em paralelo, e as palavras-chave de Gupy e Remotive também.
- Gupy: país sempre no local e tipo de contrato; Lever/Ashby: código do país.
- JobSpy: busca no país escolhido (sem isso o LinkedIn devolve vagas dos EUA), detecta vaga
  remota pelo texto (o filtro de remoto do LinkedIn não tem efeito) e usa o nível informado pelo
  LinkedIn quando o título não diz.
- CLI: `search --seniority/-S`, `--country/-c`, `--title-match`.
- Filtro de senioridade na interface (Estágio/Trainee, Júnior, Pleno, Sênior, Especialista,
  Liderança, Não informada), detectada pelo título da vaga — inclusive "Jr/Pl/Sr" e
  "Analista II/III" — com etiqueta em cada vaga e escolha lembrada no navegador.
- O currículo chega à empresa como `<nome>-<empresa>.pdf`, não com o nome interno do cofre.
- Interface web local (`candidatador ui`): perfil, respostas padrão, documentos, fontes,
  busca, filtros, detalhes da vaga, candidatura com perguntas/confirmação na página,
  registro de candidaturas manuais e histórico.
- IA via CLI: provedores `claude-cli` (Claude Code, usando sua assinatura) e `codex-cli`, além
  da API. `ai.provider: auto` escolhe o primeiro disponível. Falhas da IA não interrompem a busca
  nem a candidatura.
- `service.apply_to_job`: fluxo de candidatura compartilhado entre CLI e interface.

### Alterado
- GitHub Actions atualizadas para Node 24 (checkout 7, upload-artifact 7, download-artifact 8,
  setup-uv 7, codeql-action 4, action-gh-release 3).
- `release.yml`: novo disparo manual que monta o pacote, instala o wheel num ambiente limpo e
  confere a CLI e a interface sem publicar; publicação só em tags `v*`.

### Corrigido
- Nota de habilidades penalizava perfis com muitas habilidades (dividia pelo total da lista) e
  contava variantes como "PowerBI"/"Power BI" em dobro; agora ~6 habilidades encontradas já dão
  a pontuação máxima.
- Escolha do currículo comparava tags como trecho de texto ("bi" casava com "ambiente"); agora
  compara palavras inteiras e dá mais peso ao título da vaga.
- Lista de vagas podia mostrar o resultado de um filtro antigo quando dois filtros eram
  alterados em sequência rápida.
- Busca pela interface travava e dava `database is locked`: a busca segurava a escrita no banco
  durante as chamadas de IA e aceitava buscas simultâneas. Agora roda em segundo plano com
  progresso na página, só grava no final (upsert atômico que preserva o status da vaga), usa
  SQLite em modo WAL, aceita uma busca por vez e a IA analisa até `matching.ai_max_jobs` vagas,
  4 em paralelo (20 vagas: de ~3 min para ~50 s).
- Criação do banco não era segura entre threads (`table already exists`).
- Ctrl+C na interface demorava até 60 s com uma busca em andamento; agora fecha na hora.
- Erro de limite do Claude Code aparecia como JSON ilegível; agora mostra o motivo
  ("You've hit your session limit…") e a busca para de chamar a IA, mantendo as notas locais.
- Glassdoor removido dos sites padrão do JobSpy (bloqueia com HTTP 403).
- Perguntas de sim/não (ex.: "Will you require sponsorship to work in the country?") não
  recebem mais um campo do perfil (como o país); respostas padrão têm prioridade.

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
