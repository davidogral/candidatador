# Privacidade

| Dado | Onde fica | Sai da sua máquina? |
|---|---|---|
| `profile.yaml`, `config.yaml` | pasta de dados local | não |
| Documentos (currículos, certificados) | `<pasta>/vault/` | só quando **você** envia uma candidatura |
| Vagas e histórico | `<pasta>/candidatador.db` (SQLite) | não |
| Sessões do navegador | `<pasta>/browser/` | não |
| Perfil + texto do currículo + vaga | — | **só se a IA estiver ativa**, para a API da Anthropic (sem e-mail e telefone) |

Não há telemetria. Para apagar tudo, remova a pasta de dados.
