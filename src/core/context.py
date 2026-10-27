from contextvars import ContextVar

from opentelemetry import trace

log_context: ContextVar[dict[str, object] | None] = ContextVar("log_context", default=None)


def get_trace_id() -> str:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return "-"
    return format(span_context.trace_id, "032x")


def get_span_id() -> str:
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        return "-"
    return format(span_context.span_id, "016x")
