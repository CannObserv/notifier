"""Public type surface for notifier-client.

Stable import path for the typed response/request models. Backed by classes
in ``notifier_client.generated``, which can be renamed between codegen
versions; this module insulates consumers from that churn.

Add a name here only when an endpoint method returns or accepts the type.
The surface test (``tests/test_types_surface.py``) guards every name listed
in ``__all__``.

Regen workflow: if `clients/python/scripts/regen.sh` produces a build where
this file fails to import, the codegen renamed one of the underlying classes.
Find the new name in `clients/python/src/notifier_client/generated/models/`
(grep for the docstring) and update the matching import line below.
"""

from notifier_client.generated.models.assemble_response import AssembleResponse
from notifier_client.generated.models.channel_out import ChannelOut
from notifier_client.generated.models.channel_test_response import ChannelTestResponse
from notifier_client.generated.models.dispatch_attempt_out import DispatchAttemptOut
from notifier_client.generated.models.dispatch_attempt_out_status import DispatchAttemptOutStatus
from notifier_client.generated.models.dispatch_out import DispatchOut
from notifier_client.generated.models.dispatch_out_status import DispatchOutStatus
from notifier_client.generated.models.plugin_detail import PluginDetail
from notifier_client.generated.models.plugin_list_item import PluginListItem
from notifier_client.generated.models.preview_response import PreviewResponse
from notifier_client.generated.models.template_out import TemplateOut
from notifier_client.generated.models.template_preview_response import TemplatePreviewResponse

__all__ = [
    "AssembleResponse",
    "ChannelOut",
    "ChannelTestResponse",
    "DispatchAttemptOut",
    "DispatchAttemptOutStatus",
    "DispatchOut",
    "DispatchOutStatus",
    "PluginDetail",
    "PluginListItem",
    "PreviewResponse",
    "TemplateOut",
    "TemplatePreviewResponse",
]
