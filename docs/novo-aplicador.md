# Adicionando um aplicador

Aplicadores preenchem e enviam formulários de candidatura. A maioria herda de
`BrowserApplier`, que já cuida de: abrir o navegador com perfil persistente, `--dry-run`,
detecção de captcha, modo `review`/`auto` e confirmação antes do envio.

```python
from candidatador.apply.base import ApplyContext
from candidatador.apply.browser import (
    BrowserApplier,
    fill_if_present,
    fill_open_questions,
    upload_if_present,
)


class WorkableApplier(BrowserApplier):
    name = "workable"
    display_name = "Workable"

    @classmethod
    def supports(cls, url: str) -> bool:
        return "apply.workable.com" in url

    def fill(self, page, ctx: ApplyContext, notes: list[str]) -> None:
        p = ctx.profile.personal
        fill_if_present(page, "input[name='firstname']", p.first_name)
        fill_if_present(page, "input[name='lastname']", p.last_name)
        fill_if_present(page, "input[name='email']", p.email)
        upload_if_present(page, "input[type='file']", ctx.resume.path if ctx.resume else None)
        fill_open_questions(page, "form", ctx, notes)  # perguntas personalizadas

    def submit(self, page) -> None:
        page.get_by_role("button", name="Submit application").click()
```

## Regras

- **Nunca** clique em “enviar” fora de `submit()`. O fluxo de confirmação depende disso.
- Tudo que não conseguir preencher vai para `notes` — o usuário vê e o histórico registra.
- Perguntas sempre passam por `ctx.answers.resolve(...)` para ficarem auditáveis.
- Seletores quebram: prefira `name`, `id` e papéis ARIA a classes CSS geradas.
- Teste com `candidatador apply <vaga> --dry-run` e descreva no PR as vagas usadas no teste.

Registre em `apply/__init__.py` (`BUILTIN`) ou via entry point `candidatador.appliers`.
