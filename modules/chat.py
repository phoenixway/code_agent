import logging
from modules.providers.base import ProviderAPIError
from modules.providers.openai import OpenAICompatibleProvider
from modules.providers.ollama import OllamaProvider
from modules.providers.gemini import GeminiProvider

log = logging.getLogger(__name__)

# A dictionary to map model name keywords to provider classes and their arguments
# This configuration logic is kept here to act as a Registry/Factory
PROVIDERS = {
    "gemini": (GeminiProvider, []),
    "deepseek": (OpenAICompatibleProvider, ["https://api.deepseek.com", "DEEPSEEK_API_KEY"]),
    "gpt": (OpenAICompatibleProvider, ["https://api.openai.com/v1", "OPENAI_API_KEY"]),
    "ollama": (OllamaProvider, []),
    "qwen": (OllamaProvider, []),
    "llama": (OllamaProvider, []), # Added llama generic support
}

def get_chat_provider(model_name):
    """Factory function to get the appropriate chat provider."""
    m_lower = model_name.lower()
    
    for keyword, (provider_class, args) in PROVIDERS.items():
        if keyword in m_lower:
            try:
                # Handle specific logic for Ollama models names (e.g. ollama/qwen:4b -> qwen:4b)
                if provider_class == OllamaProvider:
                    clean_name = model_name.split('/')[-1] if '/' in model_name else model_name
                    return provider_class(clean_name)
                
                # Standard instantiation
                return provider_class(model_name, *args)
            except ValueError as e:
                log.warning(f"Error initializing chat provider for {model_name}: {e}")
                return None
            
    # Default fallback provider
    try:
        return GeminiProvider("gemini-1.5-pro")
    except ValueError as e:
        log.warning(f"Error initializing default Gemini chat provider: {e}")
        return None
