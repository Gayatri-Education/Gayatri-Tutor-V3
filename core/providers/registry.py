"""Gayatri AI — Provider registry + unified model catalog.

Manages all LLM providers, fetches their models, and provides a single
unified view of every available model across all configured providers.
"""

from __future__ import annotations

import logging

from core.providers.base import Capability, LLMProvider, ModelInfo, SpeedTier

logger = logging.getLogger("gayatri.providers.registry")


class ProviderRegistry:
    """Registry of LLM providers with unified model catalog.

    Usage:
        registry = ProviderRegistry()
        registry.register(OpenAIProvider(api_key=...))
        registry.register(AnthropicProvider(api_key=...))

        # Get all models across all providers
        all_models = registry.get_all_models()

        # Get models for a specific provider
        openai_models = registry.get_models("openai")
    """

    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider) -> None:
        """Register a provider. Idempotent — safe to call multiple times."""
        self._providers[provider.key] = provider
        logger.info(f"Provider registered: {provider.name} ({provider.key})")

    def unregister(self, provider_key: str) -> None:
        """Remove a provider."""
        self._providers.pop(provider_key, None)
        logger.info(f"Provider unregistered: {provider_key}")

    def get(self, provider_key: str) -> LLMProvider | None:
        """Get a provider by key."""
        return self._providers.get(provider_key)

    def list_providers(self) -> list[dict]:
        """List all registered providers with their status."""
        result = []
        for key, provider in self._providers.items():
            result.append({
                "key": key,
                "name": provider.name,
                "available": self._check_provider_available(provider),
            })
        return result

    def _check_provider_available(self, provider: LLMProvider) -> bool:
        """Quick check if a provider is reachable."""
        try:
            if provider.key == "local":
                from core.providers.local import LocalProvider
                return LocalProvider.is_available()
            # Cloud providers: check if they have any models
            models = provider.list_models()
            return len(models) > 0
        except Exception:
            return False

    def get_models(self, provider_key: str) -> list[ModelInfo]:
        """Get models for a specific provider."""
        provider = self._providers.get(provider_key)
        if provider is None:
            return []
        try:
            return provider.list_models()
        except Exception as exc:
            logger.error(f"Failed to fetch models for {provider_key}: {exc}")
            return []

    def get_all_models(self) -> list[ModelInfo]:
        """Get all models from all providers, sorted by provider then name."""
        all_models: list[ModelInfo] = []
        for provider in self._providers.values():
            try:
                models = provider.list_models()
                all_models.extend(models)
            except Exception as exc:
                logger.error(f"Failed to fetch models from {provider.name}: {exc}")
        all_models.sort(key=lambda m: (m.provider, m.id))
        return all_models

    def get_models_by_speed(self, speed_tier: SpeedTier) -> list[ModelInfo]:
        """Get all models matching a speed tier."""
        return [m for m in self.get_all_models() if m.speed_tier == speed_tier]

    def get_models_by_capability(self, capability: Capability) -> list[ModelInfo]:
        """Get all models supporting a specific capability."""
        return [m for m in self.get_all_models() if capability in m.capabilities]

    def get_fallback_chain(self, preferred_tier: SpeedTier) -> list[tuple[LLMProvider, ModelInfo]]:
        """Get a fallback chain of (provider, model) pairs for a tier.

        Order: preferred_tier → medium → slow.
        Returns available providers only.
        """
        chain: list[tuple[LLMProvider, ModelInfo]] = []
        seen = set()

        tier_order = [preferred_tier, SpeedTier.MEDIUM, SpeedTier.SLOW]

        for tier in tier_order:
            for provider in self._providers.values():
                if provider.key in seen:
                    continue
                try:
                    models = provider.list_models()
                    matching = [m for m in models if m.speed_tier == tier]
                    if matching:
                        chain.append((provider, matching[0]))
                        seen.add(provider.key)
                except Exception:
                    continue

        return chain

    def to_catalog_dict(self) -> list[dict]:
        """Return the full model catalog as a list of dicts (for JSON serialization)."""
        return [m.to_dict() for m in self.get_all_models()]


# Global registry (lazy-initialized)
_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Get the global provider registry."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
