# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Custom Google Cloud Translation Advanced (v3) with ICU MessageFormat support.

This is a standalone machine translation service based on Google Cloud Translation API v3.
Supports ICU MessageFormat including plural, select, and selectordinal.
"""

from __future__ import annotations

import json
import logging
import operator
from contextlib import suppress
from typing import TYPE_CHECKING

from django.utils.functional import cached_property

from google.api_core.exceptions import AlreadyExists, NotFound
from google.cloud import storage  # type: ignore[attr-defined]
from google.cloud.translate_v3 import (
    GcsSource,
    Glossary,
    GlossaryInputConfig,
    TranslateTextGlossaryConfig,
    TranslationServiceClient,
)
from google.oauth2 import service_account

from weblate.machinery.base import (
    GlossaryAlreadyExistsError,
    GlossaryDoesNotExistError,
    GlossaryMachineTranslationMixin,
    XMLMachineTranslationMixin,
)
from weblate.machinery.google import GoogleBaseTranslation

from .forms import CustomGoogleV3AdvancedForm
from .plural import PluralMachineTranslationMixin, translate_plural

if TYPE_CHECKING:
    from weblate.trans.models import Unit

    from weblate.machinery.base import (
        DownloadTranslations,
    )

logger = logging.getLogger(__name__)


class CustomGoogleV3Advanced(
    PluralMachineTranslationMixin,
    XMLMachineTranslationMixin,
    GoogleBaseTranslation,
    GlossaryMachineTranslationMixin,
):
    """
    Custom Google Cloud Translation Advanced (v3) with ICU MessageFormat support.
    
    This machine translation service provides:
    - Google Cloud Translation API v3 integration
    - ICU MessageFormat support (plural, select, selectordinal)
    - Glossary support via Google Cloud Storage
    - XML/HTML content handling
    
    Configuration requires:
    - credentials: Google service account JSON key
    - project: Google Cloud project ID
    - location: Google Cloud region (global, europe-west1, us-west1)
    - bucket_name: (optional) GCS bucket for glossary storage
    """

    name = "Custom Google V3 Advanced"
    max_score = 90
    settings_form = CustomGoogleV3AdvancedForm

    # estimation, actual limit is 10.4 million (10,485,760) UTF-8 bytes
    glossary_count_limit = 1000

    # Identifier must contain only lowercase letters, digits, or hyphens.
    glossary_name_format = (
        "weblate__{project}__{source_language}__{target_language}__{checksum}"
    )

    # Always enable plural support for custom translation
    @property
    def _plural_support_enabled(self) -> bool:
        return True

    @classmethod
    def get_identifier(cls) -> str:
        return "custom-google-v3-advanced"

    @cached_property
    def client(self):
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(self.settings["credentials"])
        )
        api_endpoint = "translate.googleapis.com"
        if self.settings["location"].startswith("europe-"):
            api_endpoint = "translate-eu.googleapis.com"
        elif self.settings["location"].startswith("us-"):
            api_endpoint = "translate-us.googleapis.com"
        return TranslationServiceClient(
            credentials=credentials, client_options={"api_endpoint": api_endpoint}
        )

    @cached_property
    def storage_client(self):
        credentials = service_account.Credentials.from_service_account_info(
            json.loads(self.settings["credentials"])
        )
        return storage.Client(credentials=credentials)

    @cached_property
    def storage_bucket(self):
        return self.storage_client.get_bucket(self.settings["bucket_name"])

    @cached_property
    def parent(self) -> str:
        project = self.settings["project"]
        location = self.settings["location"]
        return f"projects/{project}/locations/{location}"

    def download_languages(self):
        """List of supported languages."""
        response = self.client.get_supported_languages(request={"parent": self.parent})
        return [language.language_code for language in response.languages]

    def _translate_text(
        self,
        source_language: str,
        target_language: str,
        text: str,
        glossary_path: str | None = None,
        mime_type: str = "text/html",
    ) -> str:
        """
        Translate a single text using Google Cloud Translation API.

        Args:
            source_language: Source language code
            target_language: Target language code
            text: Text to translate
            glossary_path: Optional glossary resource path
            mime_type: MIME type (text/html or text/plain)

        Returns:
            Translated text
        """
        request = {
            "parent": self.parent,
            "contents": [text],
            "target_language_code": target_language,
            "source_language_code": source_language,
            "mime_type": mime_type,
        }

        if glossary_path:
            request["glossary_config"] = TranslateTextGlossaryConfig(
                glossary=glossary_path
            )

        response = self.client.translate_text(request)

        response_translations = (
            response.glossary_translations if glossary_path else response.translations
        )

        return response_translations[0].translated_text

    def download_translations(
        self,
        source_language,
        target_language,
        text: str,
        unit,
        user,
        threshold: int = 75,
    ) -> DownloadTranslations:
        """Download list of possible translations from a service."""
        logger.info(
            "[CustomGoogleV3Advanced] Input: %r | %s -> %s",
            text,
            source_language,
            target_language,
        )

        glossary_path: str | None = None
        if self.settings.get("bucket_name"):
            glossary_id = self.get_glossary_id(source_language, target_language, unit)
            if glossary_id is not None:
                glossary_path = self.get_glossary_resource_path(glossary_id)

        # Create translate function for plural support
        # Use text/plain to avoid HTML processing issues with plural forms
        def translate_func(t: str) -> str:
            return self._translate_text(
                source_language, target_language, t, glossary_path,
                mime_type="text/plain"
            )

        # Use plural-aware translation
        translated_text = translate_plural(text, translate_func)

        logger.info(
            "[CustomGoogleV3Advanced] Output: %r",
            translated_text,
        )

        yield {
            "text": translated_text,
            "quality": self.max_score,
            "service": self.name,
            "source": text,
        }

    def format_replacement(
        self, h_start: int, h_end: int, h_text: str, h_kind: Unit | None
    ) -> str:
        """Generate a single replacement."""
        return f'<span translate="no" id="{h_start}">{self.escape_text(h_text)}</span>'

    def cleanup_text(self, text, unit):
        text, replacements = super().cleanup_text(text, unit)

        # Sanitize newlines
        replacement = '<br translate="no">'
        replacements[replacement] = "\n"

        return text.replace("\n", replacement), replacements

    def list_glossaries(self) -> dict[str, str]:
        """Return dictionary with the name/id of the glossary as the key and value."""
        return {
            glossary.display_name: glossary.display_name
            for glossary in self.client.list_glossaries(parent=self.parent)
        }

    def create_glossary(
        self, source_language: str, target_language: str, name: str, tsv: str
    ) -> None:
        """
        Create glossary in the service.

        - Uploads the TSV file to gcs bucket
        - Creates the glossary in the service
        """
        # upload tsv to storage bucket
        glossary_bucket_file = self.storage_bucket.blob(f"{name}.tsv")
        glossary_bucket_file.upload_from_string(
            tsv, content_type="text/tab-separated-values"
        )
        # create glossary
        bucket_name = self.settings["bucket_name"]
        gcs_source = GcsSource(input_uri=f"gs://{bucket_name}/{name}.tsv")
        input_config = GlossaryInputConfig(gcs_source=gcs_source)

        glossary = Glossary(
            name=self.get_glossary_resource_path(name),
            language_pair=Glossary.LanguageCodePair(
                source_language_code=source_language,
                target_language_code=target_language,
            ),
            input_config=input_config,
        )
        try:
            self.client.create_glossary(parent=self.parent, glossary=glossary)
        except AlreadyExists as error:
            raise GlossaryAlreadyExistsError from error

    def delete_glossary(self, glossary_id: str) -> None:
        """Delete the glossary in service and storage bucket."""
        try:
            self.client.delete_glossary(
                name=self.get_glossary_resource_path(glossary_id)
            )
        except NotFound as error:
            raise GlossaryDoesNotExistError from error
        finally:
            with suppress(NotFound):
                #  delete tsv from storage bucket
                glossary_bucket_file = self.storage_bucket.blob(f"{glossary_id}.tsv")
                glossary_bucket_file.delete()

    def delete_oldest_glossary(self) -> None:
        """Delete the oldest glossary if any."""
        glossaries = sorted(
            self.client.list_glossaries(parent=self.parent),
            key=operator.attrgetter("submit_time"),
        )
        if glossaries:
            self.delete_glossary(glossaries[0].display_name)

    def get_glossary_resource_path(self, glossary_name: str):
        """Return the resource path used by the Translation API."""
        return self.client.glossary_path(
            self.settings["project"], self.settings["location"], glossary_name
        )
