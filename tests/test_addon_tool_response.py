from __future__ import annotations

import importlib
import json

import anyio
import pytest

from ._support import FakeFlow, FakeRequest, FakeResponse


def test_addon_relabels_model_role_function_response_to_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[bytes] = []

    def fake_post(
        _: str, *, data: bytes, headers: dict[str, str], timeout: int
    ) -> FakeResponse:
        posted.append(data)
        return FakeResponse()

    async def exercise() -> None:
        monkeypatch.setenv("ANTIGRAVITY_BRIDGE_PORT", "24680")
        addon = importlib.reload(importlib.import_module("inspect_antigravity._addon"))
        monkeypatch.setattr(addon.requests, "post", fake_post)

        body = {
            "contents": [
                {"role": "user", "parts": [{"text": "list the schemas"}]},
                {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": "call_mcp_tool",
                                "args": {"tool": "postgres_schema"},
                            }
                        }
                    ],
                },
                {
                    "role": "model",
                    "parts": [
                        {
                            "functionResponse": {
                                "name": "call_mcp_tool",
                                "response": {"output": "ok"},
                            }
                        }
                    ],
                },
                {
                    "role": "model",
                    "parts": [
                        {"text": "mixed turn"},
                        {
                            "functionResponse": {
                                "name": "call_mcp_tool",
                                "response": {"output": "mixed"},
                            }
                        },
                    ],
                },
            ],
        }
        aiplatform = FakeFlow(
            request=FakeRequest(
                pretty_host="us-central1-aiplatform.googleapis.com",
                path=(
                    "/v1/projects/project/locations/us-central1/publishers/google/"
                    "models/gemini-2.5-flash:streamGenerateContent?alt=sse"
                ),
                content=json.dumps(body).encode(),
            )
        )

        await addon.request(aiplatform)

        contents = json.loads(posted[0])["contents"]
        assert contents[0] == {"role": "user", "parts": [{"text": "list the schemas"}]}
        assert contents[1]["role"] == "model"
        assert "functionCall" in contents[1]["parts"][0]
        assert contents[2] == {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "call_mcp_tool",
                        "response": {"output": "ok"},
                    }
                }
            ],
        }
        assert contents[3] == {"role": "model", "parts": [{"text": "mixed turn"}]}
        assert contents[4] == {
            "role": "user",
            "parts": [
                {
                    "functionResponse": {
                        "name": "call_mcp_tool",
                        "response": {"output": "mixed"},
                    }
                }
            ],
        }
        assert len(contents) == 5

    anyio.run(exercise)
