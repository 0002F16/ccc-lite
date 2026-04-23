# Client Profile Review — 2026-04-23

Scope:
- compared `~/Documents/CCC/Clients` against `data/clients` in Studio Lite
- excluded **John Yumul** per request
- added missing clients into Studio Lite selection
- reviewed source completeness and obvious data issues

## Added to Studio Lite

- Amandeep Kaur
- Amal Joseph
- Narmina Ibrahimova
- Nikul Padamani

## Current selection coverage

Clients now present in `data/clients`:
- Amandeep Kaur
- Amal Joseph
- Anastasiya Karaneuskaya
- Beste Keskiner
- Ganbar Shabanov
- Narmina Ibrahimova
- Nikul Padamani

Excluded:
- John Yumul

## Review notes by client

### Nikul Padamani
Status: **usable**

What was available:
- resume text with contact details, summary, experience, education, skills, and language levels
- coaching / targeting notes with role categories and positioning guidance

What was added:
- contact basics
- positioning guidance
- summary base
- experience entries
- education
- skills
- languages

Things to review later:
- LinkedIn URL is still not present in the source text, only a generic `LinkedIn` placeholder
- work authorization note is written as `Valid till October 2026)` in source and should be cleaned/verified for final-facing outputs
- English level is inconsistent across source material (`Professional B2` in the CV skills line vs `C1/Advanced English` in coaching notes); the Studio Lite profile keeps the direct CV wording for now
- there is a timeline gap between 2017 and 2021 that may be real, but should be checked before high-stakes use
- coaching notes reference State Street internship and fund-accounting interest, but the pasted resume itself does not show a State Street role; treat that as unverified unless another source confirms it

### Amandeep Kaur
Status: **placeholder only / missing verified resume source**

What was available:
- KPI tracker spreadsheet template
- a DOCX file that is effectively blank at the document-content level

What was added:
- minimal placeholder profile so the client appears in the Studio Lite selector

Blockers:
- no verified experience, education, skills, contact info, or positioning facts were recoverable from current source files

Needed to upgrade this profile:
- actual CV text, CV-building worksheet content, exported PDF, or a structured master profile

### Narmina Ibrahimova
Status: **usable**

What was available:
- KPI tracker spreadsheet template
- updated CV Library DOCX with substantial resume, positioning, LinkedIn, and skills content

What was added:
- contact basics
- positioning guidance
- summary base
- experience entries
- education
- skills
- languages

Things to review later:
- LinkedIn value in source is a custom URL text line rather than a fully qualified `https://` URL
- BSc graduation year is flagged inside the source as potentially inconsistent (`2019` vs `2021`) and should be verified
- Turkish and Russian are present but explicitly marked as level-unverified in source notes
- one intern bullet is marked estimated in the source and should stay conservative unless client confirms stronger wording

### Amal Joseph
Status: **usable with verification flags**

What was available:
- detailed resume text with contact info, summary, experience, education, skills, and languages
- coaching / positioning notes with an explicit Warsaw-market assessment and 50-role target list

What was added:
- contact basics
- positioning guidance focused on SSC / GBS, junior accounting, finance operations, audit-support, and analyst-track roles
- summary base
- experience entries
- education
- skills
- languages

Things to review later:
- LinkedIn URL is not present in the source text, only a generic `LinkedIn` placeholder
- work authorization is inconsistent across the source set: one section says `Authorised to work in Poland (TRC)`, while the coaching notes describe student-status / pending-TRC constraints; verify the current legal status before application use
- most role metrics are explicitly estimated in the source (`50+ daily transactions`, `3–5 cost centres`, `40+ vendors and clients`, `50+ employees`) and should remain conservative until confirmed
- the summary says `1.5 years of experience`, while the dated roles currently show around 13 months total between internship and junior-accountant work; verify the exact positioning language to avoid overclaiming
- tool stack is strong for Tally Prime / Peachtree and Excel, but SAP is only basic and there is no confirmed Power BI / SQL evidence; keep targeting away from tool-screened analyst roles unless new proof appears
- Polish is A1, so avoid roles requiring client-facing Polish or local statutory reporting ownership

## Recommended next pass

1. Get real source material for Amandeep and Narmina
   - PDF/DOCX with visible resume text
   - or their prior tailored resume / master profile
2. Verify Nikul’s
   - LinkedIn URL
   - work authorization wording
   - English level
   - any missing 2017–2021 history
3. If desired, normalize all Studio Lite profiles to one standard for:
   - language levels
   - date formats
   - label style
   - tool naming conventions
