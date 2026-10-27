from src.core.errors import CoreError, IntegrationTimeoutError, IntegrationUnavailableError


class ResendUnavailableError(IntegrationUnavailableError):
    code = "resend.unavailable"
    message = "Почтовый провайдер недоступен или ограничил отправку"


class ResendTimeoutError(IntegrationTimeoutError):
    code = "resend.timeout"
    message = "Почтовый провайдер не ответил вовремя"


class ResendRejectedError(CoreError):
    code = "resend.rejected"
    message = "Почтовый провайдер отклонил письмо"
