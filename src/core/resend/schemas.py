from pydantic import AwareDatetime, BaseModel


class QuotaUsage(BaseModel):
    used: int
    limit: int | None = None
    resets_at: AwareDatetime


class EmailsUsage(BaseModel):
    daily: QuotaUsage | None = None
    monthly: QuotaUsage


class UsageResponse(BaseModel):
    emails: EmailsUsage
