# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Custom Google Cloud Translation Advanced (v3) with ICU MessageFormat support.

This is a standalone module that can be installed in Weblate Docker container.
Supports ICU MessageFormat including plural, select, and selectordinal.

Installation:
1. Copy this package to /app/data/python/machinery_custom/
2. Add to WEBLATE_MACHINERY setting:
   WEBLATE_MACHINERY=weblate.machinery.weblatememory.WeblateMemory,machinery_custom.CustomGoogleV3Advanced
"""

from .translation import CustomGoogleV3Advanced

__all__ = ["CustomGoogleV3Advanced"]
__version__ = "1.0.0"
