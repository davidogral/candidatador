# Configuração

`candidatador init` cria dois arquivos na pasta de dados (veja o caminho na saída do comando,
ou defina `CANDIDATADOR_HOME`).

## profile.yaml

| Campo | Uso |
|---|---|
| `personal.*` | nome, e-mail, telefone, cidade, LinkedIn, GitHub, portfólio — preenchem formulários |
| `headline`, `summary` | contexto para IA e cartas de apresentação |
| `seniority` | `estagio`, `junior`, `pleno`, `senior`, `especialista`, `lideranca` — pontuação |
| `skills` | habilidades comparadas com o texto da vaga (até 40 pontos) |
| `target.roles` | cargos desejados; também são as palavras-chave padrão da busca |
| `target.keywords_required` | a vaga precisa conter ao menos uma |
| `target.keywords_excluded` | título com qualquer uma delas é descartado |
| `target.remote` | `only`, `preferred`, `any`, `no` |
| `target.locations` | cidades/estados aceitos |
| `target.companies_excluded` | empresas que você não quer ver (ex.: empregador atual) |
| `answers` | respostas padrão para perguntas comuns; chaves livres também funcionam: a chave `aceita_pj: "Sim"` responde perguntas que contenham "aceita pj" |

## config.yaml

```yaml
sources:
  gupy:       { enabled: true, max_results: 100 }
  remotive:   { enabled: true, max_results: 50 }
  greenhouse: { enabled: true, boards: [nubank, gitlab] }
  lever:      { enabled: true, companies: [palantir] }
  ashby:      { enabled: false, organizations: [] }
  jobspy:     { enabled: false, sites: [linkedin, indeed, google], country_indeed: brazil }

matching:
  min_score: 40      # abaixo disso a vaga não aparece nas listagens
  use_ai: false

ai:
  provider: auto     # auto | claude-cli | codex-cli | api
  model: ""          # vazio = padrão do provedor
  effort: low        # low | medium | high

apply:
  mode: review       # review | auto
  headless: false    # só vale no modo auto
  max_per_day: 20
  delay_seconds: 30
```

### Como achar o slug de uma empresa

- Greenhouse: `https://job-boards.greenhouse.io/<slug>` ou `boards.greenhouse.io/<slug>`
- Lever: `https://jobs.lever.co/<slug>`
- Ashby: `https://jobs.ashbyhq.com/<slug>`
