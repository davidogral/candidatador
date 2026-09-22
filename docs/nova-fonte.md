# Adicionando uma fonte de vagas

Uma fonte é uma classe que herda de `JobSource` e implementa `search()`.

```python
# src/candidatador/sources/minha_fonte.py
from collections.abc import Iterable

from candidatador.sources.base import JobPosting, JobSource, SearchQuery, parse_datetime, strip_html


class MinhaFonte(JobSource):
    name = "minhafonte"  # usado no config.yaml e em --source
    display_name = "Minha Fonte"
    regions = ("BR",)
    terms_note = None  # preencha se a fonte tiver restrições de uso

    def search(self, query: SearchQuery) -> Iterable[JobPosting]:
        resp = self.client.get(
            "https://api.minhafonte.com/jobs",
            params={"q": " ".join(query.keywords), "limit": self.max_results(query)},
        )
        resp.raise_for_status()
        for item in resp.json()["results"]:
            yield JobPosting(
                source=self.name,
                external_id=str(item["id"]),
                title=item["title"],
                company=item["company"],
                location=item.get("city", ""),
                remote=item.get("remote"),
                url=item["url"],
                description=strip_html(item.get("html")),
                posted_at=parse_datetime(item.get("published_at")),
                raw={"id": item["id"]},
            )
```

## Checklist

1. **Prefira APIs públicas** ou endpoints JSON usados pelo próprio site público. Scraping de
   HTML só com `terms_note` explicando os riscos e a fonte desativada por padrão.
2. Use sempre `self.client` (tem timeout e User-Agent identificando o projeto).
3. Respeite `query.keywords`, `query.remote_only`, `query.location` quando a API suportar;
   o que não for suportado é filtrado depois em `matching/filters.py`.
4. `external_id` precisa ser estável; `posted_at` deve ser timezone-aware (`parse_datetime` garante).
5. Não guarde a descrição inteira em `raw` — ela já está em `description`.
6. Registre em `BUILTIN` (`sources/__init__.py`) e adicione um bloco no `templates/config.yaml`.
7. Escreva testes com `respx` em `tests/test_sources.py` — **sem acessar a internet**.
8. Atualize a tabela de fontes no `README.md` e o `CHANGELOG.md`.

## Publicando como plugin separado

Não quer (ou não pode) incluir a fonte aqui? Publique seu próprio pacote e registre:

```toml
[project.entry-points."candidatador.sources"]
minhafonte = "meu_pacote.fonte:MinhaFonte"
```

Depois de `pip install meu-pacote`, ela aparece em `candidatador sources`.
