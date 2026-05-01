"""Lock the public type surface against codegen renames.

The generated/ subtree may rename internal classes between
openapi-python-client versions. notifier_client.types is the stable public
import path; this test breaks at PR time (not at consumer-pin time) if a
public name disappears.
"""

import notifier_client
from notifier_client.types import (
    AssembleResponse,
    ChannelOut,
    ChannelTestResponse,
    DispatchAttemptOut,
    DispatchAttemptOutStatus,
    DispatchOut,
    DispatchOutStatus,
    PluginDetail,
    PluginListItem,
    PreviewResponse,
    TemplateOut,
    TemplatePreviewResponse,
)


def test_public_type_names_importable():
    # Each must be a class, not a module
    for cls in (AssembleResponse, ChannelOut, ChannelTestResponse, DispatchAttemptOut,
                DispatchOut, PluginDetail, PluginListItem, PreviewResponse, TemplateOut,
                TemplatePreviewResponse):
        assert isinstance(cls, type)
        assert hasattr(cls, "from_dict")
        assert hasattr(cls, "to_dict")


def test_dispatch_status_enums_importable():
    assert DispatchOutStatus.SUCCEEDED == "succeeded"
    assert DispatchOutStatus.PARTIAL == "partial"
    assert DispatchOutStatus.FAILED == "failed"
    assert DispatchAttemptOutStatus.SUCCEEDED == "succeeded"
    assert DispatchAttemptOutStatus.FAILED == "failed"


def test_channel_out_has_expected_fields():
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
    out = DispatchOut.from_dict({
        "id": "01H", "tenant_id": "t1", "template_id": None,
        "idempotency_key": None, "rendered_title": "T", "rendered_body": "B",
        "status": "succeeded", "metadata": {}, "attempts": [],
        "created_at": "2026-04-30T00:00:00Z",
    })
    assert out.id == "01H"
    assert out.status == DispatchOutStatus.SUCCEEDED
    assert out.status == "succeeded"  # str(Enum) equality preserved
    assert out.attempts == []


def test_top_level_init_re_exports_types():
    """Common types should also be available as `from notifier_client import ...`."""
    assert hasattr(notifier_client, "ChannelOut")
    assert hasattr(notifier_client, "TemplateOut")
    assert hasattr(notifier_client, "DispatchAttemptOut")
    assert hasattr(notifier_client, "DispatchAttemptOutStatus")
    assert hasattr(notifier_client, "DispatchOut")
    assert hasattr(notifier_client, "DispatchOutStatus")
    assert hasattr(notifier_client, "AssembleResponse")
    assert hasattr(notifier_client, "ChannelTestResponse")
    assert hasattr(notifier_client, "PluginDetail")
    assert hasattr(notifier_client, "PluginListItem")
    assert hasattr(notifier_client, "PreviewResponse")
    assert hasattr(notifier_client, "TemplatePreviewResponse")
