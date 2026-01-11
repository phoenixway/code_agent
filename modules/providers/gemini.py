import os
import json
import httpx
from modules.defaults import DEFAULT_SYSTEM_PROMPT
from .base import BaseChatProvider, ProviderAPIError

class GeminiProvider(BaseChatProvider):
    """Provider for Google Gemini API via REST."""
    
    def __init__(self, model_name):
        super().__init__(model_name)
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError(f"Missing API key for Gemini. Please set the GEMINI_API_KEY environment variable.")
        self.url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent?key={self.api_key}"

    async def get_streaming_response(self, prompt, history):
        # Gemini has a specific format for contents
        contents = []
        for m in history:
            # Gemini expects "model" role for assistant messages
            role = "user" if m["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})
        
        if prompt:
            contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "system_instruction": {"parts": [{"text": DEFAULT_SYSTEM_PROMPT}]}
        }
        
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("POST", self.url, json=payload) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise ProviderAPIError(f"Gemini API Error {response.status_code}: {error_text.decode('utf-8')}")

                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            line_text = line[6:]
                            try:
                                data = json.loads(line_text)
                                # Extract content from deeply nested structure
                                if 'candidates' in data and data['candidates']:
                                    parts = data['candidates'][0]['content']['parts']
                                    if parts:
                                        yield parts[0]['text']
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
        except Exception as e:
            raise ProviderAPIError(f"Gemini Stream Error: {str(e)}")
