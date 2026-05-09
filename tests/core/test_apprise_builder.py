"""Tests for src/core/notifications/apprise_builder.py.

Catalog introspection (`list_plugins`, `get_plugin_detail`, `get_service_name`)
and URL assembly (`assemble_url`) over the real Apprise plugin set. Schemes
chosen are stable across recent Apprise versions; if Apprise renames or removes
one of them, the failing test localises the breakage.
"""

import apprise
import pytest

from src.core.notifications.apprise_builder import (
    assemble_url,
    get_plugin_detail,
    get_service_name,
    list_plugins,
)


def test_list_plugins_returns_sorted_dicts_with_expected_keys():
    plugins = list_plugins()
    assert plugins, "Apprise should expose at least one plugin"
    expected_keys = {"plugin_schema", "service_name", "setup_url", "service_url", "category"}
    for p in plugins:
        assert expected_keys.issubset(p.keys())
    names = [p["service_name"].lower() for p in plugins]
    assert names == sorted(names)


def test_list_plugins_returns_independent_copy():
    """Mutating the returned list must not leak into subsequent calls."""
    plugins = list_plugins()
    plugins[0]["mutated"] = True
    plugins.append({"plugin_schema": "fake"})
    fresh = list_plugins()
    assert "mutated" not in fresh[0]
    assert fresh[-1]["plugin_schema"] != "fake"


def test_get_plugin_detail_shape_for_known_scheme():
    detail = get_plugin_detail("mailtos")
    assert detail is not None
    assert detail["plugin_schema"] == "mailtos"
    assert detail["service_name"] == "E-Mail"
    assert isinstance(detail["tokens"], dict)
    assert isinstance(detail["variants"], list)
    # Token meta carries the documented sub-keys
    sample = next(iter(detail["tokens"].values()))
    for key in ("name", "type", "required", "private", "default", "values", "regex"):
        assert key in sample
    # The 'schema' token is always stripped from the public token map
    assert "schema" not in detail["tokens"]


def test_get_plugin_detail_is_case_insensitive():
    assert get_plugin_detail("MAILTOS")["plugin_schema"] == "mailtos"


def test_get_plugin_detail_returns_none_for_unknown_scheme():
    assert get_plugin_detail("definitely-not-a-real-scheme") is None


def test_get_plugin_detail_emits_variants_when_templates_diverge():
    """Slack has multiple templates with different required-token sets."""
    detail = get_plugin_detail("slack")
    assert detail is not None
    assert len(detail["variants"]) >= 2
    for v in detail["variants"]:
        assert "label" in v
        assert "required_token_names" in v
        assert isinstance(v["required_token_names"], list)


def test_get_service_name_match_and_fallback():
    assert get_service_name("mailtos") == "E-Mail"
    # Unknown scheme falls back to the input string
    assert get_service_name("definitely-not-real") == "definitely-not-real"


def test_assemble_url_simple_scheme_round_trips_through_apprise():
    url = assemble_url("jsons", {"host": "example.com"})
    assert url.startswith("jsons://")
    assert apprise.Apprise().add(url)


def test_assemble_url_mailtos_with_targets_percent_encodes_email():
    url = assemble_url(
        "mailtos",
        {"user": "alice", "password": "s3cret", "host": "example.com", "targets": "to@d.com"},
    )
    # @ in targets must be percent-encoded so it lands in the path, not netloc
    assert "to%40d.com" in url
    assert apprise.Apprise().add(url)


def test_assemble_url_remaps_target_email_via_map_to():
    """Mailgun's `target_email` token has map_to='targets'; the value must
    end up substituted into the {targets} placeholder in the URL template."""
    url = assemble_url(
        "mailgun",
        {
            "user": "noreply",
            "host": "example.com",
            "apikey": "key-abc",
            "target_email": "rcpt@d.com",
        },
    )
    assert "rcpt%40d.com" in url
    assert apprise.Apprise().add(url)


def test_assemble_url_unknown_scheme_raises_value_error():
    with pytest.raises(ValueError, match="Unknown Apprise plugin schema"):
        assemble_url("definitely-not-real", {"host": "x"})


def test_assemble_url_missing_required_tokens_raises_value_error():
    """Mailgun requires user, host, apikey — omit apikey."""
    with pytest.raises(ValueError, match="Missing required tokens"):
        assemble_url("mailgun", {"user": "noreply", "host": "example.com"})


def test_assemble_url_variant_index_in_bounds_filters_templates():
    """An in-bounds variant_index drives template selection through the
    `groups.values()[variant_index]` filter path."""
    detail = get_plugin_detail("slack")
    assert detail and len(detail["variants"]) >= 2
    variant = detail["variants"][0]
    tokens = {name: "x" for name in variant["required_token_names"]}
    url = assemble_url("slack", tokens, variant_index=0)
    assert apprise.Apprise().add(url)


def test_assemble_url_variant_index_out_of_range_falls_back():
    """Out-of-range indices skip the filter and try all templates; the call
    still resolves if the supplied tokens satisfy at least one template."""
    detail = get_plugin_detail("slack")
    assert detail and len(detail["variants"]) >= 2
    variant = detail["variants"][0]
    tokens = {name: "x" for name in variant["required_token_names"]}
    url = assemble_url("slack", tokens, variant_index=999)
    assert apprise.Apprise().add(url)
