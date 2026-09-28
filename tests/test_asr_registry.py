from agent_videonote.asr.capabilities import AsrCapability
from agent_videonote.asr.providers.registry import ProviderRegistry
from agent_videonote.core.errors import CapabilityError


class FakeProvider:
    provider_id = "fake"
    capabilities = frozenset({AsrCapability.SHORT_AUDIO})

    def transcribe(self, request):
        raise AssertionError("not used in this test")

    def close(self) -> None:
        pass


def test_registry_checks_capabilities() -> None:
    registry = ProviderRegistry()
    registry.register(FakeProvider())

    assert registry.get("fake", {AsrCapability.SHORT_AUDIO}).provider_id == "fake"

    try:
        registry.get("fake", {AsrCapability.LONG_AUDIO})
    except CapabilityError:
        pass
    else:
        raise AssertionError("missing capability should fail")
