"""Route-level tests for the /api/v1/templates write paths.

Template coverage was scattered through `tests/test_smoke.py`, which reached
CRUD and preview and never touched what the routes accept. `variables_schema`
was stored as an opaque dict (#28): a consumer could POST a broken JSON Schema,
get a 201, and discover it only at dispatch time — on the request that
mattered, once per dispatch.
"""

import secrets

import pytest

from src.core.models.template import Template

HEADER = "X-API-Key"

INVALID_SCHEMA = {"type": "not-a-json-schema-type"}
VALID_SCHEMA = {"type": "object", "properties": {"n": {"type": "integer"}}}
STRICT_SCHEMA = {
    "type": "object",
    "properties": {"n": {"type": "integer"}},
    "required": ["n"],
}
EXTERNAL_REF_SCHEMA = {"$ref": "https://example.com/schema.json"}
DANGLING_REF_SCHEMA = {"type": "object", "properties": {"n": {"$ref": "#/$defs/missing"}}}


@pytest.fixture
def headers(api_key) -> dict[str, str]:
    raw_key, _ = api_key
    return {HEADER: raw_key}


def _payload(**overrides) -> dict:
    body = {
        "name": f"t-{secrets.token_hex(4)}",
        "title_template": "Hello {{ name }}",
        "body_template": "Body for {{ name }}",
    }
    body.update(overrides)
    return body


async def _create(client, headers, **overrides):
    return await client.post("/api/v1/templates", headers=headers, json=_payload(**overrides))


def _schema_error_locs(response) -> list[list]:
    return [e["loc"] for e in response.json()["detail"]]


class TestCreateSchemaValidation:
    """POST /templates rejects a malformed `variables_schema` on write."""

    async def test_invalid_schema_is_rejected(self, client, headers):
        response = await _create(client, headers, variables_schema=INVALID_SCHEMA)
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert any("not a valid JSON Schema" in e["msg"] for e in detail), detail

    async def test_the_rejection_names_the_offending_field(self, client, headers):
        response = await _create(client, headers, variables_schema=INVALID_SCHEMA)
        assert ["body", "variables_schema"] in _schema_error_locs(response)

    async def test_a_structurally_broken_schema_is_rejected(self, client, headers):
        """Not just a bad `type` — any metaschema violation, e.g. `required`
        as a string where the spec demands an array."""
        response = await _create(
            client, headers, variables_schema={"type": "object", "required": "n"}
        )
        assert response.status_code == 422, response.text

    async def test_a_valid_schema_is_accepted(self, client, headers):
        response = await _create(client, headers, variables_schema=VALID_SCHEMA)
        assert response.status_code == 201, response.text
        assert response.json()["variables_schema"] == VALID_SCHEMA

    async def test_an_empty_schema_is_accepted(self, client, headers):
        """`{}` is a valid JSON Schema that constrains nothing, and
        `validate_variables` already treats it as "no validation"."""
        response = await _create(client, headers, variables_schema={})
        assert response.status_code == 201, response.text

    async def test_an_absent_schema_is_accepted(self, client, headers):
        response = await _create(client, headers)
        assert response.status_code == 201, response.text
        assert response.json()["variables_schema"] is None

    async def test_an_explicit_null_schema_is_accepted(self, client, headers):
        response = await _create(client, headers, variables_schema=None)
        assert response.status_code == 201, response.text


