from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=400)
    line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    severity: Literal["high", "medium", "low"]
    category: Literal["bug", "security", "quality", "performance"]
    title: str = Field(min_length=1, max_length=200)
    explanation: str = Field(min_length=1, max_length=2000)
    trigger: str = Field(min_length=1, max_length=1000)
    evidence: str = Field(min_length=1, max_length=2000)
    suggestion: str = Field(min_length=1, max_length=2000)


class Candidates(BaseModel):
    model_config = ConfigDict(extra="forbid")
    findings: list[Candidate] = Field(default_factory=list, max_length=12)


class Finding(Candidate):
    id: str
    source: str
    rule: str = ""
    snippet: str
    status: Literal[
        "unverified",
        "supported",
        "needs_context",
        "rejected",
        "reproduced",
        "pending_evidence",
    ] = "unverified"
    verification: str = "尚未复核；未运行待审代码。"
    validation: str = "静态诊断或代码推断；未执行复现测试。"
    related_diagnostics: list[dict] = Field(default_factory=list)
    reproduction: dict | None = None


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    status: Literal["supported", "needs_context", "rejected"]
    reason: str = Field(min_length=1, max_length=2000)


class Decisions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: list[Decision] = Field(default_factory=list, max_length=30)


class ReviewOptions(BaseModel):
    mode: Literal["evidence", "full", "assisted", "direct", "static"] = "full"
    max_files: int = Field(default=12, ge=1, le=500)
    max_file_bytes: int = Field(default=200_000, ge=100, le=1_000_000)
    max_calls: int = Field(default=24, ge=1, le=1000)
    chunk_lines: int = Field(default=180, ge=10, le=500)
    chunk_chars: int = Field(default=20_000, ge=1000, le=50_000)
    timeout: int = Field(default=45, ge=5, le=300)
    model: str | None = None
    scope: str = ""
    repro_image: str = "python:3.13-slim"
    repro_timeout: int = Field(default=15, ge=2, le=60)
    max_reproductions: int = Field(default=4, ge=1, le=20)


class ContractReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=400)
    start: int = Field(ge=1)
    end: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=3000)
    kind: Literal["documented_behavior", "existing_test", "language_rule"]
    rationale: str = Field(min_length=15, max_length=2000)


class ReproductionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applicable: bool
    reason: str = Field(min_length=1, max_length=2000)
    contract: ContractReference | None = None
    test_code: str = Field(default="", max_length=18000)
    expected_behavior: str = Field(default="", max_length=2000)


class EvidenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accepted: bool
    reason: str = Field(min_length=15, max_length=2000)


def public_options(options: ReviewOptions) -> dict:
    return options.model_dump()
