import unittest
from unittest.mock import patch

import httpx

from modules.agent.technical_interruptions import interruption_from_provider_error
from modules.chat import get_chat_provider
from modules.providers.gemini import GeminiProvider, classify_gemini_error_response
from modules.providers.vertexai import VertexAIProvider, classify_vertexai_error_response


class _FakeResponse:
    def __init__(self, status_code=200, text='{"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}'):
        self.status_code = status_code
        self.text = text
        self.headers = {}


class _FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, headers=None, json=None):
        self.post_calls.append({"url": url, "headers": headers or {}, "json": json or {}})
        return _FakeResponse()


class VertexAIProviderTests(unittest.IsolatedAsyncioTestCase):
    def test_model_routing_vertexai_prefix(self):
        provider = get_chat_provider(
            "vertexai/gemini-2.5-flash",
            settings={"vertexai": {"project_id": "my-project", "location": "us-central1"}},
        )

        self.assertIsInstance(provider, VertexAIProvider)
        self.assertEqual("gemini-2.5-flash", provider.model_name)

    def test_model_routing_existing_gemini_unchanged(self):
        provider = get_chat_provider(
            "gemini-2.5-flash",
            settings={"gemini_api_key": "test-key"},
        )

        self.assertIsInstance(provider, GeminiProvider)
        self.assertEqual("gemini-2.5-flash", provider.model_name)

    def test_vertexai_requires_project_id(self):
        with self.assertRaises(ValueError) as cm:
            VertexAIProvider(
                "vertexai/gemini-2.5-flash",
                settings={"vertexai": {"location": "us-central1"}},
            )

        self.assertIn("project_id is missing", str(cm.exception))

    def test_vertexai_builds_correct_model_resource(self):
        provider = VertexAIProvider(
            "vertexai/gemini-2.5-flash",
            settings={"vertexai": {"project_id": "my-project", "location": "us-central1"}},
        )

        self.assertEqual(
            "projects/my-project/locations/us-central1/publishers/google/models/gemini-2.5-flash",
            provider.model_resource,
        )

    def test_ai_studio_prepay_depleted_is_not_retryable(self):
        response = httpx.Response(429, text='{"error":"prepayment credits are depleted"}')
        error = classify_gemini_error_response(
            response,
            response.text,
            provider_name="gemini",
            model_name="gemini-2.5-flash",
            url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:streamGenerateContent",
        )

        interruption = interruption_from_provider_error(error, provider_name=error.provider_name)
        self.assertEqual("billing_exhausted_ai_studio_prepay", error.kind)
        self.assertFalse(interruption.retryable)
        self.assertIn("AI Studio prepay credits are depleted", interruption.message)

    def test_vertexai_429_is_quota_or_rate_limit(self):
        response = httpx.Response(429, text='{"error":"Quota exceeded"}')
        error = classify_vertexai_error_response(
            response,
            response.text,
            provider_name="vertexai",
            model_name="gemini-2.5-flash",
            url="https://us-central1-aiplatform.googleapis.com/v1/projects/my-project/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent",
            project_id="my-project",
            location="us-central1",
        )

        interruption = interruption_from_provider_error(error, provider_name=error.provider_name)
        self.assertEqual("vertexai_quota_or_rate_limit", error.kind)
        self.assertTrue(interruption.retryable)
        self.assertIn("Vertex AI quota or rate limit reached", error.user_message)

    async def test_vertexai_generate_content_uses_bearer_token_and_yields_text(self):
        provider = VertexAIProvider(
            "vertexai/gemini-2.5-flash",
            settings={"vertexai": {"project_id": "my-project", "location": "us-central1"}},
        )

        fake_client = _FakeAsyncClient()
        with patch.object(provider, "_get_access_token", return_value="token-123"):
            with patch("modules.providers.vertexai.httpx.AsyncClient", return_value=fake_client):
                chunks = []
                async for chunk in provider.get_streaming_response("hello", [{"role": "user", "content": "hi"}]):
                    chunks.append(chunk)

        self.assertEqual(["ok"], chunks)
        self.assertEqual(1, len(fake_client.post_calls))
        call = fake_client.post_calls[0]
        self.assertEqual(
            "Bearer token-123",
            call["headers"].get("Authorization"),
        )
        self.assertEqual(
            "https://us-central1-aiplatform.googleapis.com/v1/projects/my-project/locations/us-central1/publishers/google/models/gemini-2.5-flash:generateContent",
            call["url"],
        )
        self.assertEqual("hello", call["json"]["contents"][-1]["parts"][0]["text"])
        self.assertIn("systemInstruction", call["json"])


if __name__ == "__main__":
    unittest.main()