class TestUpdateSchemaValidation:
    """PATCH /templates/{id} enforces the same contract as POST."""

    @pytest.fixture
    async def template_id(self, client, headers) -> str:
        response = await _create(client, headers, variables_schema=VALID_SCHEMA)
        assert response.status_code == 201, response.text
        return response.json()["id"]

    async def test_invalid_schema_is_rejected(self, client, headers, template_id):
        response = await client.patch(
            f"/api/v1/templates/{template_id}",
            headers=headers,
            json={"variables_schema": INVALID_SCHEMA},
        )
        assert response.status_code == 422, response.text
        assert ["body", "variables_schema"] in _schema_error_locs(response)

    async def test_a_rejected_patch_leaves_the_stored_schema_intact(
        self, client, headers, template_id
    ):
        await client.patch(
            f"/api/v1/templates/{template_id}",
            headers=headers,
            json={"variables_schema": INVALID_SCHEMA},
        )
        response = await client.get(f"/api/v1/templates/{template_id}", headers=headers)
        assert response.json()["variables_schema"] == VALID_SCHEMA

    async def test_a_valid_schema_replaces_the_stored_one(self, client, headers, template_id):
        replacement = {"type": "object", "required": ["n"]}
        response = await client.patch(
            f"/api/v1/templates/{template_id}",
            headers=headers,
            json={"variables_schema": replacement},
        )
        assert response.status_code == 200, response.text
        assert response.json()["variables_schema"] == replacement

    async def test_an_explicit_null_clears_the_schema(self, client, headers, template_id):
        """The guard must not turn "remove this schema" into a 422 — a bare
        `check_schema(None)` raises, so the falsy short-circuit has to stay."""
        response = await client.patch(
            f"/api/v1/templates/{template_id}",
            headers=headers,
            json={"variables_schema": None},
        )
        assert response.status_code == 200, response.text
        assert response.json()["variables_schema"] is None

    async def test_an_untouched_schema_survives_an_unrelated_patch(
        self, client, headers, template_id
    ):
        response = await client.patch(
            f"/api/v1/templates/{template_id}", headers=headers, json={"title_template": "new"}
        )
        assert response.status_code == 200, response.text
        assert response.json()["variables_schema"] == VALID_SCHEMA


