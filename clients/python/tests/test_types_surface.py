"""Lock the public type surface against codegen renames.

The generated/ subtree may rename internal classes between
openapi-python-client versions. notifier_client.types is the stable public
import path; this test breaks at PR time (not at consumer-pin time) if a
public name disappears.
"""

def test_public_type_names_importable():
    from notifier_client.types import (
        AssembleResponse,
        ChannelOut,
        ChannelTestResponse,
        DispatchOut,
        PluginDetail,
        PluginListItem,
        PreviewResponse,
        TemplateOut,
        TemplatePreviewResponse,
    )
    # Each must be a class, not a module
    for cls in (AssembleResponse, ChannelOut, ChannelTestResponse, DispatchOut,
                PluginDetail, PluginListItem, PreviewResponse, TemplateOut,
                TemplatePreviewResponse):
        assert isinstance(cls, type)
        assert hasattr(cls, "from_dict")
        assert hasattr(cls, "to_dict")


def test_channel_out_has_expected_fields():
    from notifier_client.types import ChannelOut
    out = ChannelOut.from_dict({
        "id": "01H", "tenant_id": "t1", "name": "n",
        "apprise_url_masked": "m", "channel_hint": None,
        "created_at": "2026-04-30T00:00:00Z",
        "updated_at": "2026-04-30T00:00:00Z",
    })
    assert out.id == "01H"
    assert out.tenant_id == "t1"
    assert out.name == "n"


def test_dispatch_out_has_expected_fields():
    from notifier_client.types import DispatchOut
    out = DispatchOut.from_dict({
        "id": "01H", "tenant_id": "t1", "template_id": None,
        "idempotency_key": None, "rendered_title": "T", "rendered_body": "B",
        "status": "succeeded", "metadata": {}, "attempts": [],
        "created_at": "2026-04-30T00:00:00Z",
    })
    assert out.id == "01H"
    assert out.status == "succeeded"
    assert out.attempts == []


def test_top_level_init_re_exports_types():
    """Common types should also be available as `from notifier_client import ...`."""
    import notifier_client
    assert hasattr(notifier_client, "ChannelOut")
    assert hasattr(notifier_client, "TemplateOut")
    assert hasattr(notifier_client, "DispatchOut")
