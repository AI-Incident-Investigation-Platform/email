# Входы email

Публичного HTTP API нет. Работа приходит задачами из RabbitMQ.

## Задача на письмо

Отправитель публикует в exchange `email` (direct, durable) с routing key
`send.transactional`, `mandatory` и подтверждением брокера. Тело —
JSON:

```json
{
  "message_id": "0196f2c4-6f0e-7a51-9c3e-1d2b3a4c5d6e",
  "template": "auth.login_code",
  "to": "user@example.com",
  "locale": "ru",
  "params": {"code": "004271", "expires_in": 300},
  "created_at": "2026-10-27T12:00:00Z",
  "expires_at": "2026-10-27T12:05:00Z",
  "collapse_key": "auth.login_code:user@example.com"
}
```

| Поле | Что |
|---|---|
| `message_id` | ключ идемпотентности: повтор задачи не даёт второго письма (`Idempotency-Key` у Resend) |
| `template` | имя шаблона, см. таблицу ниже |
| `to` | один адрес |
| `locale` | язык шаблона, двухбуквенный |
| `params` | подстановки шаблона; в логи не пишутся |
| `expires_at` | после этого момента письмо не отправляется |
| `created_at` | когда отправитель поставил задачу; нужен вместе с `collapse_key` |
| `collapse_key` | необязательный ключ вытеснения: из ждущих писем с одним ключом уходит только самое новое по `created_at`. Не логируется |

Свойства AMQP: `message_id`, `content_type: application/json`, persistent,
`expiration` — оставшийся срок, `traceparent` в заголовках. Заголовок
`x-attempt` ставит сам воркер при повторе.

| Шаблон | Кто ставит | `params` |
|---|---|---|
| `auth.login_code` | `auth`, вход и регистрация | `code` — 6 цифр, `expires_in` — секунды |

## Очереди

| Очередь | Что в ней |
|---|---|
| `email.transactional` | срочные письма; quorum, dead-letter в `email.dead` |
| `email.transactional.retry` | повтор после временного отказа и ожидание квоты провайдера; живёт `letters.retry_delay_seconds` и возвращается в `email` |
| `email.transactional.dead` | битые, отклонённые провайдером и исчерпавшие попытки задачи; хранятся `letters.dead_letter_ttl_days` |

Топологию объявляет воркер при старте; отправитель объявляет только
exchange `email`.

## Служебные роуты

| Метод и путь | Кто зовёт | Ответ |
|---|---|---|
| `GET /health` | kubelet: liveness, startup | `200 {status: "ok"}`, зависимостей не проверяет |
| `GET /ready` | kubelet: readiness | `200`, если соединение с RabbitMQ живо; иначе `503` `rabbitmq.unavailable` |
| `GET /metrics` | Alloy | `email_letters_total{template, outcome}`, `email_delivery_duration_seconds`, `email_resend_quota_used{period}` и `email_resend_quota_limit{period}` (`daily`, `monthly`), метрики процесса |
