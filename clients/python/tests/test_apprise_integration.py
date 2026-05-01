"""Round-trip: apprise.list_plugins → get_plugin("jsons") → assemble.

Exercises the typed apprise sub-client surface against a real notifier process.
Asserts "jsons" schema is present (Apprise stdlib always ships it — the JSON
plugin's primary scheme is the TLS variant) and that the assembled URL contains
the supplied host token.
"""

import pytest

from notifier_client import AssembleResponse, NotifierClient, PluginDetail, PluginListItem

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_apprise_round_trip(notifier_url, tenant_credentials):
    _, api_key = tenant_credentials
    async with NotifierClient(base_url=notifier_url, api_key=api_key) as c:
        plugins = await c.apprise.list_plugins()
        assert plugins
        assert all(isinstance(p, PluginListItem) for p in plugins)

        schemas = {p.plugin_schema for p in plugins}
        assert "jsons" in schemas, "Apprise stdlib should expose jsons:// schema"

        detail = await c.apprise.get_plugin("jsons")
        assert isinstance(detail, PluginDetail)
        assert detail.plugin_schema == "jsons"

        # Only verifies URL assembly (string round-trip), not deliverability.
        # jsons:// is HTTPS-bound; localhost without a cert won't resolve, but
        # /assemble does no network probing — it just returns the URL string.
        assembled = await c.apprise.assemble("jsons", tokens={"host": "localhost"})
        assert isinstance(assembled, AssembleResponse)
        assert assembled.apprise_url.startswith("jsons://")
        assert "localhost" in assembled.apprise_url
