# Analyst workspace design and acceptance

Primary job: select subscribers for review, understand their observed activity/payment/plan
context, compare mature cohorts, and decide whether the published model/data is trustworthy.
The System entry view adds the operator's job: inspect publication readiness, source truth,
artifact integrity and pipeline attempts before using the retention views.

## Design pass and review

Tokens: paper `#f4f7fb`, white `#ffffff`, ink `#16334b`, muted slate `#52687c`,
teal `#087566`, and amber `#805500`. Use Avenir Next/system sans and tabular numerals.
Keep the existing RetentionOps identity; make risk review the main working surface.

```
Navigation | Context / historical-data provenance / refresh
           | System: publication + source truth + artifact checksum + actual attempts
           | Overview: portfolio numbers + cohort history + review queue
           | Risk: filters + paginated table + customer detail dialog
           | Cohorts: selectable observed rates + explicit eligible denominator
           | Data & model: source/model lineage + actual job attempts
```

Brief review: avoid a wall of identical KPI cards and decorative charts. Use a compact
metric strip, a quiet cohort plot, and a wide table with observed feature values. Retention
views use one consistent workspace response; System uses its independent status response.
A detail dialog shows inputs, never fabricated causal reasons. Risk band policy is explicit:
high >=40%, watch >=20%, lower
<20%; these are triage thresholds, not proven intervention effectiveness.

## Interaction and evidence

Search by synthetic subscriber ID; filter band/auto-renew; apply/clear filters and paginate.
Risk search, filters and page offset live in the URL so reload, shared links and browser
history preserve the review state. Applying filters resets pagination.
Open a customer from a keyboard-accessible button, inspect feature dates, close by button
or Escape. Cohort buttons expose selected date and mature eligible/churned counts.
Views show loading, API failure/retry and no matches; requests abort when replaced.
Customer details pin the displayed model version.

The root `/` and `/system` open System; `/overview` opens Retention Overview, with `/risk`,
`/cohorts` and `/status` retaining their named views. System displays `ready`, `empty` or
`unavailable` publication state, plus a separate model checksum result. Attempts remain
visible before the first successful release when history is readable. Source truth labels
both snapshot and event outcomes as simulated; cloud is not connected and authentication
is not configured. No utilization, latency, uptime or cloud resource values are invented.
Data & model shows the selected model family, candidate/configuration and validation AP.
Source & artifact evidence expands to show actual source/event release IDs and dataset/model
checksums. The attempt table covers source generation/intake and model runs; Output rows
counts event revisions for source stages and scored customers for model stages. A successful
source attempt leaves model publication unchanged. Liveness-based service startup keeps
empty or first-failed System state accessible before score readiness is available.
An attempt recorded as running is shown as the last recorded state, not as proof that the
process is still alive; interrupted attempts that Python catches report their error type.

Next.js handles a single same-origin read proxy with a fixed backend and allowlisted paths;
FastAPI validates inputs and response models. Types are generated from exported OpenAPI.
No secrets/backend credentials enter browser bundles, no write actions or arbitrary URL
proxying, and no external fonts/charts/analytics. Local and Compose ports bind to loopback.
Verify responsive layout, contrast/keyboard flow and real API integration before accepting.
