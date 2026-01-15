# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Configuration form for Custom Google V3 Advanced Translation Service."""

from __future__ import annotations

import json

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, pgettext_lazy

from weblate.machinery.forms import BaseMachineryForm


class CustomGoogleV3AdvancedForm(BaseMachineryForm):
    """Configuration form for Custom Google V3 Advanced Translation Service."""

    credentials = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration",
            "Google Translate service account info",
        ),
        widget=forms.Textarea,
        help_text=pgettext_lazy(
            "Google Cloud Translation configuration",
            "Enter a JSON key for the service account.",
        ),
    )
    project = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Google Translate project"
        ),
        help_text=pgettext_lazy(
            "Google Cloud Translation configuration",
            "Enter the numeric or alphanumeric ID of your Google Cloud project.",
        ),
    )
    location = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Google Translate location"
        ),
        initial="global",
        help_text=pgettext_lazy(
            "Google Cloud Translation configuration",
            "Choose a Google Cloud Translation region that is used for the Google Cloud project or is closest to you.",
        ),
        widget=forms.Select(
            choices=(
                ("global", pgettext_lazy("Google Cloud region", "Global")),
                ("europe-west1", pgettext_lazy("Google Cloud region", "Europe")),
                ("us-west1", pgettext_lazy("Google Cloud region", "US")),
            )
        ),
    )
    bucket_name = forms.CharField(
        label=pgettext_lazy(
            "Automatic suggestion service configuration", "Google Storage Bucket name"
        ),
        help_text=pgettext_lazy(
            "Google Cloud Translation configuration",
            "Enter the name of the Google Cloud Storage bucket that is used to store the Glossary files.",
        ),
        required=False,
    )

    def clean_credentials(self):
        try:
            json.loads(self.cleaned_data["credentials"])
        except json.JSONDecodeError as error:
            raise ValidationError(
                gettext("Could not parse JSON: %s") % error
            ) from error
        return self.cleaned_data["credentials"]
