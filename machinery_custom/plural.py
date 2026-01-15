# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
ICU Message Format parser and translator mixin.

This module provides support for translating ICU MessageFormat strings
including plural and select formats by splitting them into individual
cases and translating each separately.

Supported formats:
- Plural: {count, plural, one{1 item} other{{count} items}}
- Select: {gender, select, male{He} female{She} other{They}}
- Nested: {gender, select, male{{count, plural, one{He has 1 item} other{He has {count} items}}} ...}
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from weblate.trans.models import Unit


# Plural form to number mapping for translation
# These values are used to replace placeholders when translating each case
# Values are chosen to trigger correct grammatical forms in Slavic languages:
# - zero/many/other: use numbers that require genitive plural (5, 0, 100)
# - one: use 1 for singular
# - two: use 2
# - few: use 3 for nominative plural (2-4 range)
PLURAL_FORM_VALUES: dict[str, str] = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "few": "3",      # Changed from 2 to 3 (still in 2-4 range for nominative plural)
    "many": "100",   # Changed from 10 to 100 (larger number for genitive plural)
    "other": "25",   # Changed from 5 to 25 (clearly genitive plural context)
    # Exact values like =0, =1, =2
    "=0": "0",
    "=1": "1",
    "=2": "2",
}

# ICU message types
ICU_TYPE_PLURAL = "plural"
ICU_TYPE_SELECT = "select"
ICU_TYPE_SELECTORDINAL = "selectordinal"

# Supported ICU message types
ICU_TYPES = {ICU_TYPE_PLURAL, ICU_TYPE_SELECT, ICU_TYPE_SELECTORDINAL}

# Pattern to find all placeholders like {variableName}
PLACEHOLDER_PATTERN = re.compile(r"\{(\w+)\}")


