"""Tests for Batch B: Provider readiness, capability integrity, and TurnOptions routing.

Verifies fixes for Audit issues:
- #20: Provider Registry treats fallback model catalogs as available
- #21: Cloud model catalogs are hardcoded and can become stale (live discovery & fallback distinction)
- #22: Google provider claims tool support but tool calls are not converted
- #23: Anthropic provider's JSON mode API contract
- #24: Provider model selection ignores user model selection (model_override & forced_tier)
- #25: TurnOptions.task_type appears unused
- #26: Provider registry fallback chain can select an unready provider
"""

from unittest.mock import MagicMock, patch
import pytest

from core.config import ExecutionMode
from core.orchestrator import Orchestrator, TurnOptions
from core.providers.anthropic import AnthropicProvider
from core.providers.base import (
    Capability,
    CatalogSource,
    ChatMessage,
    ChatOptions,
    ChatResponse,
    LLMProvider,
    ModelInfo,
    SpeedTier,
)
from core.providers.google import GoogleProvider
from core.providers.openai_compat import OpenAICompatibleProvider
from core.providers.registry import ProviderRegistry
from core.settings import SettingsStore


class TestProviderReadinessAndAvailability:
    """Audit #20 & #26: Unready providers with fallback catalogs must not be considered available."""

    def test_empty_key_providers_are_not_ready_or_available(self):
        reg = ProviderRegistry()
        google = GoogleProvider(api_key="")
        anthropic = AnthropicProvider(api_key="")
        openai = OpenAICompatibleProvider(api_key="", base_url="https://api.openai.com/v1")

        reg.register(google)
        reg.register(anthropic)
        reg.register(openai)

        # Fallback models exist in catalog
        assert len(google.list_models()) > 0
        assert len(anthropic.list_models()) > 0
        assert len(openai.list_models()) > 0

        # But providers are NOT authenticated, NOT ready, and NOT available
        assert not google.is_authenticated
        assert not google.is_ready()
        assert not reg._check_provider_available(google)

        assert not anthropic.is_authenticated
        assert not anthropic.is_ready()
        assert not reg._check_provider_available(anthropic)

        assert not openai.is_authenticated
        assert not openai.is_ready()
        assert not reg._check_provider_available(openai)

    def test_fallback_chain_strictly_excludes_unready_cloud_providers(self, monkeypatch, tmp_path):
        settings = SettingsStore(tmp_path / "settings.json")
        settings.set("privacy_mode", "cloud_allowed")
        monkeypatch.setattr("core.settings.get_settings", lambda: settings)

        reg = ProviderRegistry()
        # Providers with empty keys
        google = GoogleProvider(api_key="")
        anthropic = AnthropicProvider(api_key="")
        openai = OpenAICompatibleProvider(api_key="", base_url="https://api.openai.com/v1")

        reg.register(google)
        reg.register(anthropic)
        reg.register(openai)

        # Even though cloud_allowed, unready providers must not enter fallback chain
        chain = reg.get_fallback_chain(SpeedTier.FAST)
        assert len(chain) == 0

        chain_medium = reg.get_fallback_chain(SpeedTier.MEDIUM)
        assert len(chain_medium) == 0

    def test_catalog_source_marked_live_vs_fallback(self):
        # Without network/keys, catalog source is FALLBACK
        google = GoogleProvider(api_key="")
        models = google.list_models()
        assert google.catalog_source == CatalogSource.FALLBACK
        for m in models:
            assert m.catalog_source == CatalogSource.FALLBACK

        # Mock successful API call for Google
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "models/gemini-2.0-flash", "displayName": "Gemini 2.0 Flash"},
            ]
        }

        with patch("httpx.get", return_value=mock_response):
            live_google = GoogleProvider(api_key="valid-test-key")
            live_models = live_google.list_models()
            assert live_google.catalog_source == CatalogSource.LIVE
            assert live_google.is_authenticated
            assert live_google.is_reachable
            assert live_google.is_ready()
            assert live_models[0].catalog_source == CatalogSource.LIVE


class TestProviderCapabilitiesAndContracts:
    """Audit #22 & #23: Correct capabilities and API contracts."""

    def test_google_provider_does_not_claim_unsupported_tools(self):
        google = GoogleProvider(api_key="dummy")
        assert google.supports_tools() is False

        for model in google.list_models():
            assert model.supports_tools is False
            assert Capability.TOOLS not in model.capabilities

    def test_anthropic_json_mode_contract_and_capabilities(self, monkeypatch, tmp_path):
        settings = SettingsStore(tmp_path / "settings.json")
        settings.set("privacy_mode", "cloud_allowed")
        monkeypatch.setattr("core.settings.get_settings", lambda: settings)

        anthropic = AnthropicProvider(api_key="dummy-key")
        assert anthropic.supports_json() is False
        for model in anthropic.list_models():
            assert model.supports_json is False

        # Verify chat payload does NOT send response_format={"type": "json_object"}
        captured_payload = {}

        def mock_post(url, headers=None, json=None, timeout=None):
            nonlocal captured_payload
            captured_payload = json
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "content": [{"type": "text", "text": '{"result": "ok"}'}],
                "usage": {"input_tokens": 10, "output_tokens": 10},
                "model": "claude-3-5-sonnet-20241022",
                "stop_reason": "stop",
            }
            return mock_resp

        with patch("httpx.post", side_effect=mock_post):
            anthropic.chat(
                messages=[ChatMessage(role="user", content="Return JSON")],
                options=ChatOptions(json_mode=True),
            )

        assert "response_format" not in captured_payload
        assert "Respond strictly with valid JSON" in captured_payload.get("system", "")


