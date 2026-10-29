import asyncio
import os
import socket
import time
from collections.abc import Iterator
from pathlib import Path

import aio_pika
import pytest
from testcontainers.core.container import DockerContainer

from tests.support.scenarios import Layer, ScenarioStatus, Suite, load_scenarios

ROOT = Path(__file__).resolve().parents[1]
TESTS_ROOT = ROOT / "tests"
_RABBITMQ_KEY = pytest.StashKey[DockerContainer]()

os.environ.update(
    {
        "RABBITMQ__URL": "amqp://test_only:test_only@127.0.0.1:1/aiip",
        "RABBITMQ__RECONNECT_DELAY_SECONDS": "0.1",
        "RESEND__API_KEY": "re_test_only",
        "RESEND__BASE_URL": "http://127.0.0.1:1",
        "RESEND__FROM_ADDRESS": "AIIP <no-reply@example.com>",
        "RESEND__REQUESTS_PER_SECOND": "1000",
        "LETTERS__RETRY_DELAY_SECONDS": "1",
        "TRACING__ENABLED": "false",
    }
)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--suite",
        choices=[suite.value for suite in Suite],
        default=Suite.FULL.value,
        help="Слой тестов: unit (без Docker), integration (RabbitMQ), full.",
    )


def _suite(config: pytest.Config) -> Suite:
    return Suite(config.getoption("--suite"))


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool:
    try:
        relative = collection_path.relative_to(TESTS_ROOT)
    except ValueError:
        return False
    if not relative.parts or relative.parts[0] not in set(Layer):
        return False
    return Layer(relative.parts[0]) not in _suite(config).layers


def pytest_sessionstart(session: pytest.Session) -> None:
    if Layer.INTEGRATION not in _suite(session.config).layers:
        return
    rabbitmq = (
        DockerContainer("rabbitmq:4.3.5-alpine")
        .with_env("RABBITMQ_DEFAULT_USER", "test_only")
        .with_env("RABBITMQ_DEFAULT_PASS", "test_only")
        .with_env("RABBITMQ_DEFAULT_VHOST", "aiip")
        .with_exposed_ports(5672)
    )
    try:
        rabbitmq.start()
        url = (
            f"amqp://test_only:test_only@{rabbitmq.get_container_host_ip()}:"
            f"{rabbitmq.get_exposed_port(5672)}/aiip"
        )
        asyncio.run(_wait_for_rabbitmq(url))
        os.environ["RABBITMQ__URL"] = url
    except BaseException as exc:
        rabbitmq.stop()
        pytest.exit(f"Integration-тестам нужен RabbitMQ, он не поднялся: {exc}", returncode=2)
    session.config.stash[_RABBITMQ_KEY] = rabbitmq


async def _wait_for_rabbitmq(url: str) -> None:
    deadline = time.monotonic() + 60
    while True:
        try:
            connection = await aio_pika.connect(url, timeout=2)
            await connection.close()
            return
        except aio_pika.exceptions.AMQPError, OSError, TimeoutError:
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(0.5)


def pytest_sessionfinish(session: pytest.Session) -> None:
    rabbitmq = session.config.stash.get(_RABBITMQ_KEY, None)
    if rabbitmq is not None:
        rabbitmq.stop()


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    layers = _suite(config).layers
    manifest = load_scenarios(TESTS_ROOT / "scenarios.toml")
    selected: list[pytest.Item] = []
    seen: dict[str, str] = {}
    for item in items:
        marker = item.get_closest_marker("case")
        if marker is None:
            raise pytest.UsageError(f"missing @pytest.mark.case: {item.nodeid}")
        case_id = marker.kwargs.get("id")
        if not isinstance(case_id, str) or (scenario := manifest.get(case_id)) is None:
            raise pytest.UsageError(f"case absent from scenarios.toml: {case_id} ({item.nodeid})")
        test_id = item.nodeid.split("[", 1)[0]
        if seen.setdefault(case_id, test_id) != test_id:
            raise pytest.UsageError(f"duplicate case id {case_id}: {seen[case_id]}, {test_id}")
        expected_dir = TESTS_ROOT / scenario.layer / scenario.domain
        if expected_dir not in Path(str(item.path)).parents:
            raise pytest.UsageError(
                f"{case_id}: file must live under {expected_dir.relative_to(ROOT)}"
            )
        if scenario.layer not in layers:
            continue
        if scenario.status == ScenarioStatus.KNOWN_BUG:
            item.add_marker(pytest.mark.xfail(strict=True, reason=scenario.reason))
        selected.append(item)

    full_tree_requested = any(
        Path(argument).resolve() == TESTS_ROOT
        for argument in config.args
        if not argument.startswith("-")
    )
    if full_tree_requested:
        missing = {s.id for s in manifest.values() if s.layer in layers} - seen.keys()
        if missing:
            raise pytest.UsageError(
                "manifest scenarios were not collected: " + ", ".join(sorted(missing))
            )
    deselected = [item for item in items if item not in selected]
    items[:] = selected
    if deselected:
        config.hook.pytest_deselected(items=deselected)


@pytest.fixture(autouse=True)
def block_external_network(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    layer = Layer(Path(str(request.node.path)).relative_to(TESTS_ROOT).parts[0])
    real_connect = socket.socket.connect

    def guarded_connect(sock: socket.socket, address: tuple[object, ...] | str) -> None:
        host = address[0] if isinstance(address, tuple) else None
        if layer == Layer.INTEGRATION and host in {"127.0.0.1", "::1", "localhost"}:
            real_connect(sock, address)
            return
        raise RuntimeError(f"network is forbidden in {layer} tests: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    yield
