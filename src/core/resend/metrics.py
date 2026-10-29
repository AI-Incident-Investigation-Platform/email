from prometheus_client import Gauge

QUOTA_USED = Gauge(
    "email_resend_quota_used",
    "Израсходованная квота писем Resend по периоду: daily, monthly",
    ["period"],
)
QUOTA_LIMIT = Gauge(
    "email_resend_quota_limit",
    "Квота писем Resend, которую соблюдает воркер, по периоду: daily, monthly",
    ["period"],
)
