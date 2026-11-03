# Analyst workspace design and acceptance

Primary job: select subscribers for review, understand their observed activity/payment/plan
context, compare mature cohorts, and decide whether the published model/data is trustworthy.
The owner approved this direction on 2026-11-03; four views follow the accepted PRD.

## Design pass and review

Tokens: paper `#f4f7fb`, white `#ffffff`, ink `#16334b`, muted slate `#52687c`,
teal `#087566`, and amber `#805500`. Use Avenir Next/system sans and tabular numerals.
Keep the existing RetentionOps identity; make risk review the main working surface.

```
Navigation | Context / historical-data provenance / refresh
           | Overview: portfolio numbers + cohort history + review queue
           | Risk: filters + paginated table + customer detail dialog
           | Cohorts: selectable observed rates + explicit eligible denominator
           | Data & model: source/model lineage + actual job attempts
```

Brief review: avoid a wall of identical KPI cards and decorative charts. Use a compact
metric strip, a quiet cohort plot, and a wide table with observed feature values. Every
number comes from one consistent workspace response. A detail dialog shows inputs, never
fabricated causal reasons. Risk band policy is explicit: high >=40%, watch >=20%, lower
<20%; these are triage thresholds, not proven intervention effectiveness.

## Interaction and evidence

Search by synthetic subscriber ID; filter band/auto-renew; apply/clear filters and paginate.
Open a customer from a keyboard-accessible button, inspect feature dates, close by button
or Escape. Cohort buttons expose selected date and mature eligible/churned counts.
Views show loading, API failure/retry and no matches. Pagination resets on filter changes;
requests abort when replaced. Customer details pin the displayed model version.

Next.js handles a single same-origin read proxy with a fixed backend and allowlisted paths;
FastAPI validates inputs and response models. Types are generated from exported OpenAPI.
No secrets/backend credentials enter browser bundles, no write actions or arbitrary URL
proxying, and no external fonts/charts/analytics. Local and Compose ports bind to loopback.
Verify responsive layout, contrast/keyboard flow and real API integration before accepting.
