"""Region-type-specific prompts for GLM-OCR."""

from typing import Dict


# Region type to prompt mapping
REGION_PROMPTS: Dict[str, str] = {
    "text": "Text Recognition:",
    "table": "Table Recognition:",
    "formula": "Formula Recognition:",
    "title": "Text Recognition:",  # Titles use text recognition
    "figure": "Text Recognition:",  # Figures use text recognition for captions
    "caption": "Text Recognition:",
    "header": "Text Recognition:",
    "footer": "Text Recognition:",
}


def get_prompt_for_region_type(region_type: str, custom_prompt: str = None) -> str:
    """
    Get the appropriate prompt for a region type.
    
    Args:
        region_type: Type of region (text, table, formula, etc.)
        custom_prompt: Optional custom prompt override
    
    Returns:
        Prompt string to use for extraction
    """
    if custom_prompt:
        return custom_prompt
    
    return REGION_PROMPTS.get(region_type.lower(), REGION_PROMPTS["text"])
