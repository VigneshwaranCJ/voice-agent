from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=200)
    new_password: str = Field(min_length=12, max_length=200)


TeamRole = Literal["platform_admin", "tenant_admin", "tenant_agent"]


class UserCreateIn(BaseModel):
    email: EmailStr
    full_name: str = Field(default="", max_length=200)
    role: TeamRole
    password: str = Field(min_length=12, max_length=200)


class UserUpdateIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    role: TeamRole | None = None
    is_active: bool | None = None


class PasswordResetIn(BaseModel):
    new_password: str = Field(min_length=12, max_length=200)


class LeadUpdateIn(BaseModel):
    status: Literal["new", "qualified", "contacted", "won", "lost"] | None = None
    assigned_to: str | None = Field(default=None, max_length=200)  # null clears the assignment
    notes: str | None = Field(default=None, max_length=4000)


class EscalationUpdateIn(BaseModel):
    status: Literal["open", "assigned", "resolved"] | None = None
    assigned_to: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=4000)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class TenantIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9-]{2,80}$")
    industry: str
    admin_email: EmailStr | None = None
    admin_password: str | None = Field(default=None, min_length=8)


class TenantOut(ORM):
    id: str
    name: str
    slug: str
    industry: str
    is_active: bool
    created_at: datetime


class BusinessProfileIn(BaseModel):
    display_name: str
    description: str = ""
    phone: str = ""
    email: str = ""
    website: str = ""
    timezone: str = "Asia/Kolkata"
    operating_hours: dict[str, str] = {}
    locations: list[Any] = []
    services: list[str] = []
    policies: dict[str, Any] = {}
    escalation_contacts: list[Any] = []


class BusinessProfileOut(BusinessProfileIn, ORM):
    id: str


class AgentConfigIn(BaseModel):
    persona_name: str = "Priya"
    personality: str = ""
    system_instructions: str = ""
    greeting: dict[str, str] = {}
    enabled_tools: list[str] = []
    workflows: dict[str, Any] = {}
    escalation_policy: dict[str, Any] = {}
    llm_settings: dict[str, Any] = {}


class AgentConfigOut(AgentConfigIn, ORM):
    id: str
    version: int
    created_at: datetime


class AgentIn(BaseModel):
    name: str
    industry: str
    default_language: str = "en-IN"
    languages: list[str] = ["en-IN", "ta-IN"]
    public_widget_enabled: bool = True
    is_active: bool = True
    config: AgentConfigIn | None = None


class AgentOut(ORM):
    id: str
    tenant_id: str
    name: str
    industry: str
    default_language: str
    languages: list[str]
    public_widget_enabled: bool
    is_active: bool
    created_at: datetime


class AgentDetailOut(AgentOut):
    config: AgentConfigOut | None


class KnowledgeDocOut(ORM):
    id: str
    agent_id: str | None
    title: str
    source_type: str
    filename: str | None
    status: str
    error: str | None
    chunk_count: int
    created_at: datetime


class KnowledgeTextIn(BaseModel):
    title: str
    text: str = Field(min_length=1)
    source_type: str = "faq"
    agent_id: str | None = None


class DBConnectionIn(BaseModel):
    name: str
    kind: str = Field(pattern=r"^(postgresql|mysql|rest_api)$")
    config: dict[str, Any]  # dsn / host / user / password / base_url / api_key …  (encrypted at rest)
    permissions: str = Field(default="read", pattern=r"^(read|read_write)$")


class DBConnectionOut(ORM):
    id: str
    name: str
    kind: str
    permissions: str
    last_tested_at: datetime | None
    last_test_ok: bool | None


class ConversationOut(ORM):
    id: str
    agent_id: str
    channel: str
    status: str
    language: str | None
    languages_used: list[str]
    intents: list[str]
    summary: str | None
    resolved: bool | None
    created_at: datetime
    ended_at: datetime | None


class MessageOut(ORM):
    id: str
    role: str
    content: str
    language: str | None
    interrupted: bool
    meta: dict
    created_at: datetime


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None
    language: str | None = None


class ChatOut(BaseModel):
    conversation_id: str
    reply: str
    language: str
    events: list[dict]
    tool_calls: list[dict]
    escalated: bool
