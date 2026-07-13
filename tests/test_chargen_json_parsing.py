# tests/test_chargen_json_parsing.py — _extract_json() and its repair passes.
#
# Local models frequently produce "JSON" that isn't quite valid: real
# newlines inside string values instead of escaped \n (mes_example
# especially, since it's asked for multi-turn dialogue), or occasionally
# an entirely missing opening quote (mes_example's own <START>...<START>
# convention markers look enough like delimiters that some models treat
# them as the value's real boundary). Both were real bugs found via actual
# user-reported model output, not hypothetical edge cases.

import chargen_dialog as cg


def test_plain_valid_json_unaffected(qapp):
    raw = '{"name": "Bob", "description": "A simple guy.", "personality": "Nice."}'
    assert cg._extract_json(raw) == {
        "name": "Bob", "description": "A simple guy.", "personality": "Nice.",
    }


def test_non_json_text_returns_none(qapp):
    assert cg._extract_json("Sorry, I can't help with that request.") is None


def test_fenced_json_extracted_from_surrounding_prose(qapp):
    raw = (
        "Here's the card:\n```json\n"
        '{"name": "Faeva", "description": "An elf."}'
        "\n```\nHope that helps!"
    )
    result = cg._extract_json(raw)
    assert result == {"name": "Faeva", "description": "An elf."}


def test_real_newlines_in_properly_quoted_value(qapp):
    """strict=False fix: a real (unescaped) newline inside an otherwise
    correctly-quoted string value used to hard-fail json.loads() entirely."""
    raw = '''{
  "name": "Faeva",
  "mes_example": "<START>
{{user}}: hi
{{char}}: hello
<START>"
}'''
    result = cg._extract_json(raw)
    assert result is not None
    assert result["name"] == "Faeva"
    assert "{{user}}" in result["mes_example"]
    assert "\n" in result["mes_example"]


def test_missing_opening_quote_gets_repaired(qapp):
    """_repair_unquoted_values fix: this is the user's actual real model
    output (abbreviated) -- mes_example's value is missing its opening
    quote entirely, which strict=False alone can't fix since the value
    never had valid string syntax to begin with."""
    raw = '''{
  "name": "Faeva",
  "description": "Faeva is an elven girl, a guardian spirit of the ancient forest of Elara.",
  "personality": "Gentle, serene, knowledgeable, wise.",
  "scenario": "Faeva sits in a grassy clearing, surrounded by massive trees.",
  "first_mes": "Faeva looks at you, her silver hair blowing lightly in the wind.",
  "mes_example": <START>
{{user}}: *I sit down next to Faeva.* Do you live here alone?
{{char}}: *Faeva looks up.* Oh, no, I am never alone here. Elara is filled with life!
<START>
}'''
    result = cg._extract_json(raw)
    assert result is not None
    assert result["name"] == "Faeva"
    assert result["description"].startswith("Faeva is an elven girl")
    assert result["mes_example"].startswith("<START>")
    assert "{{user}}" in result["mes_example"]


def test_repair_does_not_touch_already_quoted_fields(qapp):
    """Regex gotcha: a plain \\s* right before the repair's negative
    lookahead used to backtrack to zero-width so the lookahead could test
    an unconsumed space instead of the real next character, silently
    "approving" already-quoted fields as broken and double-wrapping them.
    Fixed with possessive quantifiers (\\s*+) -- this guards the fix."""
    raw = '{"name": "Faeva", "description": "An elf.", "personality": "Kind."}'
    result = cg._extract_json(raw)
    assert result["name"] == "Faeva"  # not '"Faeva"' (double-wrapped)
    assert result["description"] == "An elf."


def test_field_name_as_prose_does_not_confuse_boundary_detection(qapp):
    """A field name (e.g. "personality") appearing as plain text inside a
    DIFFERENT field's value must not be mistaken for a real field
    boundary by the repair pass's lookahead."""
    raw = (
        '{"name": "Ann", "description": "Her personality is warm and kind.", '
        '"personality": "Warm, kind."}'
    )
    result = cg._extract_json(raw)
    assert result["description"] == "Her personality is warm and kind."
    assert result["personality"] == "Warm, kind."
