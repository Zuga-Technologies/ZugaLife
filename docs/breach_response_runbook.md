# ZugaLife Breach Response Runbook

**Statute basis:** FTC Health Breach Notification Rule — 16 CFR Part 318
(eff 2024-07-29). Also satisfies WA MHMDA breach-notification §19.373.110
(45-day SLA) — our 60-day FTC SLA is the longer of the two; we commit
to the shorter SLA when WA users are affected.

**Issue:** [Zuga-Technologies/ZugaLife#3](https://github.com/Zuga-Technologies/ZugaLife/issues/3) row T5
**Process owner:** Mike (TacoNips) — designated breach response lead
**Template author:** Buga
**Last reviewed:** 2026-05-16

This is the legal-template runbook. Mike owns *executing* the process
during an actual incident. Buga's role is to provide the technical
scope query + email blast. Both must be on call during an active breach.

---

## Trigger conditions

A "breach" under 16 CFR §318.2(c) means ANY acquisition of unsecured
personally identifiable health information without authorization. This
INCLUDES, NOT limited to:

- Database leak (SQL injection, backup exposed publicly, S3 misconfig)
- Stolen credentials with admin access to production data
- Lost laptop with unencrypted DB dump
- Insider misuse (employee accessing user records outside their role)
- Third-party processor breach (Venice AI, Stripe, SuperTokens, Railway)

**NOT a breach** (per §318.2(c)(2)):
- Encrypted data + key not also compromised
- Accidental access by authorized personnel that they did not
  acquire or retain

If unsure: assume breach, run the runbook. Better to over-notify.

---

## Phase 1 — DETECT (T+0)

**Trigger sources Buga is on call for:**
- Sentry alert on `data_management.py`, `consent_guards.py`, auth modules
- GitHub Dependabot CVE on a load-bearing dep (FastAPI/SQLAlchemy/SuperTokens)
- Railway access-log anomaly (unfamiliar IP, mass `/api/life/*` traffic)
- Third-party processor breach notification email
- User report at `legal@zugatechnologies.com`

**Action on detection:**
1. Buga or Mike opens a Linear/GitHub private incident with prefix `INC-`
2. Page the other immediately (text + Slack)
3. Freeze production deploys (Railway: pause auto-deploy on master)
4. Preserve evidence — snapshot Railway DB, save logs, NO destructive
   actions on production data until scope is known

**Buga's technical action:**
- Run `python scripts/breach_scope_query.py --window <ISO start>..<ISO end>`
  to get a preliminary affected-user list
- Save the output to the incident folder, do not commit user emails
  to git

---

## Phase 2 — ASSESS SCOPE (T+0 to T+72h)

**Mike** and **Buga** together fill in:

| Field | Source |
|---|---|
| Date breach discovered | INC- timestamp |
| Date breach occurred | from logs |
| # of users affected | `breach_scope_query.py` output |
| Data categories accessed | based on tables touched — mood, journal, habits, therapist transcripts, consent records |
| States represented | join users.state column (if populated) or geo-IP from auth logs |
| Third-party processors involved | Venice AI, Stripe, SuperTokens, Railway |

**Critical thresholds** that drive notification scope:
- ≥500 affected residents in any one state → **prominent media notice**
  in that state (§318.5(b))
- Any WA resident affected → 45-day SLA (faster than FTC's 60-day)
- Any CA resident with mental-health data accessed → CMIA §56.36 also
  triggers; consult Cooley/Wilson Sonsini before notification

---

## Phase 3 — USER NOTIFICATION (within 60 days of discovery)

**Channels** (§318.5(a)):
1. Email to last-known email address (preferred)
2. Mail if email bounces
3. Substitute notice on `zugabot.ai/life` if email unavailable for ≥10 users

**Email template:** `docs/breach_email_template.md` — Mike-approved
language before sending.

**Required elements per §318.6:**
- A brief description of what happened
- The date of the breach and the date of discovery
- The types of unsecured PHR information involved
- Steps the user should take to protect themselves
- What ZugaLife is doing to investigate the breach, mitigate harm,
  and protect against further breaches
- Contact info (phone, postal, email, or web)

**Buga's technical action:**
- Use `scripts/breach_email_send.py` (write at incident time — out of
  scope for this runbook template). Use Resend with the
  `life-compliance` template. Throttle to <500/hour to respect Resend
  shared-domain rate limit.

---

## Phase 4 — FTC NOTIFICATION (60-day SLA)

**If <500 affected:** Annual log to FTC via
https://www.ftc.gov/enforcement/rules/rulemaking-regulatory-reform-proceedings/health-breach-notification-rule

**If ≥500 affected:** Within 60 days of discovery, file the same form
PLUS notify each state AG for states with ≥1 affected resident.

**Mike** owns the filing.

---

## Phase 5 — MEDIA NOTICE (≥500 in any single state)

Buy a "prominent media notice" (§318.5(b)) — newspaper or local broadcast
station in the state. Mike to coordinate with PR/comms.

---

## Post-incident

Within 30 days of resolution:
1. Public post-mortem on `zugatechnologies.com/security/` (no user names)
2. Code fix merged + deployed
3. Update this runbook with anything we learned
4. Update `MEMORY.md` feedback file if any new "don't do X" rule emerged

---

## Drill schedule

Run a tabletop drill EVERY 90 DAYS. Last drill: ____. Next due: ____.

Update both dates in this section after each drill.
