# ZugaLife — User Breach Notification Email Template

**Authority:** 16 CFR §318.6 (FTC HBNR). All fields below are required.
**Status:** Template — Mike's legal review required before sending.

---

## From / Subject

```
From:   legal@zugatechnologies.com
Reply-To: legal@zugatechnologies.com
Subject: Important security notice about your ZugaLife account
```

## Body

```
Hi [FIRST_NAME],

We're writing because on [BREACH_DISCOVERY_DATE], we discovered that
unauthorized access occurred to systems that contained your ZugaLife
account information. We're sorry. You deserve a straight account.

[ONE PARAGRAPH — WHAT HAPPENED]
[Replace at incident time with a plain-English explanation. Avoid
"sophisticated attacker" language. Be specific about what failed.]

[ONE PARAGRAPH — WHEN IT HAPPENED]
The unauthorized access occurred on [BREACH_DATE] and was discovered
on [BREACH_DISCOVERY_DATE]. The window of exposure was approximately
[N days/hours].

[ONE PARAGRAPH — WHAT WAS ACCESSED]
The accessed information likely included your: [DATA_CATEGORIES — e.g.
"mood log entries", "journal entries", "AI therapist conversations",
"email address and account creation date"]. Specifically NOT accessed:
[NEGATIVE_LIST — e.g. "payment card details (handled by Stripe)",
"SuperTokens password hashes"].

[ONE PARAGRAPH — WHAT YOU SHOULD DO]
[Tailor to data category. Examples:]
- Review your mood log and journal entries at zugabot.ai/life — if
  anything looks tampered with, contact us
- Watch for phishing emails referencing your wellness data
- Consider changing your password at zugabot.ai/auth (we did not
  detect password compromise but recommend rotation as a precaution)

[ONE PARAGRAPH — WHAT WE'RE DOING]
We have: (1) closed the access vector, (2) rotated all credentials
that could have been exposed, (3) audited every system that touched
the affected data, (4) filed required reports with the U.S. Federal
Trade Commission and the [state] Attorney General. A detailed
post-mortem will be posted at zugatechnologies.com/security/
within 30 days.

[ONE PARAGRAPH — YOUR RIGHTS]
You can: delete your ZugaLife account at any time (Settings → Delete
account), revoke consent for data collection and AI sharing (Settings
→ Privacy & Consent), request a copy of your data (reply to this
email), or file a complaint with the FTC at ftc.gov/complaint.

For Washington residents: you may also file a complaint under WA MHMDA
with the Washington Attorney General at atg.wa.gov.

For California residents: you may also file a complaint under CMIA
with the California Attorney General at oag.ca.gov.

If you have questions, reply to this email. A human at Zuga
Technologies will respond within 3 business days.

Sincerely,
Mike [LAST_NAME], Co-founder, Zuga Technologies
Antonio Delgado, Co-founder, Zuga Technologies
```

---

## Variables checklist (before sending)

- [ ] `[FIRST_NAME]` resolved from `users.name`
- [ ] `[BREACH_DISCOVERY_DATE]` — ISO date
- [ ] `[BREACH_DATE]` — ISO date
- [ ] `[DATA_CATEGORIES]` — match `breach_scope_query.py` output
- [ ] `[NEGATIVE_LIST]` — what was NOT accessed (be specific)
- [ ] WA / CA paragraphs included ONLY if the recipient is in that state
- [ ] Mike approved the final wording (per Issue #3 T5)
- [ ] Resend `from:` domain verified for `legal@zugatechnologies.com`
