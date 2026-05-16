"""ZugaLife consent versioning.

Bump CURRENT_CONSENT_VERSION every time the consent UI copy materially
changes (WA MHMDA / CA CMIA disclosure language, AI-sharing disclosure,
age affirmation wording). Users whose `life_consents.consent_version`
is less than CURRENT_CONSENT_VERSION are forced through the onboarding
consent gate again.

History:
  0 — initial placeholder copy (2026-05-13). NOT legally binding;
      blocked from revenue per Issue #3 until Mike's T1/T2/T3 lands.
  1 — RESERVED for Mike's first legal-final copy (T1+T2+T3 merged).
      DO NOT bump until that PR ships to master.

When Mike's copy lands:
  1. Bump CURRENT_CONSENT_VERSION below to 1.
  2. Deploy.
  3. All 15 pre-existing users (and any backfilled rows) auto-become
     stale → LifeOnboarding gate re-fires on their next /life visit.
  4. Email cohort that they need to re-accept the updated terms.
"""

CURRENT_CONSENT_VERSION: int = 0
