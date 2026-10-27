import pytest

from src.worker.exc.letters import TemplateNotFoundError, TemplateParamsError
from src.worker.letters.enums import LetterTemplate
from src.worker.letters.renderer import LetterRenderer


@pytest.mark.case(id="LETTERS-RENDER-001")
def test_login_code_letter_is_rendered_from_template() -> None:
    letter = LetterRenderer.render(
        LetterTemplate.AUTH_LOGIN_CODE, "ru", {"code": "<b>04</b>", "expires_in": 300}
    )

    assert letter.subject == "Код входа в AIIP: <b>04</b>"
    assert "<b>04</b>" in letter.text
    assert "5 мин" in letter.text
    assert "&lt;b&gt;04&lt;/b&gt;" in letter.html
    assert "<b>04</b>" not in letter.html


@pytest.mark.case(id="LETTERS-RENDER-002")
def test_missing_template_or_param_is_permanent_error() -> None:
    with pytest.raises(TemplateNotFoundError):
        LetterRenderer.render(LetterTemplate.AUTH_LOGIN_CODE, "de", {"code": "1", "expires_in": 1})
    with pytest.raises(TemplateParamsError):
        LetterRenderer.render(LetterTemplate.AUTH_LOGIN_CODE, "ru", {"expires_in": 300})
