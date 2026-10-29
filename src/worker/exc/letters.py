from src.core.errors import GoneError, OverloadedError, RuleViolationError


class LetterExpiredError(GoneError):
    code = "letters.expired"
    message = "Срок письма истёк до отправки"


class LetterSupersededError(GoneError):
    code = "letters.superseded"
    message = "Письмо заменено более новым с тем же ключом вытеснения"


class LetterDeferredError(OverloadedError):
    code = "letters.deferred"
    message = "Квота или частота провайдера не позволяют отправить письмо сейчас"


class TemplateNotFoundError(RuleViolationError):
    code = "letters.template_not_found"
    message = "Нет шаблона письма для этого языка"


class TemplateParamsError(RuleViolationError):
    code = "letters.template_params_invalid"
    message = "Параметры не подходят шаблону письма"


class LetterRejectedError(RuleViolationError):
    code = "letters.rejected"
    message = "Почтовый провайдер отклонил письмо"
