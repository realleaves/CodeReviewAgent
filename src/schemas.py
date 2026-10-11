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
    status: Literal["unverified", "supported", "needs_context", "rejected"] = (
        "unverified"
    )
    verification: str = "尚未复核；未运行待审代码。"
    validation: str = "静态诊断或代码推断；未执行复现测试。"
    related_diagnostics: list[dict] = Field(default_factory=list)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    status: Literal["supported", "needs_context", "rejected"]
    reason: str = Field(min_length=1, max_length=2000)


class Decisions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: list[Decision] = Field(default_factory=list, max_length=30)


class ReviewOptions(BaseModel):
    mode: Literal["full", "assisted", "direct", "static"] = "full"
    max_files: int = Field(default=12, ge=1, le=500)
    max_file_bytes: int = Field(default=200_000, ge=100, le=1_000_000)
    max_calls: int = Field(default=24, ge=1, le=1000)
    chunk_lines: int = Field(default=180, ge=10, le=500)
    chunk_chars: int = Field(default=20_000, ge=1000, le=50_000)
    timeout: int = Field(default=45, ge=5, le=300)
    model: str | None = None
    scope: str = ""


def public_options(options: ReviewOptions) -> dict:
    return options.model_dump()
