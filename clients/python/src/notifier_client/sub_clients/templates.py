"""``client.templates.*`` — template CRUD + preview."""

from __future__ import annotations

from typing import TYPE_CHECKING

from notifier_client.errors import error_from_response
from notifier_client.generated.models.template_create import TemplateCreate
from notifier_client.generated.models.template_create_sample_variables_type_0 import (
    TemplateCreateSampleVariablesType0,
)
from notifier_client.generated.models.template_create_variables_schema_type_0 import (
    TemplateCreateVariablesSchemaType0,
)
from notifier_client.generated.models.template_preview_request import TemplatePreviewRequest
from notifier_client.generated.models.template_preview_request_variables_type_0 import (
    TemplatePreviewRequestVariablesType0,
)
from notifier_client.generated.models.template_update import TemplateUpdate
from notifier_client.generated.models.template_update_sample_variables_type_0 import (
    TemplateUpdateSampleVariablesType0,
)
from notifier_client.generated.models.template_update_variables_schema_type_0 import (
    TemplateUpdateVariablesSchemaType0,
)
from notifier_client.generated.types import UNSET, Unset
from notifier_client.types import TemplateOut, TemplatePreviewResponse

if TYPE_CHECKING:
    from notifier_client.client import NotifierClient


class TemplatesAPI:
    """Template CRUD + preview under ``/api/v1/templates``."""

    def __init__(self, client: NotifierClient) -> None:
        self._client = client

    async def list(self) -> list[TemplateOut]:
        """GET /api/v1/templates — all templates owned by the calling tenant."""
        response = await self._client._http.request("GET", "/api/v1/templates")
        if response.status_code >= 400:
            raise error_from_response(response)
        return [TemplateOut.from_dict(item) for item in response.json()]

    async def create(
        self,
        *,
        name: str,
        title_template: str,
        body_template: str,
        variables_schema: dict | None | Unset = UNSET,
        sample_variables: dict | None | Unset = UNSET,
        tags: list[str] | None | Unset = UNSET,
    ) -> TemplateOut:
        """POST /api/v1/templates — create a new template."""
        vs = (
            TemplateCreateVariablesSchemaType0.from_dict(variables_schema)
            if isinstance(variables_schema, dict)
            else variables_schema
        )
        sv = (
            TemplateCreateSampleVariablesType0.from_dict(sample_variables)
            if isinstance(sample_variables, dict)
            else sample_variables
        )
        body = TemplateCreate(
            name=name,
            title_template=title_template,
            body_template=body_template,
            variables_schema=vs,
            sample_variables=sv,
            tags=tags,
        ).to_dict()
        return await self._client._typed_request(
            "POST", "/api/v1/templates", model=TemplateOut, json=body, retry_safe=False,
        )

    async def get(self, template_id: str) -> TemplateOut:
        """GET /api/v1/templates/{id}."""
        return await self._client._typed_request(
            "GET", f"/api/v1/templates/{template_id}",
            model=TemplateOut, retry_safe=True,
        )

    async def update(
        self,
        template_id: str,
        *,
        name: str | Unset = UNSET,
        title_template: str | Unset = UNSET,
        body_template: str | Unset = UNSET,
        variables_schema: dict | None | Unset = UNSET,
        sample_variables: dict | None | Unset = UNSET,
        tags: list[str] | None | Unset = UNSET,
    ) -> TemplateOut:
        """PATCH /api/v1/templates/{id} — partial update; only supplied fields are sent."""
        vs = (
            TemplateUpdateVariablesSchemaType0.from_dict(variables_schema)
            if isinstance(variables_schema, dict)
            else variables_schema
        )
        sv = (
            TemplateUpdateSampleVariablesType0.from_dict(sample_variables)
            if isinstance(sample_variables, dict)
            else sample_variables
        )
        body = TemplateUpdate(
            name=name,
            title_template=title_template,
            body_template=body_template,
            variables_schema=vs,
            sample_variables=sv,
            tags=tags,
        ).to_dict()
        return await self._client._typed_request(
            "PATCH", f"/api/v1/templates/{template_id}",
            model=TemplateOut, json=body, retry_safe=False,
        )

    async def delete(self, template_id: str) -> None:
        """DELETE /api/v1/templates/{id}; 204 on success.

        Not auto-retried — DELETE is non-idempotent at the resource level
        (a 5xx may have already deleted the row; retrying would 404).
        """
        response = await self._client._http.request(
            "DELETE", f"/api/v1/templates/{template_id}",
            extensions={"notifier_no_retry": True},
        )
        if response.status_code >= 400:
            raise error_from_response(response)

    async def preview(
        self, template_id: str, *, variables: dict | None = None,
    ) -> TemplatePreviewResponse:
        """POST /api/v1/templates/{id}/preview — render with supplied or stored sample variables."""
        vars_field: TemplatePreviewRequestVariablesType0 | None | Unset
        if variables is not None:
            vars_field = TemplatePreviewRequestVariablesType0.from_dict(variables)
        else:
            vars_field = UNSET
        body = TemplatePreviewRequest(variables=vars_field).to_dict()
        return await self._client._typed_request(
            "POST", f"/api/v1/templates/{template_id}/preview",
            model=TemplatePreviewResponse, json=body, retry_safe=False,
        )