class ICUMessageParser:
    """
    Parser for ICU MessageFormat strings (plural, select, selectordinal).

    Handles parsing and reassembling of ICU formats like:
    - Plural: {count, plural, zero {no items} one {1 item} other {{count} items}}
    - Select: {gender, select, male{He} female{She} other{They}}
    - SelectOrdinal: {count, selectordinal, one{#st} two{#nd} few{#rd} other{#th}}

    Also supports additional placeholders in the content:
    {artistsCount, plural, zero{{artistsCountFormated} Artists} one{1 Artist} ...}

    Also supports ICU messages embedded in text:
    {count, plural, one{1 item} other{{count} items}} in the cart

    Example usage:
        parser = ICUMessageParser(text)
        if parser.is_icu_message:
            for case_name, case_content in parser.cases.items():
                prepared, replacements = parser.prepare_case_for_translation(
                    case_name, case_content
                )
                translated = translate(prepared)
                restored = parser.restore_placeholders(translated, replacements)
            result = parser.reassemble(translated_cases)
    """

    # Pattern to find start of ICU message
    # Matches: {variable, type, where type is plural/select/selectordinal
    ICU_MESSAGE_START_PATTERN = re.compile(
        r"\{(\w+),\s*(plural|select|selectordinal),\s*",
        re.DOTALL | re.IGNORECASE,
    )

    # Backward compatibility alias
    EMBEDDED_ICU_PATTERN = ICU_MESSAGE_START_PATTERN
    ICU_MESSAGE_PATTERN = ICU_MESSAGE_START_PATTERN

    def __init__(self, text: str):
        self.text = text
        self.variable_name: str | None = None
        self.message_type: str | None = None  # 'plural', 'select', or 'selectordinal'
        self.cases: dict[str, str] = {}
        self.is_icu_message = False
        # For backward compatibility
        self.is_plural = False
        # For embedded messages: text before and after the ICU message
        self.text_before: str = ""
        self.text_after: str = ""
        self.is_embedded = False
        self._parse()

    def _parse(self) -> None:
        """Parse the ICU message string using brace-counting for accuracy."""
        # Always use brace-counting approach to correctly handle:
        # 1. Single ICU messages
        # 2. Multiple ICU messages in sequence
        # 3. ICU messages embedded in text
        self._parse_with_brace_counting()

    def _parse_with_brace_counting(self) -> None:
        """
        Parse an ICU message using brace counting for accuracy.
        
        This approach correctly handles:
        - Single ICU messages: {count, plural, one{1} other{{count}}}
        - Multiple ICU messages: {a, plural, ...} • {b, plural, ...}
        - Embedded messages: Hello {count, plural, ...} world
        """
        match = self.ICU_MESSAGE_START_PATTERN.search(self.text)
        if not match:
            return

        # Found the start of an ICU message
        icu_start = match.start()
        self.variable_name = match.group(1)
        self.message_type = match.group(2).lower()
        self.text_before = self.text[:icu_start]

        # Find the matching closing brace for the ICU message
        # Start after "{variable, type, "
        pos = match.end()
        brace_count = 1  # We're inside the opening brace of the ICU message

        while pos < len(self.text) and brace_count > 0:
            if self.text[pos] == "{":
                brace_count += 1
            elif self.text[pos] == "}":
                brace_count -= 1
            pos += 1

        if brace_count == 0:
            # Found the end of the ICU message
            icu_end = pos
            self.text_after = self.text[icu_end:]

            # Extract cases string (between "{var, type, " and the final "}")
            cases_str = self.text[match.end() : icu_end - 1]
            self.cases = self._parse_cases(cases_str)
            self.is_icu_message = bool(self.cases)
            self.is_plural = self.is_icu_message and self.message_type == ICU_TYPE_PLURAL
            # Embedded if there's text before or after the ICU message
            self.is_embedded = bool(self.text_before or self.text_after)

    def _parse_cases(self, cases_str: str) -> dict[str, str]:
        """
        Parse the cases part of an ICU plural string.

        Handles nested braces correctly.
        """
        cases: dict[str, str] = {}
        i = 0
        length = len(cases_str)

        while i < length:
            # Skip whitespace
            while i < length and cases_str[i].isspace():
                i += 1

            if i >= length:
                break

            # Find case name (e.g., 'zero', 'one', '=0', etc.)
            case_start = i
            while i < length and cases_str[i] not in " \t\n{":
                i += 1

            case_name = cases_str[case_start:i].strip()
            if not case_name:
                break

            # Skip whitespace before opening brace
            while i < length and cases_str[i].isspace():
                i += 1

            if i >= length or cases_str[i] != "{":
                break

            # Find matching closing brace (handle nested braces)
            brace_count = 1
            content_start = i + 1
            i += 1

            while i < length and brace_count > 0:
                if cases_str[i] == "{":
                    brace_count += 1
                elif cases_str[i] == "}":
                    brace_count -= 1
                i += 1

            if brace_count == 0:
                case_content = cases_str[content_start : i - 1]
                cases[case_name] = case_content

        return cases

    def prepare_case_for_translation(
        self, case_name: str, case_content: str
    ) -> tuple[str, dict[str, str]]:
        """
        Prepare a case for translation by replacing all variable placeholders with numbers.

        Handles both the main plural variable and any additional placeholders
        like {artistsCountFormated}.

        Args:
            case_name: The plural case name (e.g., 'one', 'few', 'many')
            case_content: The content of the case to prepare

        Returns:
            tuple of (prepared_text, dict mapping placeholder names to replacement values)
        """
        # Get the replacement value based on case name
        replacement_value = PLURAL_FORM_VALUES.get(case_name, "5")

        # Find all placeholders in the content
        placeholders = PLACEHOLDER_PATTERN.findall(case_content)

        if not placeholders:
            return case_content, {}

        # Replace all placeholders with the same number value
        prepared_text = case_content
        replacements: dict[str, str] = {}

        for placeholder_name in placeholders:
            placeholder = f"{{{placeholder_name}}}"
            if placeholder in prepared_text:
                prepared_text = prepared_text.replace(placeholder, replacement_value)
                replacements[placeholder_name] = replacement_value

        return prepared_text, replacements

    def restore_placeholders(
        self, translated_text: str, replacements: dict[str, str]
    ) -> str:
        """
        Restore all variable placeholders in translated text.

        Args:
            translated_text: The translated text
            replacements: Dict mapping placeholder names to the values used for replacement

        Returns:
            Text with all placeholders restored
        """
        if not replacements:
            return translated_text

        result = translated_text

        # Group placeholders by their replacement value
        # (multiple placeholders might have the same value)
        value_to_placeholders: dict[str, list[str]] = {}
        for name, value in replacements.items():
            if value not in value_to_placeholders:
                value_to_placeholders[value] = []
            value_to_placeholders[value].append(name)

        # For each unique replacement value, restore placeholders
        for value, placeholder_names in value_to_placeholders.items():
            # If multiple placeholders had the same value, we need to restore them
            # We'll use a simple approach: replace all occurrences of the value
            # with the first placeholder, since they all had the same value
            # (this is the best we can do without more context)
            if len(placeholder_names) == 1:
                # Simple case: one placeholder for this value
                result = result.replace(value, f"{{{placeholder_names[0]}}}")
            else:
                # Multiple placeholders had same value - restore to first one
                # The caller should use different values if they need to distinguish
                result = result.replace(value, f"{{{placeholder_names[0]}}}")

        return result

    def reassemble(
        self,
        translated_cases: dict[str, str],
        translated_before: str = "",
        translated_after: str = "",
    ) -> str:
        """
        Reassemble the ICU message string with translated cases.

        Args:
            translated_cases: Dictionary mapping case names to translated content
            translated_before: Translated text before the ICU message (for embedded)
            translated_after: Translated text after the ICU message (for embedded)

        Returns:
            Complete ICU message string (with surrounding text if embedded)
        """
        if not self.is_icu_message or not self.variable_name or not self.message_type:
            return self.text

        # Build cases string maintaining original order
        cases_parts = []
        for case_name in self.cases:
            translated_content = translated_cases.get(case_name, self.cases[case_name])
            cases_parts.append(f"{case_name}{{{translated_content}}}")

        cases_str = " ".join(cases_parts)
        icu_str = f"{{{self.variable_name}, {self.message_type}, {cases_str}}}"

        # For embedded ICU messages, combine with translated surrounding text
        if self.is_embedded:
            before = translated_before if translated_before else self.text_before
            after = translated_after if translated_after else self.text_after
            return f"{before}{icu_str}{after}"

        return icu_str


