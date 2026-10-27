# email

Воркер писем AIIP. Берёт задачи из RabbitMQ (exchange `email`), собирает
письмо по шаблону и отправляет через [Resend](https://resend.com). Сам письма
не придумывает: что и кому отправить, решает сервис, который поставил
задачу (сейчас — `auth`, код входа).

Публичного API нет: из HTTP только `/health`, `/ready` и `/metrics`, без
Ingress. Работает в namespace `apps` кластера `aiip`; число подов (1–3)
ведёт KEDA по длине очереди `email.transactional`.

## Документация

- [docs/endpoints.md](docs/endpoints.md) — формат задачи на письмо, очереди,
  служебные роуты.
- [docs/design.md](docs/design.md) — повторы, dead-letter, шаблоны,
  масштабирование, решения.
- [docs/requirements.md](docs/requirements.md) — что требует документация
  продукта и что из этого реализовано.

## Стек

Python 3.14, uv, FastAPI (только служебные роуты), dishka, aio-pika к
RabbitMQ, httpx к Resend, pydantic-settings, OpenTelemetry,
prometheus-client.

## Запуск

Нужны Docker, `k3d`, `kubectl` и поднятая инфра (`make -C ../infra up`).

```bash
make config          # первый раз: config.toml из примера и выдачи инфры
                     # затем впиши resend.api_key и resend.from_address
make up              # образ → кластер, секрет, RollingUpdate с откатом
make ps              # поды и решение автоскейлера
make logs
make down            # убрать Deployment и ScaledObject; секрет остаётся
```

На хосте: `make -C ../infra forward` в соседнем терминале, затем
`make run`.

Без подтверждённого домена Resend отправляет письма только на почту
владельца аккаунта Resend с адреса `onboarding@resend.dev`. Дневной лимит
бесплатного тарифа приходит ответом 429 и обрабатывается как временный
отказ: задача повторяется, пока не истечёт её срок или попытки.

## Проверка

```bash
make check             # ruff format --check + ruff check + mypy
make test              # unit, без Docker
make test-integration  # RabbitMQ в Testcontainers, Resend подменён
make test-all
```

## Конфиг и секреты

`config.toml` (не в git) собирается из `config.toml.example` и блоков
`[rabbitmq]` и `[tracing]`, которые печатает
`make -C ../infra service name=email`. Переменные окружения перекрывают его
(вложенность через `__`). В кластере он лежит в Secret `email` и
монтируется файлом. Ключ Resend — `resend.api_key`, в git не попадает.
