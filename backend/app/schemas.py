from typing import Literal, Optional
from pydantic import BaseModel


class VerifyRequest(BaseModel):
    message: str


class MatchedPattern(BaseModel):
    category: str
    title: str
    why: list[str]
    advice: str
    source: str


class VerifyResponse(BaseModel):
    verdict: Literal["likely_scam", "uncertain", "likely_safe", "link_unsupported"]
    confidence: int
    headline: str
    matched: Optional[MatchedPattern] = None
    generic_advice: Optional[str] = None
    link_notice: Optional[str] = None
    source_platform: Optional[str] = None


class ReportRequest(BaseModel):
    message: str
    category: Optional[str] = None
    location: Optional[str] = None


class ReportResponse(BaseModel):
    status: str
    id: int


class StatsResponse(BaseModel):
    total_reports: int
    top_categories: list[dict]