def translate_with_placeholders(
    text: str,
    translate_func: Callable[[str], str],
) -> str:
    """
    Translate text while preserving ICU-style placeholders.

    Replaces {placeholder} with a marker, translates, then restores.
    If text contains only placeholders (no actual text to translate),
    returns the original text without calling translation service.

    Args:
        text: Text with placeholders like {variable}
        translate_func: A function that translates a single string

    Returns:
        Translated text with placeholders preserved
    """
    # Find all placeholders
    placeholders = PLACEHOLDER_PATTERN.findall(text)

    if not placeholders:
        # No placeholders, translate directly
        return translate_func(text)

    # Replace placeholders with numbered markers that won't be translated
    prepared_text = text
    placeholder_map: dict[str, str] = {}

    for i, placeholder_name in enumerate(placeholders):
        placeholder = f"{{{placeholder_name}}}"
        # Use a marker that's unlikely to be translated
        marker = f"__PH{i}__"
        prepared_text = prepared_text.replace(placeholder, marker)
        placeholder_map[marker] = placeholder

    # Check if there's any actual content to translate
    if not _has_translatable_content(prepared_text, placeholder_map):
        # Text is only placeholders - return original without translation
        return text

    # Translate
    translated_text = translate_func(prepared_text)

    # Restore placeholders
    result = translated_text
    for marker, placeholder in placeholder_map.items():
        result = result.replace(marker, placeholder)

    return result


