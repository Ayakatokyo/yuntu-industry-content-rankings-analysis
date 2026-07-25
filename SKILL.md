---
name: yuntu-industry-content-rankings-analysis
description: Use when Yuntu industry-content ranking materials need a bounded list-to-seconds-level-detail workflow through fixed Yuce RPA connectors.
---

# Yuntu Industry Content Rankings Analysis

Use this standalone skill to retrieve a Yuntu industry content rankings list
with `rpa.conn.juliang.yt.industry.content.rankings.list`, select the first
unique numeric `material_id` values in response order, then retrieve each
selection with `rpa.conn.juliang.yt.industry.content.rankings.detail`. The
connector metadata is fixed internally and cannot be supplied or overridden.

## Runtime Requirements

Set these environment variables before contacting the gateway:

- `ENV_BACKEND_HOST`: a bare trusted HTTPS gateway URL without an IP literal,
  userinfo, query, or fragment.
- `YUCE_AUTHORIZATION`: the gateway authorization value.
- `YUCE_SESSION_ID`: the gateway agent session ID.

Credentials remain in the environment. Do not put credentials in commands,
input JSON, or output paths. Run `list-accounts` when `shop_id` is unknown.

## Parameters

`fetch` accepts the list connector's optional `--industry`, time range, age,
gender, crowd, brand scope, brand, and ranking-limit filters. List custom dates
use the same Asia/Shanghai limits as the list skill. Detail dates use
`--detail-date-range-type` (`LAST_7_DAYS`, `LAST_30_DAYS`, or `CUSTOM`); custom
detail dates require both `--detail-custom-start-date` and
`--detail-custom-end-date`, with the end not earlier than the start.

`--top-n` is a positive integer and defaults to `10`. It limits the first
unique numeric material IDs in the returned order. `material_id` is always
selected from the list response, never supplied as a detail override.

The list filter flags are `--industry`, `--time-range-type`,
`--custom-start-date`, `--custom-end-date`, `--ages`, `--genders`,
`--crowd-groups`, `--brand-scope-type`, `--brands`, and
`--ranking-limit-type`.

## Commands

Run commands from the workspace root. The skill requires Python and
`requests>=2.31,<3`.

List authorized accounts:

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py list-accounts
```

Print the analysis parameter metadata:

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py schema
```

Run offline checks without contacting the gateway:

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py self-test
```

Fetch a list and seconds-level details for up to ten selected materials:

```bash
python yuntu-industry-content-rankings-analysis/scripts/rpa_connector.py fetch \
  --shop-id "<shop_id>" \
  --industry "食品饮料" \
  --time-range-type "LAST_7_DAYS" \
  --detail-date-range-type "LAST_7_DAYS" \
  --top-n 10 \
  --output-dir "RPA数据汇总/yuntu-rankings-analysis"
```

For a custom detail range, add `--detail-date-range-type "CUSTOM"` with both
`--detail-custom-start-date` and `--detail-custom-end-date`.

## Output And Failures

The output directory is atomically populated with:

- `list-response.json`: the raw successful list response.
- `details/<material_id>.json`: each raw successful detail response.
- `manifest.json`: filters, selected IDs, relative response paths, per-material
  status, and non-sensitive error summaries.

If the list fails or has no valid material ID, the command writes a manifest
and exits nonzero without starting detail requests. A failed detail request is
recorded and the next selected material continues; the command exits nonzero
when any detail fails, while successful detail JSON files remain available.

This skill does not download video, process `files` results, extract frames,
retry requests, or resume interrupted work. It does not generate reports.
