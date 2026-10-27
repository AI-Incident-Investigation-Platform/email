# Устройство email

## Как обрабатывается задача

1. `LettersConsumer` берёт задачу из `email.transactional` (prefetch
   `letters.prefetch` на под) и разбирает тело. Битое тело — dead-letter.
2. `LettersService` проверяет срок: истёкшая задача подтверждается без
   отправки (`outcome=expired`).
3. `LetterRenderer` собирает тему, текст и HTML из
   `src/worker/letters/templates/<шаблон>/<язык>/` (`subject.txt`,
   `body.txt`, `body.html`). Подстановки — `$имя`, в HTML значения
   экранируются; из `expires_in` выводится `expires_in_minutes`. Нет
   шаблона или параметра — dead-letter.
4. `ResendService` отправляет письмо с `Idempotency-Key = message_id`.
5. Исход:
   - отправлено — ack, `outcome=sent`;
   - 429, 5xx, таймаут, сеть — копия в `email.transactional.retry` с
     `x-attempt + 1` и ack оригинала; через `retry_delay_seconds` задача
     возвращается в работу. После `letters.max_attempts` попыток —
     dead-letter;
   - 4xx от Resend — dead-letter: повтор не поможет.

Каждый исход — строка лога `letters.<outcome>` с `message_id`, шаблоном и
номером попытки и счётчик `email_letters_total`. `params` и адрес в логи
не пишутся.

## Код

```
src/
├── main.py              сборка: DI, lifespan (конфиг → соединение → consumer), служебные роуты
├── config/              Config, доступ через `from src.config import cfg`
├── api/
│   ├── health/          /health и /ready
│   ├── metrics/         /metrics
│   └── exc/             ответ об ошибке служебных роутов
├── worker/
│   ├── letters/         consumer, schemas, dto, renderer и templates, service, metrics
│   └── exc/             ошибки домена писем
└── core/
    ├── rabbitmq/        соединение с брокером
    ├── resend/          клиент и сервис Resend
    ├── errors/          категории ошибок, ErrorReport
    ├── di/              провайдеры dishka
    └── logging.py, tracing.py, context.py
```

Тесты: `tests/unit` без внешних зависимостей (Resend подменён
`httpx.MockTransport`), `tests/integration` — RabbitMQ в Testcontainers.

## Ресурсы и масштабирование

- Под: `requests` 50m / 96Mi, `limits` 500m / 192Mi. Не замерено.
- Число подов — KEDA (`k8s/scaledobject.yaml`), 1–3: по
  `rabbitmq_queue_messages_ready{queue="email.transactional"}` из
  Prometheus, 20 задач на под. Метрики недоступны — 1 под.
- Старт ждёт брокер: пока RabbitMQ нет, сервис не принимает трафик, а
  startup-проба через 2 минуты перезапускает под.
- Выкатка: RollingUpdate с `maxUnavailable: 0`; не стали готовы — `make up`
  делает `rollout undo`. При остановке неподтверждённые задачи
  возвращаются брокером в очередь.

## Решения

- **Отдельный воркер писем за RabbitMQ** (2026-10-27): сервисы не зависят
  от скорости и доступности почтового провайдера, воркер масштабируется по
  очереди. Отброшена отправка из каждого сервиса.
- **Resend** (2026-10-27): HTTP API с идемпотентностью, бесплатный тариф
  для стенда.
- **Идемпотентность — `Idempotency-Key` у Resend, без своей БД**
  (2026-10-27): повторная доставка задачи не даёт второго письма, а журнал
  доставки — логи и метрики. Своя таблица писем появится с админкой
  рассылок.
- **Повтор через retry-очередь с TTL, а не requeue** (2026-10-27): requeue
  вернул бы задачу сразу и крутил её без паузы.
- **Срочные и массовые письма — разные очереди**: сейчас есть только
  `email.transactional`; `email.bulk` появится с первой рассылкой.

## Чего пока нет

- Шаблона приглашения в проект и очереди массовых писем.
- Журнала писем в БД и админки рассылок.
- Проверенного домена отправителя в Resend.
- Замеров ресурсов пода.
