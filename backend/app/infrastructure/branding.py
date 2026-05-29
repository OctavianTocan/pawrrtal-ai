"""Single source of truth for the product's name, slug, and themed identity.

Mirrors ``frontend/shared/branding.ts`` — keep the two in sync.  Renaming
the product is a one-file edit (this one and its frontend twin) plus a
commit.  Every user-visible string reads from these constants rather
than hardcoding the name.
"""

from __future__ import annotations

from typing import Final

#: Title-cased product name as users see it in copy.
PRODUCT_NAME: Final[str] = "Pawrrtal"

#: kebab-case slug used in URLs, package names, env-var prefixes.
PRODUCT_SLUG: Final[str] = "pawrrtal"

#: Domain hint for outbound email and marketing surfaces.
PRODUCT_DOMAIN: Final[str] = "pawrrtal.app"

#: Tagline / one-liner used by onboarding + marketing surfaces.
PRODUCT_TAGLINE: Final[str] = "Your purr-sonal AI workspace."

#: Theme identifier — drives palette and iconography choices.  Cat-
#: themed for now; rotating is a one-string edit here.
PRODUCT_THEME: Final[str] = "cat"

#: License under which the project is distributed.  See ``LICENSE`` at
#: the repo root for the full text.  FSL-1.1-Apache-2.0 is a
#: source-available license that converts to Apache-2.0 two years
#: after each release.
PRODUCT_LICENSE: Final[str] = "FSL-1.1-Apache-2.0"
