You are extracting structured governance knowledge from trusted regulatory, institutional, or technical documents.

## Instructions

- Extract ONLY knowledge explicitly supported by the provided chunk text.
- Do NOT invent regulations, rules, or obligations.
- Do NOT generalize beyond what is stated in the text.
- Prefer returning empty arrays over hallucinating content.
- Every rule MUST include at least one evidence item.
- If no evidence supports a rule, do NOT include it.
- If the chunk is irrelevant or contains no extractable governance knowledge, return empty arrays for all fields.
- Use stable snake_case identifiers (e.g. `rule.data_minimization`, `concept.personal_data`).
- Mark inferred items clearly with `evidence_status: "inferred"` — they must NOT be treated as legal/regulatory fact.

## Evidence status values

- `source_supported` — directly supported by a quote or clear statement in the chunk
- `inferred` — reasonably implied but not explicitly stated; must be clearly marked
- `manual_seed_unverified` — manually seeded, not yet linked to a real source
- `rejected` — evidence is contradicted or insufficient; the rule must be excluded

## Domains

Use one of: `RGPD`, `CNIL`, `EDS`, `AI_GOVERNANCE`, `DATA_SHARING`, `SECURITY`, `PARTNERSHIP`, `RESEARCH`, `governance`, `gdpr`, `health_data`, `security`

## Severity

Use one of: `low`, `medium`, `high`

## Confidence

Use one of: `low`, `medium`, `high`

## Required JSON shape

Return ONLY valid JSON with no prose, no markdown fences, no explanation:

```json
{
  "concepts": [
    {
      "id": "concept.example",
      "label": "Example concept",
      "description": "Description grounded in the text",
      "aliases": [],
      "domain": "RGPD",
      "source_ids": ["<source_id from chunk metadata>"]
    }
  ],
  "rules": [
    {
      "id": "rule.example",
      "label": "Example rule",
      "description": "Rule description grounded in text",
      "domain": "RGPD",
      "severity": "high",
      "applies_to": [],
      "trigger_conditions": [],
      "recommended_actions": [],
      "confidence": "high",
      "evidence_status": "source_supported",
      "evidence": [
        {
          "source_id": "<source_id from chunk metadata>",
          "chunk_id": "<chunk_id from chunk metadata>",
          "quote_or_summary": "Exact or close quote from the text",
          "confidence": "high",
          "evidence_status": "source_supported"
        }
      ]
    }
  ],
  "conditions": [
    {
      "id": "condition.example",
      "label": "Example condition",
      "description": "Condition description",
      "detection_hint": "How to detect this condition"
    }
  ],
  "actions": [
    {
      "id": "action.example",
      "label": "Example action",
      "description": "Action description",
      "action_type": "governance"
    }
  ],
  "relations": [
    {
      "subject": "concept.example",
      "predicate": "requires",
      "object": "action.example",
      "confidence": "medium",
      "evidence": []
    }
  ],
  "evidence": []
}
```

## Chunk metadata

Source ID: <<source_id>>
Chunk ID: <<chunk_id>>
Section: <<section_title>>

## Chunk text

<<chunk_text>>
