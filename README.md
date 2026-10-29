# email

Воркер писем AIIP. Берёт задачи из RabbitMQ (exchange `email`), собирает
письмо по шаблону и отправляет через [Resend](https://resend.com). Сам письма
не придумывает: что и кому отправить, решает сервис, который поставил
задачу (сейчас — `auth`, код входа).

Публичного API нет: из HTTP только `/health`, `/ready` и `/metrics`, без
Ingress. Работает в namespace `apps` кластера `aiip` одним подом: скорость
отправки ограничивает квота провайдера, а не под.

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
make up              # образ → кластер, секрет, Recreate с откатом
make ps              # под и его нагрузка
make logs
make down            # убрать Deployment; секрет остаётся
```

На хосте: `make -C ../infra forward` в соседнем терминале, затем
`make run`.

Без подтверждённого домена Resend отправляет письма только на почту
владельца аккаунта Resend с адреса `onboarding@resend.dev`. Воркер
соблюдает квоты Resend (`resend.requests_per_second`, `daily_quota`,
`monthly_quota`) для всех писем: сверх квоты письмо ждёт в очереди, пока
не истечёт его срок. Подробности — «Квоты провайдера» в
[docs/design.md](docs/design.md).

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