class TestOrchestratorTurnOptionsRouting:
    """Audit #24 & #25: Observable behavior for task_type, model_override, and forced_tier."""

    def test_turn_options_task_type_direct_agent_dispatch(self, monkeypatch):
        monkeypatch.setattr("core.providers.local.LocalProvider.chat", lambda *args, **kwargs: "Mock answer")
        orch = Orchestrator()
        # Submit a generic message with task_type="tutor"
        # Normally "tell me something" wouldn't match Tutor triggers
        res = orch.submit("tell me something", options=TurnOptions(task_type="tutor"))
        assert res.agent_name == "Tutor"
        assert "task_type:tutor" in res.routing_reason

        # Test task_type="code"
        res_code = orch.submit("look at this text", options=TurnOptions(task_type="code"))
        assert res_code.agent_name == "Code Reviewer"
        assert "task_type:code" in res_code.routing_reason

    def test_turn_options_model_override_privacy_mode_enforcement(self, monkeypatch, tmp_path):
        settings = SettingsStore(tmp_path / "settings.json")
        settings.set("privacy_mode", "local_only")
        monkeypatch.setattr("core.settings.get_settings", lambda: settings)

        orch = Orchestrator()
        # Requesting a cloud model override while in LOCAL_ONLY mode must be blocked cleanly
        res = orch.submit("hello", options=TurnOptions(model_override="openai/gpt-4o"))
        assert "Operation blocked by privacy policy" in res.text
        assert "PermissionError" in res.routing_reason

    def test_turn_options_model_override_cloud_dispatch(self, monkeypatch, tmp_path):
        settings = SettingsStore(tmp_path / "settings.json")
        settings.set("privacy_mode", "cloud_allowed")
        monkeypatch.setattr("core.settings.get_settings", lambda: settings)

        # Mock custom provider
        mock_provider = MagicMock(spec=LLMProvider)
        mock_provider.name = "CustomMock"
        mock_provider.key = "custom"
        mock_provider.is_ready.return_value = True
        mock_provider.list_models.return_value = [
            ModelInfo(id="custom-fast", name="Custom Fast", provider="custom", speed_tier=SpeedTier.FAST)
        ]
        mock_provider.chat.return_value = ChatResponse(
            text="Mock cloud answer",
            model_id="custom-fast",
            provider="custom",
        )

        reg = ProviderRegistry()
        reg.register(mock_provider)
        monkeypatch.setattr("core.providers.registry.get_registry", lambda: reg)

        orch = Orchestrator()
        res = orch.submit("general non-agent query", options=TurnOptions(model_override="custom/custom-fast"))
        assert res.text == "Mock cloud answer"
        assert res.model_used == "custom-fast"
        assert "model_override:custom/custom-fast" in res.routing_reason
        mock_provider.chat.assert_called_once()

    def test_turn_options_forced_tier_routing(self, monkeypatch, tmp_path):
        settings = SettingsStore(tmp_path / "settings.json")
        settings.set("privacy_mode", "cloud_allowed")
        monkeypatch.setattr("core.settings.get_settings", lambda: settings)

        mock_fast_provider = MagicMock(spec=LLMProvider)
        mock_fast_provider.name = "FastCloud"
        mock_fast_provider.key = "fastcloud"
        mock_fast_provider.is_ready.return_value = True
        mock_fast_provider.list_models.return_value = [
            ModelInfo(id="fast-1", name="Fast 1", provider="fastcloud", speed_tier=SpeedTier.FAST)
        ]
        mock_fast_provider.chat.return_value = ChatResponse(
            text="Fast response",
            model_id="fast-1",
            provider="fastcloud",
        )

        reg = ProviderRegistry()
        reg.register(mock_fast_provider)
        monkeypatch.setattr("core.providers.registry.get_registry", lambda: reg)

        orch = Orchestrator()
        res = orch.submit("non-agent query", options=TurnOptions(forced_tier="fast"))
        assert res.text == "Fast response"
        assert res.model_used == "fast-1"
        assert "forced_tier:fast:fastcloud/fast-1" in res.routing_reason
