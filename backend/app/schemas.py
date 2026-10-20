from typing import Literal, Optional
from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    language: str = Field(default="en", max_length=8)


class MatchedPattern(BaseModel):
    category: str
    category_en: Optional[str] = None
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


class VisitRequest(BaseModel):
    ref: Optional[str] = Field(default=None, max_length=40)


class FeedbackRequest(BaseModel):
    message: str = Field(min_length=3, max_length=2000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    contact: Optional[str] = Field(default=None, max_length=200)
    wants_pilot: bool = False
    ref: Optional[str] = Field(default=None, max_length=40)
    language: str = Field(default="en", max_length=8)
    website: Optional[str] = Field(default=None, max_length=200)  # hidden field: real people leave it empty


class ReportRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    category: Optional[str] = Field(default=None, max_length=120)
    location: Optional[str] = Field(default=None, max_length=120)


class ReportResponse(BaseModel):
    status: str
    id: int


class StatsResponse(BaseModel):
    total_reports: int
    top_categories: list[dict]
