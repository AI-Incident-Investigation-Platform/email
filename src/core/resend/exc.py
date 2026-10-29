from src.core.errors import CoreError, IntegrationTimeoutError, IntegrationUnavailableError


class ResendUnavailableError(IntegrationUnavailableError):
    code = "resend.unavailable"
    message = "Почтовый провайдер недоступен"


class ResendTimeoutError(IntegrationTimeoutError):
    code = "resend.timeout"
    message = "Почтовый провайдер не ответил вовремя"


class ResendRejectedError(CoreError):
    code = "resend.rejected"
    message = "Почтовый провайдер отклонил письмо"


class ResendRateLimitedError(CoreError):
    code = "resend.rate_limited"
    message = "Почтовый провайдер ограничил частоту запросов"


class ResendQuotaExhaustedError(CoreError):
    code = "resend.quota_exhausted"
    message = "Квота писем почтового провайдера исчерпана"
