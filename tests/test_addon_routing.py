from __future__ import annotations

import importlib
import json

import anyio
import pytest

from ._support import FakeFlow, FakeRequest, FakeResponse


def test_addon_rewrites_only_aiplatform(monkeypatch: pytest.MonkeyPatch) -> None:
    posted: list[tuple[str, bytes, dict[str, str]]] = []

    def fake_post(
        url: str, *, data: bytes, headers: dict[str, str], timeout: int
    ) -> FakeResponse:
        posted.append((url, data, headers))
        return FakeResponse()

    async def exercise() -> None:
        monkeypatch.setenv("ANTIGRAVITY_BRIDGE_PORT", "24680")
        addon = importlib.reload(importlib.import_module("inspect_antigravity._addon"))
        monkeypatch.setattr(addon.requests, "post", fake_post)

        non_aiplatform = FakeFlow(
            request=FakeRequest(
                pretty_host="oauth2.googleapis.com",
                path="/token",
                content=b"{}",
            )
        )
        await addon.request(non_aiplatform)

        aiplatform = FakeFlow(
            request=FakeRequest(
                pretty_host="us-central1-aiplatform.googleapis.com",
                path=(
                    "/v1/projects/project/locations/us-central1/publishers/google/"
                    "models/gemini-2.5-flash:streamGenerateContent?alt=sse"
                ),
                content=b'{"contents": []}',
            )
        )
        await addon.request(aiplatform)

        assert non_aiplatform.response is None
        assert posted == [
            (
                "http://127.0.0.1:24680/v1beta/models/"
                "gemini-2.5-flash:streamGenerateContent?alt=sse",
                b'{"contents": []}',
                {"content-type": "application/json"},
            )
        ]
        assert aiplatform.response is not None
        assert aiplatform.response.status_code == 200
        assert aiplatform.response.content == b"data: {}\n\n"
        assert aiplatform.response.headers["content-type"] == "text/event-stream"

    anyio.run(exercise)


def test_addon_lowercases_vertex_schema_types_for_the_bridge(
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

        vertex_body = {
            "contents": [{"type": "OBJECT"}],
            "tools": [
                {
                    "functionDeclarations": [
                        {
                            "name": "browser",
                            "parameters": {
                                "type": "OBJECT",
                                "properties": {
                                    "action": {"type": "STRING"},
                                    "count": {
                                        "anyOf": [
                                            {"type": "NUMBER"},
                                            {"type": "INTEGER"},
                                        ]
                                    },
                                    "options": {
                                        "type": "ARRAY",
                                        "items": {"type": ["STRING", "NULL"]},
                                    },
                                    "enabled": {"allOf": [{"type": "BOOLEAN"}]},
                                    "target": {
                                        "oneOf": [
                                            {
                                                "type": "OBJECT",
                                                "properties": {
                                                    "id": {"type": "STRING"}
                                                },
                                            }
                                        ]
                                    },
                                },
                            },
                        }
                    ]
                }
            ],
        }
        aiplatform = FakeFlow(
            request=FakeRequest(
                pretty_host="us-central1-aiplatform.googleapis.com",
                path=(
                    "/v1/projects/project/locations/us-central1/publishers/google/"
                    "models/gemini-2.5-flash:streamGenerateContent?alt=sse"
                ),
                content=json.dumps(vertex_body).encode(),
            )
        )

        await addon.request(aiplatform)

        forwarded = json.loads(posted[0])
        schema = forwarded["tools"][0]["functionDeclarations"][0]["parameters"]
        assert schema["type"] == "object"
        assert schema["properties"]["action"]["type"] == "string"
        assert schema["properties"]["count"]["anyOf"][0]["type"] == "number"
        assert schema["properties"]["count"]["anyOf"][1]["type"] == "integer"
        assert schema["properties"]["options"]["type"] == "array"
        assert schema["properties"]["options"]["items"]["type"] == ["string", "null"]
        assert schema["properties"]["enabled"]["allOf"][0]["type"] == "boolean"
        target_schema = schema["properties"]["target"]["oneOf"][0]
        assert target_schema["type"] == "object"
        assert target_schema["properties"]["id"]["type"] == "string"
        assert forwarded["contents"] == [{"type": "OBJECT"}]

    anyio.run(exercise)