class TestSampleVariablesCrossValidation:
    """Templates must not carry a `sample_variables` bag their own
    `variables_schema` rejects (#31).

    POST checks the request pair; PATCH checks the *merged* result — either
    field can arrive alone, and the one that stayed home is read from the
    stored row. Route-level, so the error is dispatch's `{section, path,
    message}` dict, not Pydantic's `loc` list.
    """

    async def test_post_rejects_a_sample_the_schema_refuses(self, client, headers):
        response = await _create(
            client,
            headers,
            variables_schema=STRICT_SCHEMA,
            sample_variables={"n": "not-an-integer"},
        )
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert detail["section"] == "sample_variables"
        assert detail["path"] == "n"

    async def test_post_accepts_a_sample_the_schema_allows(self, client, headers):
        response = await _create(
            client, headers, variables_schema=STRICT_SCHEMA, sample_variables={"n": 3}
        )
        assert response.status_code == 201, response.text

    async def test_post_rejects_an_empty_sample_when_the_schema_requires_a_key(
        self, client, headers
    ):
        """`{}` genuinely violates `required`, and preview's `or`-chain treats
        an empty sample as absent anyway — refusing it loses nothing."""
        response = await _create(
            client, headers, variables_schema=STRICT_SCHEMA, sample_variables={}
        )
        assert response.status_code == 422, response.text

    async def test_post_accepts_a_sample_with_no_schema_to_judge_it(self, client, headers):
        response = await _create(client, headers, sample_variables={"n": "anything"})
        assert response.status_code == 201, response.text

    @pytest.fixture
    async def strict_template_id(self, client, headers) -> str:
        response = await _create(
            client, headers, variables_schema=STRICT_SCHEMA, sample_variables={"n": 1}
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    async def test_patch_checks_a_lone_sample_against_the_stored_schema(
        self, client, headers, strict_template_id
    ):
        response = await client.patch(
            f"/api/v1/templates/{strict_template_id}",
            headers=headers,
            json={"sample_variables": {"n": "not-an-integer"}},
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["section"] == "sample_variables"

    async def test_patch_checks_a_lone_schema_against_the_stored_sample(
        self, client, headers, strict_template_id
    ):
        """Tightening a schema must not silently strand the sample it was
        supposed to describe."""
        response = await client.patch(
            f"/api/v1/templates/{strict_template_id}",
            headers=headers,
            json={"variables_schema": {"type": "object", "properties": {"n": {"type": "string"}}}},
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["section"] == "sample_variables"

    async def test_a_rejected_patch_leaves_the_stored_row_intact(
        self, client, headers, strict_template_id
    ):
        await client.patch(
            f"/api/v1/templates/{strict_template_id}",
            headers=headers,
            json={"sample_variables": {"n": "not-an-integer"}},
        )
        response = await client.get(f"/api/v1/templates/{strict_template_id}", headers=headers)
        assert response.json()["sample_variables"] == {"n": 1}
        assert response.json()["variables_schema"] == STRICT_SCHEMA

    async def test_patch_accepts_a_compatible_schema_replacement(
        self, client, headers, strict_template_id
    ):
        response = await client.patch(
            f"/api/v1/templates/{strict_template_id}",
            headers=headers,
            json={"variables_schema": VALID_SCHEMA},
        )
        assert response.status_code == 200, response.text

    async def test_patch_clearing_the_schema_lifts_the_constraint(
        self, client, headers, strict_template_id
    ):
        response = await client.patch(
            f"/api/v1/templates/{strict_template_id}",
            headers=headers,
            json={"variables_schema": None, "sample_variables": {"n": "anything"}},
        )
        assert response.status_code == 200, response.text

    async def test_patch_clearing_the_sample_needs_no_judgement(
        self, client, headers, strict_template_id
    ):
        response = await client.patch(
            f"/api/v1/templates/{strict_template_id}",
            headers=headers,
            json={"sample_variables": None},
        )
        assert response.status_code == 200, response.text
        assert response.json()["sample_variables"] is None

    async def test_an_unrelated_patch_does_not_rejudge_the_stored_pair(
        self, client, headers, db_session, tenant
    ):
        """A pre-guard row holding a contradictory pair stays editable on
        other fields — only a request touching the pair triggers the check."""
        stored = Template(
            tenant_id=tenant.id,
            name=f"contradictory-{secrets.token_hex(4)}",
            title_template="x",
            body_template="y",
            variables_schema=STRICT_SCHEMA,
            sample_variables={"n": "not-an-integer"},
        )
        db_session.add(stored)
        await db_session.flush()
        response = await client.patch(
            f"/api/v1/templates/{stored.id}", headers=headers, json={"title_template": "z"}
        )
        assert response.status_code == 200, response.text

    async def test_a_lone_sample_patch_names_a_malformed_stored_schema(
        self, client, headers, db_session, tenant
    ):
        """Pre-#28 row with a broken stored schema: the fault is the schema,
        not the sample the consumer just sent — dispatch's precedent."""
        stored = Template(
            tenant_id=tenant.id,
            name=f"legacy-{secrets.token_hex(4)}",
            title_template="x",
            body_template="y",
            variables_schema=INVALID_SCHEMA,
        )
        db_session.add(stored)
        await db_session.flush()
        response = await client.patch(
            f"/api/v1/templates/{stored.id}",
            headers=headers,
            json={"sample_variables": {"n": 1}},
        )
        assert response.status_code == 422, response.text
        assert response.json()["detail"]["section"] == "variables_schema"


class TestSchemaReferences:
    """`check_schema` passes a `$ref` it will never be able to resolve.

    Metaschema-valid, so the write guard waved it through — and `iter_errors`
    then raised `referencing.exceptions.Unresolvable`, which is not a
    SchemaError and which no route catches. That is a 500 on consumer input:
    the exact failure #28 set out to remove, wearing a different hat.
    """

    async def test_an_external_ref_is_rejected_on_write(self, client, headers):
        response = await _create(client, headers, variables_schema=EXTERNAL_REF_SCHEMA)
        assert response.status_code == 422, response.text
        assert any("$ref" in e["msg"] for e in response.json()["detail"])

    async def test_an_external_ref_is_rejected_on_patch(self, client, headers):
        created = await _create(client, headers)
        response = await client.patch(
            f"/api/v1/templates/{created.json()['id']}",
            headers=headers,
            json={"variables_schema": EXTERNAL_REF_SCHEMA},
        )
        assert response.status_code == 422, response.text

    async def test_a_dangling_local_pointer_is_rejected_on_write(self, client, headers):
        """`#/$defs/missing` is metaschema-valid and resolves to nothing."""
        response = await _create(client, headers, variables_schema=DANGLING_REF_SCHEMA)
        assert response.status_code == 422, response.text

    async def test_a_resolvable_local_ref_is_accepted(self, client, headers):
        schema = {
            "type": "object",
            "$defs": {"count": {"type": "integer"}},
            "properties": {"n": {"$ref": "#/$defs/count"}},
        }
        response = await _create(client, headers, variables_schema=schema)
        assert response.status_code == 201, response.text

    async def test_a_ref_shaped_data_value_is_not_mistaken_for_a_reference(self, client, headers):
        """`const`/`enum` hold instance data, not subschemas. A payload that
        happens to contain a `$ref` key is not a reference to resolve."""
        schema = {"type": "object", "properties": {"n": {"const": {"$ref": "https://x.test/s"}}}}
        response = await _create(client, headers, variables_schema=schema)
        assert response.status_code == 201, response.text


class TestDeliberateExclusions:
    """Three behaviours the write-time guard deliberately does *not* change.

    Each is documented on `JSONSchemaDict`; each would be silently undone by
    "consistently" applying that type to one more model. Pinned here so the
    undoing fails a test instead of a consumer's request.
    """

    @pytest.fixture
    async def legacy_template(self, db_session, tenant) -> Template:
        """A row holding a schema the write guard would refuse today —
        inserted through the ORM, as a pre-guard template effectively was."""
        stored = Template(
            tenant_id=tenant.id,
            name=f"legacy-{secrets.token_hex(4)}",
            title_template="x",
            body_template="y",
            variables_schema=INVALID_SCHEMA,
        )
        db_session.add(stored)
        await db_session.flush()
        return stored

    async def test_inline_preview_reports_a_bad_schema_in_band(self, client, headers):
        """POST /preview answers 200 with `error_section`, by design. Adding
        JSONSchemaDict to PreviewRequest would turn it into a hard 422 and
        break the endpoint whose whole job is explaining what is wrong."""
        response = await client.post(
            "/api/v1/preview",
            headers=headers,
            json={
                "title_template": "t",
                "body_template": "b",
                "variables": {},
                "variables_schema": INVALID_SCHEMA,
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["error_section"] == "variables_schema"
        assert "not a valid JSON Schema" in response.json()["error"]

    async def test_template_preview_reports_a_bad_stored_schema_in_band(
        self, client, headers, legacy_template
    ):
        response = await client.post(
            f"/api/v1/templates/{legacy_template.id}/preview", headers=headers, json={}
        )
        assert response.status_code == 200, response.text
        assert response.json()["error_section"] == "variables_schema"

    async def test_a_legacy_row_can_still_be_read_back(self, client, headers, legacy_template):
        """TemplateOut stays an opaque dict. Typing it as JSONSchemaDict would
        make response-model validation fail on the row — turning a readable
        legacy template into a 500 for GET and for the whole list endpoint."""
        response = await client.get(f"/api/v1/templates/{legacy_template.id}", headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["variables_schema"] == INVALID_SCHEMA

        listing = await client.get("/api/v1/templates", headers=headers)
        assert listing.status_code == 200, listing.text

    async def test_an_unrelated_patch_leaves_a_legacy_row_alone(
        self, client, headers, legacy_template
    ):
        """Only a supplied `variables_schema` is validated — an untouched one
        is not resurrected for judgement by an edit to another field."""
        response = await client.patch(
            f"/api/v1/templates/{legacy_template.id}",
            headers=headers,
            json={"title_template": "z"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["variables_schema"] == INVALID_SCHEMA
