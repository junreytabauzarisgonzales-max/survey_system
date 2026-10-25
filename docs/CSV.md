# Student Survey Creator CSV encoding and export guarantees

## Common rules

Downloads use `survey-*.csv` and `survey-export-manifest.json`. Internally, exported records and API paths still use the original `interview` terminology; in the user interface these are called **responses**.

- UTF-8, no BOM, configurable comma/semicolon/tab delimiter, CRLF record endings.
- RFC-style quoting: quote fields containing the delimiter, quote, CR or LF; escape quotes by doubling them. Embedded newlines remain inside quoted cells.
- Server metadata timestamps are ISO 8601 UTC. Dates/times within answers retain their original validated ISO values.
- Identifiers and choice codes define stable columns, not mutable labels. The data dictionary maps them to original labels and version information.
- Numeric answers remain numeric, including negative values and zero; currency answers never acquire symbols or thousands separators. Boolean values are 1/0 in tabular cells and JSON booleans in raw answer objects.
- Non-answered values are empty cells with an explicit state. They are never silently converted to zero, false or the text `No`.
- Personal-field values, respondent/researcher identifiers, coordinate answers and media answers are excluded by default. Explicit inclusion requires the appropriate project grant. Project location categories are included by default as metadata unless deselected or de-identified.
- The mandatory `source` column distinguishes `researcher` interviews from `public_link` responses. Public responses are included in authorized project exports/analytics and can be selected with the collection-source filter. They have no assigned researcher, so identifiable exports leave that cell empty; no staff identity is fabricated.

Spreadsheet formula protection prefixes dangerous **text** cells with an apostrophe when a formula marker (`=`, `+`, `-`, `@`) follows leading whitespace/control characters. Initial tab/CR/LF also receives protection. Real numeric negative values remain numeric. This is an intentional display-safe transformation; use raw answer JSON when exact original text must be recovered.

## Formats

### Wide

One row per matching response. Base columns include project, response/interview ID, questionnaire version, status, location, collection/update timestamps, export timestamp and applied correction ID, subject to selected metadata/privacy options.

For each selected published version and question:

```
v_{version UUID}__q_{question UUID}__state
v_{version UUID}__q_{question UUID}
```

Multiple-choice value columns instead expand to:

```
v_{version UUID}__q_{question UUID}__{choice code}
```

Each choice cell is `1` when selected, `0` when not selected in an answered question, and empty for a non-answered question. A recorded empty choice array is distinct from an unanswered question. A required choice/media question must contain a selection to complete.

Columns from other versions have state `not_applicable_version`; they do not imply that a respondent skipped those questions. UUID qualification prevents accidental merging when labels/options change. Selected versions are grouped in the file but are not semantically coalesced.

### Long

One row per selected question for each matching response, **including missing question responses**. Columns add:

```
question_id, question_label, data_type, answer_state, answer_value
```

Arrays/objects in `answer_value` are JSON. A multiple-choice array such as `["a","b"]` preserves every selected code without delimiter ambiguity.

### Raw

Uses long structure. `answer_value` is always the JSON answer object:

```json
{"state":"answered","value":["a","b"]}
```

or, for example:

```json
{"state":"not_sure"}
```

This preserves string/number/boolean/array/object distinctions and exact recorded text after JSON decoding. Human-readable label cells may still receive spreadsheet protection. By default, exports use the latest tracked corrected snapshot; select **original submissions** to export immutable originals. The raw formatter does not normalize choice labels into recorded codes or change recorded values.

### Analysis-ready

Uses the wide coded structure. Choice codes and indicator columns replace mutable human-readable labels, numeric values stay numeric, and every question has an explicit state column. Download the accompanying data dictionary. State values are:

| State | Meaning |
|---|---|
| `answered` | A typed value was recorded; false/zero are valid values |
| `missing` | No response was recorded |
| `skipped` | Explicit skip, or not shown by conditional logic |
| `not_sure` | Respondent expressed uncertainty |
| `prefer_not_to_answer` | Respondent declined |
| `not_applicable_version` | Column belongs to a different form version |

## Dictionary, manifest and counts

The dictionary maps column/version/question/type/choice identifiers to original labels and documents state/indicator encoding. It is UTF-8 CSV with the same delimiter and spreadsheet protections.

The web CSV response exposes `X-Record-Count`, `X-Exported-At` and `X-Export-ID`. The download begins a SQLite read snapshot before sending headers. Row generation and the header count use that snapshot. A count preview is a separate query and may differ if responses arrive before download.

After download, **Save last export manifest** retrieves the audited export's exact count, resolved versions, columns, data types, filters and CSV row count. Long/raw row counts can exceed response counts. The server records `started`, then `completed` or `interrupted`; interrupted counts describe generated progress and should not be treated as a complete file. Local Android exports write their own manifest with response and CSV-row counts and record a local audit event.

Response exports stream server-side one interview at a time. The automated memory test streams 3,000 response rows with a peak Python allocation ceiling of 2 MB. This is a representative regression check, not a production capacity benchmark.

## Privacy and limitations

- Anonymization/de-identification excludes configured protected fields. Optional web per-export pseudonyms prevent exported interview IDs from linking directly across separate exports and omit precise collection metadata. This cannot remove identifying information mistakenly entered into an unprotected free-text answer; classify fields appropriately and review exports.
- CSV is a text table. It does **not** embed images, PDFs or recordings. Authorized media questions contain UUID references. Authorized users can download those resources separately through `/api/attachments/{id}`. A reference may temporarily precede its file while offline uploads are pending. Automatic attachment ZIP bundles are not implemented.
- Excel/spreadsheet row, column and precision limits apply. Many versions or large choice lists can exceed spreadsheet column limits. Use long/raw structure or a statistical tool for large/dynamic research sets. Very long integers/floating-point answers may be displayed differently by spreadsheet software; import with deliberate data types and retain the raw archive.
- Wide and analysis-ready share the same unambiguous coded encoding; the dictionary supplies human-readable interpretation. Multi-version exports deliberately use separate version-qualified columns, not a guessed semantic correspondence.
- Browser downloads use a Blob and can consume memory proportional to file size on the browser, even though the server streams. API clients can stream the response directly to disk.
- Android local exports include only locally stored, currently cached-authorized responses. They are not necessarily the entire server dataset. Local export does not perform synchronization, and local export audits currently stay on the device.
- CSV is not a complete database backup: it does not contain authentication data, complete configuration history, binary attachment content or the full correction chain. Use the verified database/local recovery backup facilities for restoration.
