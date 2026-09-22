# Política de segurança

O candidatador lida com dados sensíveis (currículos, documentos, contatos e sessões de
navegador logadas). Levamos vulnerabilidades a sério.

## Como reportar

**Não abra uma issue pública.** Use o
[reporte privado de vulnerabilidades](https://github.com/davidogral/candidatador/security/advisories/new)
do GitHub. Responderemos em até 7 dias.

## Escopo

- Vazamento de dados do perfil/cofre para terceiros não declarados
- Execução de código a partir de conteúdo de vagas (ex.: descrição maliciosa, prompt injection que
  leve a ações não confirmadas pelo usuário)
- Envio de candidaturas sem confirmação no modo `review`
- Dependências com vulnerabilidades conhecidas

## Como protegemos seus dados

- Tudo é armazenado localmente (`candidatador init` mostra a pasta). Não há servidor.
- A IA é opcional; quando ativa, e-mail e telefone não são enviados.
- O perfil do navegador (cookies/logins) fica em `<pasta de dados>/browser`. Proteja essa pasta
  como protegeria suas senhas.
