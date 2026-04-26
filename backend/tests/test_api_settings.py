import pytest
from app.api.settings import DEFAULTS, _parse_value


def test_defaults_include_llm_keys():
    assert "llm_provider" in DEFAULTS
    assert "llm_model" in DEFAULTS
    assert "llm_base_url" in DEFAULTS
    assert "llm_api_key" in DEFAULTS
    assert "analysis_enabled" in DEFAULTS
    assert "breaking_threshold" in DEFAULTS
    assert "display_expand_summaries" in DEFAULTS
    assert "display_sort_by" in DEFAULTS
    assert "display_score_threshold" in DEFAULTS
    assert "notifications_enabled" in DEFAULTS


def test_parse_value_types():
    assert _parse_value("true") is True
    assert _parse_value("false") is False
    assert _parse_value("42") == 42
    assert _parse_value("ollama") == "ollama"
    assert _parse_value("") == ""