def translate_icu_message(
    text: str,
    translate_func: Callable[[str], str],
) -> str:
    """
    Translate an ICU message, handling plural, select, and simple placeholders.

    This is a convenience function that handles the full translation flow.
    Also handles ICU messages embedded within other text.
    Handles nested ICU messages recursively.

    Args:
        text: The text to translate (may be ICU plural/select or simple placeholder format)
        translate_func: A function that translates a single string

    Returns:
        Translated text with placeholders and ICU structure preserved

    Example:
        def my_translate(text):
            return google_api.translate(text)

        result = translate_icu_message(icu_string, my_translate)
    """
    parser = ICUMessageParser(text)

    if not parser.is_icu_message:
        # Not an ICU format - check for simple placeholders
        return translate_with_placeholders(text, translate_func)

    translated_cases: dict[str, str] = {}

    for case_name, case_content in parser.cases.items():
        # First, recursively handle any nested ICU messages in this case
        nested_parser = ICUMessageParser(case_content)
        if nested_parser.is_icu_message:
            # Recursively translate the nested ICU message
            case_content = translate_icu_message(case_content, translate_func)
            # After recursive translation, the case content is already translated
            translated_cases[case_name] = case_content
        else:
            # No nested ICU message - prepare for translation
            # For plural/selectordinal, replace placeholders with appropriate numbers
            # For select, just protect placeholders
            if parser.message_type == ICU_TYPE_PLURAL or parser.message_type == ICU_TYPE_SELECTORDINAL:
                prepared_text, replacements = parser.prepare_case_for_translation(
                    case_name, case_content
                )
                # Check if there's actual content to translate (not just numbers)
                has_content = _has_translatable_content(prepared_text, {v: v for v in replacements.values()})
            else:
                # For select, use placeholder protection instead of number replacement
                prepared_text, replacements = _protect_placeholders(case_content)
                # Check if there's actual content to translate (not just placeholders)
                has_content = _has_translatable_content(prepared_text, replacements)

            if has_content:
                # Translate the prepared text
                translated_text = translate_func(prepared_text)

                # Restore all placeholders
                if parser.message_type == ICU_TYPE_PLURAL or parser.message_type == ICU_TYPE_SELECTORDINAL:
                    restored_text = parser.restore_placeholders(translated_text, replacements)
                else:
                    restored_text = _restore_protected_placeholders(translated_text, replacements)

                translated_cases[case_name] = restored_text
            else:
                # No translatable content - just keep the original (it's only placeholders)
                translated_cases[case_name] = case_content

    # Translate surrounding text for embedded ICU messages
    # Use recursive call to handle multiple ICU messages in sequence
    translated_before = ""
    translated_after = ""

    if parser.is_embedded:
        if parser.text_before.strip():
            # Preserve trailing whitespace (translation services often strip it)
            trailing_ws = parser.text_before[len(parser.text_before.rstrip()):]

            # Recursively translate - may contain more ICU messages
            translated_before = translate_icu_message(
                parser.text_before, translate_func
            )

            # Restore trailing whitespace if lost
            if trailing_ws and (not translated_before or not translated_before.endswith(trailing_ws)):
                translated_before = translated_before.rstrip() + trailing_ws

        if parser.text_after.strip():
            # Preserve leading whitespace (translation services often strip it)
            leading_ws = parser.text_after[:len(parser.text_after) - len(parser.text_after.lstrip())]

            # Recursively translate - may contain more ICU messages
            translated_after = translate_icu_message(
                parser.text_after, translate_func
            )

            # Restore leading whitespace if lost
            if leading_ws and (not translated_after or not translated_after.startswith(leading_ws)):
                translated_after = leading_ws + translated_after.lstrip()

    # Reassemble the ICU message string
    return parser.reassemble(translated_cases, translated_before, translated_after)


def _protect_placeholders(text: str) -> tuple[str, dict[str, str]]:
    """
    Protect ICU placeholders by replacing them with markers.

    Args:
        text: Text containing {placeholder} patterns

    Returns:
        tuple of (text with markers, dict mapping markers to original placeholders)
    """
    placeholders = PLACEHOLDER_PATTERN.findall(text)
    if not placeholders:
        return text, {}

    prepared_text = text
    replacements: dict[str, str] = {}

    for i, placeholder_name in enumerate(placeholders):
        placeholder = f"{{{placeholder_name}}}"
        marker = f"__ICU_PH_{i}__"
        prepared_text = prepared_text.replace(placeholder, marker)
        replacements[marker] = placeholder

    return prepared_text, replacements


