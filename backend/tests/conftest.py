import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_db}",
    "SARVAM_API_KEY": "",
    "REDIS_URL": "",
    "SEED_DEMO_DATA": "false",
    "ENVIRONMENT": "development",
    "RATE_LIMIT_PER_MINUTE": "100000",
})

import json  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.context.manager import load_agent_bundle  # noqa: E402
from app.core.database import SessionLocal, create_all, engine  # noqa: E402
from app.llm.base import LLMResponse, ToolCall  # noqa: E402
from app.llm.sarvam import set_llm  # noqa: E402
from app.models import Agent, Base, Tenant  # noqa: E402
from app.orchestration.engine import AgentEngine  # noqa: E402
from app.orchestration.lifecycle import start_conversation  # noqa: E402
from app.seed import seed  # noqa: E402

TENANT_PW = "ChangeMe-Tenant-123"


class ScriptedLLM:
    """Test double for the LLM provider: returns queued responses and records the prompts it saw."""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls: list[list[dict]] = []
        self.opts: list[dict] = []
        self.tools: list = []

    def queue(self, *items):
        self.script.extend(items)

    async def complete(self, messages, tools=None, **opts):
        self.calls.append(messages)
        self.opts.append(opts)
        self.tools.append(tools)
        if not self.script:
            return LLMResponse(content="Okay.")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(messages)
        return item


def call(tool_name: str, **args) -> LLMResponse:
    return LLMResponse(content="", tool_calls=[ToolCall(id=f"c_{tool_name}", name=tool_name, arguments=json.dumps(args))])


def say(text: str) -> LLMResponse:
    return LLMResponse(content=text)


def tool_results(messages: list[dict]) -> list[dict]:
    return [json.loads(m["content"]) for m in messages if m.get("role") == "tool"]


@pytest.fixture(autouse=True)
async def fresh_db():
    from app.knowledge.retrieval import clear_cache

    clear_cache()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await create_all()
    async with SessionLocal() as db:
        await seed(db)
    yield


@pytest.fixture
def llm():
    s = ScriptedLLM()
    set_llm(s)
    yield s
    set_llm(None)


@pytest.fixture
async def db():
    async with SessionLocal() as s:
        yield s


async def agent_for(db, slug: str) -> Agent:
    t = (await db.execute(select(Tenant).where(Tenant.slug == slug))).scalar_one()
    return (await db.execute(select(Agent).where(Agent.tenant_id == t.id))).unique().scalar_one()


async def new_engine(db, slug: str, llm, channel="web_text"):
    agent = await agent_for(db, slug)
    bundle = await load_agent_bundle(db, agent.id)
    state = await start_conversation(db, bundle, channel)
    return AgentEngine(db, bundle, llm=llm), state


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def login(client, email: str, password: str = TENANT_PW) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
