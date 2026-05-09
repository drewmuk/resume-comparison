from pydantic import BaseModel, Field
from typing import List, Literal


class MatchScores(BaseModel):
    overall: int = Field(ge=0, le=100)
    technical_skills: int = Field(ge=0, le=100)
    experience_level: int = Field(ge=0, le=100)
    education_credentials: int = Field(ge=0, le=100)
    soft_skills_leadership: int = Field(ge=0, le=100)
    industry_knowledge: int = Field(ge=0, le=100)


class MatchedSkill(BaseModel):
    skill: str
    evidence_in_resume: str
    job_requirement: str
    strength: Literal["strong", "moderate", "weak"]


class SkillGap(BaseModel):
    skill: str
    importance: Literal["critical", "important", "nice_to_have"]
    reasoning: str
    how_to_address: str
    addressable_quickly: bool


class ResumeEdit(BaseModel):
    section: str
    issue: str
    suggested_change: str
    reasoning: str
    impact: Literal["high", "medium", "low"]


class ActionItem(BaseModel):
    priority: int
    action: str
    category: Literal[
        "skill_building",
        "resume_edit",
        "application_strategy",
        "networking",
        "certification",
    ]
    impact: Literal["high", "medium", "low"]
    effort: Literal["high", "medium", "low"]
    timeline: Literal["immediate", "1_week", "1_month", "3_months"]
    details: str


class AnalysisResult(BaseModel):
    job_title: str
    company_name: str
    analysis_timestamp: str
    match_scores: MatchScores
    executive_summary: str
    matched_skills: List[MatchedSkill]
    skill_gaps: List[SkillGap]
    resume_edits: List[ResumeEdit]
    action_items: List[ActionItem]
    keywords_to_add: List[str]
    strengths_to_emphasize: List[str]
