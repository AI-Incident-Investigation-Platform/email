.PHONY: help config run up down ps build secret deploy logs \
        format lint lint-fix typecheck check test test-integration test-all

SRC := src tests
BUILD := BUILDX_NO_DEFAULT_ATTESTATIONS=1
CLUSTER := aiip
CONTEXT := k3d-$(CLUSTER)
KUBECTL := kubectl --context $(CONTEXT) -n apps
IMAGE := aiip-email:$(shell date +%Y%m%d%H%M%S)
ON_HOST := RABBITMQ__URL=$$(sed -n 's|^url = "\(amqp://[^@]*@\)[^:/]*\(.*\)"|\1localhost\2|p' config.toml) \
           TRACING__OTLP_ENDPOINT=http://localhost:4318
NEED_FORWARD = @nc -z localhost 5672 2>/dev/null || { echo "инфра закрыта: запусти make -C ../infra forward в соседнем терминале"; exit 1; }

help:
	@echo ""
	@echo "  Первый запуск"
	@echo "    config                    config.toml: секции сервиса из примера + выдача инфры"
	@echo "                              (make -C ../infra service name=email); ключ Resend — руками"
	@echo "    run                       запустить на хосте без Docker, служебные роуты на localhost:8002;"
	@echo "                              нужен make -C ../infra forward"
	@echo ""
	@echo "  Kubernetes (кластер k3d aiip, namespace apps)"
	@echo "    up                        собрать образ, загрузить в кластер, обновить секрет и выкатить"
	@echo "                              RollingUpdate без простоя; если новые поды не стали готовы —"
	@echo "                              откат. Число подов ведёт KEDA по длине очереди писем"
	@echo "    down                      удалить Deployment и ScaledObject, секрет остаётся"
	@echo "    ps                        поды, их нагрузка и решение автоскейлера"
	@echo "    logs                      логи всех подов"
	@echo "    build                     собрать образ и загрузить в кластер"
	@echo ""
	@echo "  Качество кода"
	@echo "    check                     формат + линт + типы"
	@echo "    format                    форматирование ruff"
	@echo "    lint                      проверка линтером"
	@echo "    lint-fix                  форматирование + автоисправление линтера"
	@echo "    typecheck                 проверка типов mypy"
	@echo ""
	@echo "  Тесты"
	@echo "    test                      unit-тесты (без Docker)"
	@echo "    test-integration          integration-тесты (RabbitMQ в Testcontainers)"
	@echo "    test-all                  все тесты"
	@echo ""

config:
	@test -f config.toml && { echo "config.toml уже есть"; exit 1; } || true
	@{ sed -n '/^\[service\]/,/^\[rabbitmq\]/p' config.toml.example | sed '$$d'; \
	   $(MAKE) -s -C ../infra service name=email | sed -n '/^\[rabbitmq\]/,/^$$/p;/^\[tracing\]/,/^$$/p'; } > config.toml
	@echo "создан config.toml, впиши resend.api_key"

run:
	$(NEED_FORWARD)
	$(ON_HOST) uv run python -m src

up: build secret deploy

down:
	$(KUBECTL) delete -k k8s --ignore-not-found

ps:
	@$(KUBECTL) get scaledobject email 2>/dev/null || true
	@echo
	@$(KUBECTL) top pods -l app=email 2>/dev/null || true
	@echo
	@$(KUBECTL) get pods -l app=email -o wide

build:
	$(BUILD) docker build -q -t $(IMAGE) . >/dev/null
	k3d image import $(IMAGE) -c $(CLUSTER)

secret:
	@test -f config.toml || { echo "нужен config.toml: make config"; exit 1; }
	@$(KUBECTL) create secret generic email --from-file=config.toml \
		--dry-run=client -o yaml | $(KUBECTL) apply -f - >/dev/null

deploy:
	kubectl kustomize k8s | sed 's|aiip-email:latest|$(IMAGE)|' | kubectl --context $(CONTEXT) apply -f -
	@$(KUBECTL) rollout status deploy/email --timeout=150s || { echo "новые поды не стали готовы, откатываю"; $(KUBECTL) rollout undo deploy/email; exit 1; }

logs:
	$(KUBECTL) logs -l app=email --prefix --tail=100 -f

test:
	uv run pytest tests --suite=unit

test-integration:
	uv run pytest tests --suite=integration

test-all:
	uv run pytest tests --suite=full

format:
	uv run ruff format $(SRC)

lint:
	uv run ruff check $(SRC)

lint-fix:
	uv run ruff format $(SRC)
	uv run ruff check --fix $(SRC)

typecheck:
	uv run mypy $(SRC)

check:
	uv run ruff format --check $(SRC)
	uv run ruff check $(SRC)
	uv run mypy $(SRC)