def _has_translatable_content(text: str, markers: dict[str, str]) -> bool:
    """
    Check if text has any content that needs translation after removing markers.

    Args:
        text: Text with markers
        markers: Dict of markers that were substituted

    Returns:
        True if there's actual text to translate, False if only markers/whitespace
    """
    # Remove all markers from text
    check_text = text
    for marker in markers:
        check_text = check_text.replace(marker, "")
    
    # Check if anything remains besides whitespace
    return bool(check_text.strip())


def _restore_protected_placeholders(text: str, replacements: dict[str, str]) -> str:
    """
    Restore protected placeholders from markers.

    Args:
        text: Text with markers
        replacements: Dict mapping markers to original placeholders

    Returns:
        Text with original placeholders restored
    """
    result = text
    for marker, placeholder in replacements.items():
        result = result.replace(marker, placeholder)
    return result


def translate_plural(
    text: str,
    translate_func: Callable[[str], str],
) -> str:
    """
    Translate an ICU message, handling plural, select, and simple placeholders.

    This is an alias for translate_icu_message for backward compatibility.

    Args:
        text: The text to translate (may be ICU plural/select or simple placeholder format)
        translate_func: A function that translates a single string

    Returns:
        Translated text with placeholders preserved
    """
    return translate_icu_message(text, translate_func)


def is_icu_message(text: str) -> bool:
    """Check if text contains an ICU message format (plural/select, standalone or embedded)."""
    # Check for full ICU message match
    if ICUMessageParser.ICU_MESSAGE_PATTERN.match(text.strip()):
        return True
    # Check for embedded ICU message
    if ICUMessageParser.EMBEDDED_ICU_PATTERN.search(text):
        return True
    return False


def is_icu_plural(text: str) -> bool:
    """Check if text contains an ICU plural format (standalone or embedded).

    Note: This is kept for backward compatibility. Use is_icu_message() to check
    for any ICU message format (plural, select, selectordinal).
    """
    return is_icu_message(text)


def has_icu_placeholders(text: str) -> bool:
    """Check if text contains ICU-style placeholders like {variable}."""
    return bool(PLACEHOLDER_PATTERN.search(text))


class PluralMachineTranslationMixin:
    """
    Mixin for machine translation services that support ICU message translation.

    This mixin overrides cleanup_text to skip cleanup for ICU message strings
    (plural, select, selectordinal), allowing the ICU parser to handle them properly.

    Usage:
        class MyTranslation(PluralMachineTranslationMixin, XMLMachineTranslationMixin, ...):
            ...

    To always enable ICU support, define a property:
        @property
        def _plural_support_enabled(self) -> bool:
            return True
    """

    # Flag to track if we're processing an ICU message string
    _processing_plural: bool = False
    _plural_original_text: str | None = None

    def _is_plural_support_enabled(self) -> bool:
        """Check if ICU message support is enabled for this service."""
        # Check for property override first
        if hasattr(self, "_plural_support_enabled"):
            return getattr(self, "_plural_support_enabled")
        # Otherwise check settings
        return getattr(self, "settings", {}).get("enable_plural_support", False)

    def cleanup_text(
        self, text: str, unit: "Unit"
    ) -> tuple[str, dict[str, str]]:
        """
        Override cleanup_text to skip cleanup for ICU format strings.

        For ICU message strings (plural, select) and strings with ICU placeholders,
        we return the text unchanged so we can handle placeholder replacement properly.
        """
        # Check if ICU support is enabled
        if not self._is_plural_support_enabled():
            return super().cleanup_text(text, unit)  # type: ignore[misc]

        # Check if this is an ICU message format (plural, select, selectordinal)
        if is_icu_message(text):
            # Store the original text and flag that we're processing an ICU message
            self._processing_plural = True
            self._plural_original_text = text
            # Return text unchanged - ICU parser will handle placeholders
            return text, {}

        # Check if this has ICU-style placeholders like {variable}
        # Skip cleanup to prevent XML mixin from breaking the placeholders
        if has_icu_placeholders(text):
            self._processing_plural = False
            self._plural_original_text = None
            # Return text unchanged - we'll handle placeholders ourselves
            return text, {}

        # Not ICU format, use normal cleanup
        self._processing_plural = False
        self._plural_original_text = None
        return super().cleanup_text(text, unit)  # type: ignore[misc]


# Backward compatibility alias
ICUPluralParser = ICUMessageParser
