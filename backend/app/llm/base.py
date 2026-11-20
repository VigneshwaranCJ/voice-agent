import json
import re
from dataclasses import dataclass, field


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON string


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)

    def assistant_message(self) -> dict:
        msg: dict = {"role": "assistant", "content": self.content or ""}
        if self.tool_calls:
            msg["tool_calls"] = [{"id": c.id, "type": "function",
                                  "function": {"name": c.name, "arguments": c.arguments}} for c in self.tool_calls]
        return msg


_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def clean_content(text: str | None) -> str:
    return _THINK.sub("", text or "").strip()


def parse_openai_message(msg: dict) -> LLMResponse:
    calls = []
    for c in msg.get("tool_calls") or []:
        fn = c.get("function", {})
        args = fn.get("arguments", "{}")
        if not isinstance(args, str):
            args = json.dumps(args)
        calls.append(ToolCall(id=c.get("id") or fn.get("name", "call"), name=fn.get("name", ""), arguments=args))
    return LLMResponse(content=clean_content(msg.get("content")), tool_calls=calls)
