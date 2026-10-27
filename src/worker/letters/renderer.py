import html
import math
from collections.abc import Mapping
from pathlib import Path
from string import Template

from src.worker.exc.letters import TemplateNotFoundError, TemplateParamsError
from src.worker.letters.dto import RenderedLetter
from src.worker.letters.enums import LetterTemplate


class LetterRenderer:
    """Собирает письмо из файлов `templates/<шаблон>/<язык>/`: subject.txt, body.txt, body.html.

    Подстановки — `$имя` из params; в HTML значения экранируются. Из `expires_in`
    (секунды) выводится `expires_in_minutes`.
    """

    @staticmethod
    def render(
        template: LetterTemplate, locale: str, params: Mapping[str, str | int]
    ) -> RenderedLetter:
        directory = Path(__file__).parent / "templates" / template.value / locale
        if not directory.is_dir():
            raise TemplateNotFoundError({"template": template.value, "locale": locale})
        values = {key: str(value) for key, value in params.items()}
        if isinstance(expires_in := params.get("expires_in"), int):
            values["expires_in_minutes"] = str(math.ceil(expires_in / 60))
        escaped = {key: html.escape(value) for key, value in values.items()}
        try:
            return RenderedLetter(
                subject=LetterRenderer._fill(directory / "subject.txt", values).strip(),
                text=LetterRenderer._fill(directory / "body.txt", values),
                html=LetterRenderer._fill(directory / "body.html", escaped),
            )
        except (KeyError, ValueError) as exc:
            raise TemplateParamsError(
                {"template": template.value, "params": sorted(params)}
            ) from exc

    @staticmethod
    def _fill(path: Path, values: Mapping[str, str]) -> str:
        return Template(path.read_text(encoding="utf-8")).substitute(values)
