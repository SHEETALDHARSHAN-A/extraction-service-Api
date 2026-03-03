"""Tests for prompt mapping."""

import pytest
from app.prompts import get_prompt_for_region_type, REGION_PROMPTS


class TestPromptMapping:
    """Tests for region type to prompt mapping."""
    
    def test_text_region_prompt(self):
        """Test text region prompt."""
        prompt = get_prompt_for_region_type("text")
        assert prompt == "Text Recognition:"
    
    def test_table_region_prompt(self):
        """Test table region prompt."""
        prompt = get_prompt_for_region_type("table")
        assert prompt == "Table Recognition:"
    
    def test_formula_region_prompt(self):
        """Test formula region prompt."""
        prompt = get_prompt_for_region_type("formula")
        assert prompt == "Formula Recognition:"
    
    def test_title_region_prompt(self):
        """Test title region prompt (uses text recognition)."""
        prompt = get_prompt_for_region_type("title")
        assert prompt == "Text Recognition:"
    
    def test_figure_region_prompt(self):
        """Test figure region prompt (uses text recognition)."""
        prompt = get_prompt_for_region_type("figure")
        assert prompt == "Text Recognition:"
    
    def test_custom_prompt_override(self):
        """Test custom prompt override."""
        custom = "Custom Recognition Prompt:"
        prompt = get_prompt_for_region_type("text", custom)
        assert prompt == custom
    
    def test_case_insensitive(self):
        """Test case insensitive region type."""
        prompt1 = get_prompt_for_region_type("TEXT")
        prompt2 = get_prompt_for_region_type("text")
        assert prompt1 == prompt2
    
    def test_unknown_region_type_fallback(self):
        """Test unknown region type falls back to text."""
        prompt = get_prompt_for_region_type("unknown_type")
        assert prompt == REGION_PROMPTS["text"]
    
    def test_all_region_types_have_prompts(self):
        """Test all expected region types have prompts."""
        expected_types = ["text", "table", "formula", "title", "figure", "caption", "header", "footer"]
        for region_type in expected_types:
            prompt = get_prompt_for_region_type(region_type)
            assert prompt is not None
            assert len(prompt) > 0
