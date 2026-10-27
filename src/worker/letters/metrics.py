from prometheus_client import Counter, Histogram

LETTERS = Counter(
    "email_letters_total",
    "Задачи на письма по шаблону и исходу: sent, retried, dead, expired",
    ["template", "outcome"],
)
DELIVERY_DURATION = Histogram(
    "email_delivery_duration_seconds",
    "Время обработки задачи на письмо, включая запрос к провайдеру",
    ["template"],
)
