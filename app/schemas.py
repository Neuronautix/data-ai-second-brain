from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class EvidenceStatus(str, Enum):
    source_supported = "source_supported"
    manual_seed_unverified = "manual_seed_unverified"
    inferred = "inferred"
    rejected = "rejected"


class ProvisionalDecision(str, Enum):
    go = "go"
    conditional_go = "conditional_go"
    no_go = "no_go"
    insufficient_information = "insufficient_information"


class DocumentSource(BaseModel):
    source_id: str
    title: str
    source_type: str
    authority: str
    url_or_path: str
    date_ingested: datetime
    trust_level: str = "trusted"


class DocumentChunk(BaseModel):
    chunk_id: str
    source_id: str
    section_title: str | None = None
    text: str
    char_start: int
    char_end: int


_CONFIDENCE_MAP = {"low": 0.3, "medium": 0.6, "high": 0.9}


class Evidence(BaseModel):
    evidence_id: str | None = None
    source_id: str
    chunk_id: str
    quote_or_summary: str
    page_or_section: str | None = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    evidence_status: EvidenceStatus = EvidenceStatus.manual_seed_unverified

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v: object) -> float:
        if isinstance(v, str):
            try:
                return _CONFIDENCE_MAP[v.lower()]
            except KeyError:
                return float(v)
        return float(v)  # type: ignore[arg-type]


class Condition(BaseModel):
    id: str
    label: str
    description: str
    detection_hint: str


class Action(BaseModel):
    id: str
    label: str
    description: str
    action_type: str = "governance"


class Concept(BaseModel):
    id: str
    label: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    domain: str
    source_ids: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    subject: str
    predicate: str
    object: str
    evidence: list[Evidence] = Field(default_factory=list)
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)


class Rule(BaseModel):
    id: str
    label: str
    description: str
    domain: str
    severity: Severity
    applies_to: list[str] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    evidence: list[Evidence]
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    evidence_status: EvidenceStatus = EvidenceStatus.manual_seed_unverified

    @field_validator("confidence", mode="before")
    @classmethod
    def coerce_confidence(cls, v: object) -> float:
        if isinstance(v, str):
            try:
                return _CONFIDENCE_MAP[v.lower()]
            except KeyError:
                return float(v)
        return float(v)  # type: ignore[arg-type]

    @model_validator(mode="after")
    def validate_rule_has_evidence(self) -> "Rule":
        if not self.evidence:
            raise ValueError("Rule requires at least one evidence item (no evidence, no rule)")
        return self


class ProjectCard(BaseModel):
    title: str
    summary: str
    purpose: str = "unknown"
    actors: list[str] = Field(default_factory=list)
    data: list[str] = Field(default_factory=list)
    processing: list[str] = Field(default_factory=list)
    governance: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)


class DecisionOutput(BaseModel):
    provisional_decision: ProvisionalDecision
    rationale: str
    activated_conditions: list[str] = Field(default_factory=list)
    activated_rules: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class KnowledgePayload(BaseModel):
    concepts: list[Concept] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    conditions: list[Condition] = Field(default_factory=list)
    actions: list[Action] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class SeedURL(BaseModel):
    url: str
    authority: str = "unknown"
    trust_level: Literal["trusted", "reference", "unknown"] = "trusted"
    title: str | None = None


# Alias used by extract_knowledge to make the intent explicit.
ExtractionResult = KnowledgePayload
