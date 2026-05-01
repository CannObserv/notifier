"""Round-trip: apprise.list_plugins → get_plugin → assemble.

Exercises the typed apprise sub-client surface against a real notifier process.
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

        # Pick a known schema if available; otherwise use the first listed.
        schemas = {p.plugin_schema for p in plugins}
        target = "json" if "json" in schemas else next(iter(schemas))

        detail = await c.apprise.get_plugin(target)
        assert isinstance(detail, PluginDetail)
        assert detail.plugin_schema == target

        # Assemble may fail with 422 if required tokens are missing; only
        # check assemble for "json" which accepts a bare host token.
        if target == "json":
            assembled = await c.apprise.assemble(target, tokens={"host": "localhost"})
            assert isinstance(assembled, AssembleResponse)
            assert assembled.apprise_url.startswith("json://")
