"""Intervals.icu custom item content schemas reference for LLM consumption.

Exposed as the `intervals-icu://custom-item-schemas` MCP Resource. The
`content` parameter on create_custom_item and update_custom_item points
the LLM here instead of inlining the per-item_type schema in every
Annotated description.
"""

CUSTOM_ITEM_SCHEMAS_SPEC = """# Intervals.icu Custom Item Content Schemas

Use this reference when constructing the `content` object for
create_custom_item or update_custom_item. The shape of `content` depends
on the `item_type` value. **Read this before guessing — getting `content`
wrong causes a generic HTTP 400 from the API with no schema hint.**

## Field-type items (REQUIRE `content`)

These three item types share an identical content schema:

- `INPUT_FIELD` — extra input on the wellness page (e.g. RPE, mood, weight)
- `ACTIVITY_FIELD` — extra field on each activity (e.g. bike weight, fuel)
- `INTERVAL_FIELD` — extra field on each interval (e.g. perceived effort)

### Schema

```json
{
  "code": "<MachineId>",
  "type": "<numeric|text|select>",
  "aggregate": "<MIN|SUM|MAX|AVERAGE>"
}
```

### Constraints

- `code`: machine identifier. Regex: `[A-Z][A-Za-z0-9]+`. Must start with
  an uppercase letter and contain only ASCII alphanumerics. No spaces,
  underscores, hyphens, or dots.
- `type`: must be exactly one of `numeric`, `text`, or `select`.
  **NOT `number` or `string` — the API rejects those.**
- `aggregate`: must be exactly one of `MIN`, `SUM`, `MAX`, `AVERAGE`.
  **NOT `AVG` — the API rejects that.**

### Worked examples

```json
{
  "name": "RPE",
  "item_type": "INPUT_FIELD",
  "description": "Rating of perceived exertion (1-10)",
  "content": {"code": "Rpe", "type": "numeric", "aggregate": "AVERAGE"},
  "visibility": "PRIVATE"
}
```

```json
{
  "name": "Bike Weight",
  "item_type": "ACTIVITY_FIELD",
  "content": {"code": "BikeWeight", "type": "numeric", "aggregate": "AVERAGE"}
}
```

```json
{
  "name": "Workout Tag",
  "item_type": "INTERVAL_FIELD",
  "content": {"code": "Tag", "type": "select", "aggregate": "MAX"}
}
```

## All other item types (OMIT `content` when creating)

For these types, **do not send `content`** when creating via the API.
The API provisions a default configuration that the user then customizes
in the Intervals.icu web UI (where the chart-builder / zone-editor /
panel-designer lives). Sending a hand-rolled `content` for these types
without knowing the exact shape will fail.

| `item_type`         | What it is                                       |
|---------------------|--------------------------------------------------|
| `FITNESS_CHART`     | Custom chart on the fitness page                 |
| `FITNESS_TABLE`     | Custom table on the fitness page                 |
| `TRACE_CHART`       | Custom trace (overlay) chart                     |
| `ACTIVITY_CHART`    | Custom chart on the activity page                |
| `ACTIVITY_HISTOGRAM`| Custom histogram on the activity page            |
| `ACTIVITY_HEATMAP`  | Custom heatmap on the activity page              |
| `ACTIVITY_MAP`      | Custom map on the activity page                  |
| `ACTIVITY_PANEL`    | Custom panel (composite) on the activity page    |
| `ACTIVITY_STREAM`   | Computed time-series stream                      |
| `ZONES`             | Custom power/HR/pace zone set                    |

### Recommended workflow for these types

1. Call `create_custom_item` with just `name`, `item_type`, and
   `visibility` — omit `content`.
2. Tell the user the item was created and they should open it in the
   Intervals.icu UI to configure the details.
3. If the user later wants to inspect the shape, call
   `get_custom_item(item_id)` after they've configured it — that returns
   the actual `content` the API stored, which can be used as a template
   for future `update_custom_item` calls.

## `visibility` enum (any item type)

- `PRIVATE` (default if omitted) — only the owner sees it
- `FOLLOWERS` — visible to followers
- `PUBLIC` — visible to anyone

## Update semantics

`update_custom_item.content` **replaces** the existing `content` object
wholesale. If you want to change one field of a field-type item, fetch
the current content with `get_custom_item` first, mutate it, and pass
the full object back.
"""
