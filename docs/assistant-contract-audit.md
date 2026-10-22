# 36-criterion contract comparison

Base: `prototype-2-lina` at `e9fafc01d6323e6c934a928552735428bf614557`.

The runtime catalog has 100 entries: 10 supported, 90 planned. Of the requested 36,
10 are supported, 16 planned, and 10 absent. All 10 supported IDs and parameter
names match the contract exactly. Planned entries are excluded from recommendations.

| Contract ID | Runtime status | Parameter comparison |
| --- | --- | --- |
| `required_keywords` | supported | Exact parameter names |
| `forbidden_keywords` | supported | Exact parameter names |
| `required_phrases` | supported | Exact parameter names |
| `forbidden_phrases` | supported | Exact parameter names |
| `exact_match` | supported | Exact parameter names |
| `contains_text` | supported | Exact parameter names |
| `case_insensitive_match` | supported | Exact parameter names |
| `minimum_characters` | supported | Exact parameter names |
| `maximum_characters` | supported | Exact parameter names |
| `minimum_sentences` | supported | Exact parameter names |
| `valid_json` | planned | Not executable |
| `json_object` | absent | Not executable |
| `json_array` | absent | Not executable |
| `json_required_keys` | absent | Not executable |
| `json_forbidden_keys` | absent | Not executable |
| `json_field_type` | planned | Placeholder `{}`; contract requires `field, type` |
| `json_field_value` | planned | Placeholder `{}`; contract requires `field, value` |
| `json_array_min_length` | planned | Placeholder `{}`; contract requires `min_length` |
| `json_array_max_length` | planned | Placeholder `{}`; contract requires `max_length` |
| `json_schema` | planned | Placeholder `{}`; contract requires `schema` |
| `regex_match` | planned | Placeholder `{}`; contract requires `pattern` |
| `regex_not_match` | planned | Placeholder `{}`; contract requires `pattern` |
| `email_format` | planned | Not executable |
| `url_format` | planned | Not executable |
| `numeric_exact` | planned | Placeholder `{}`; contract requires `expected` |
| `numeric_range` | planned | Placeholder `{}`; contract requires `minimum, maximum` |
| `numeric_tolerance` | planned | Placeholder `{}`; contract requires `expected, tolerance` |
| `word_count_min` | planned | Placeholder `{}`; contract requires `count` |
| `word_count_max` | planned | Placeholder `{}`; contract requires `count` |
| `required_sections` | planned | Placeholder `{}`; contract requires `sections` |
| `keyword_coverage` | absent | Not executable |
| `prompt_relevance` | absent | Not executable |
| `response_length` | absent | Not executable |
| `sentence_structure` | absent | Not executable |
| `forbidden_terms` | absent | Not executable |
| `nonempty_response` | absent | Not executable |

The catalog also uses planned `schema_required_keys` and `schema_forbidden_keys`,
where the contract specifies `json_required_keys` and `json_forbidden_keys`. No
alias is introduced. The six legacy contract IDs are absent from this catalog;
the existing legacy scoring path remains intact and its regression tests pass.

Runtime parameter definitions use `list[str]`, `str`, and `int`, rather than JSON
Schema. The adapter translates these types generically and preserves parameter
names, then calls the authoritative registry validator for value constraints.
Integers must be nonnegative; `minimum_sentences.count` must be at least 1.

The dispatcher consumes `id` and `weight`; the recommendation API deliberately
retains `criterion_id` and `maximum_points` exactly as requested. This feature
does not automatically submit, execute, or save recommendations.
