# Local smoke UI decisions

Audience: a retention analyst reviewing a synthetic historical risk ranking. The screen's job
is to connect a model result to its cohort, source and limitations. The Next.js product UI is
separate planned work.

Design pass: paper white `#f8fafc`, ink navy `#14283f`, slate `#52647b`, blue `#2359b8`,
amber `#805000`, pale blue `#eaf1fc`. Use Avenir Next with system sans fallbacks for readable
tables and text; tabular numerals for probability comparisons. Left-aligned layout with a
wide risk table and a narrower evaluation/lineage rail, stacked on mobile.

```
RetentionOps                         Synthetic demo
Historical risk review              Cohort + model status
Risk ranking (table + probability)   Evaluation + limits
```

Brief review: a generic wall of KPI cards would hide the actual analyst task. Use the risk
ranking as the main surface; put diagnostic metrics in a definition list. A blue probability
bar is the only visual emphasis. No external fonts, animation, fake activity or invented KPIs.

Acceptance: API-backed rows; explicit synthetic/history labels; loading, empty, failure and
retry states; accessible headers; keyboard focus; responsive layout. Browser evidence is
recorded in the Day 1 report only after observed testing.
