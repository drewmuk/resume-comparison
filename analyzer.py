import os
from datetime import datetime

import anthropic

from models import AnalysisResult

_SYSTEM_PROMPT = """You are an expert career counselor, hiring manager, and resume strategist \
with 20+ years of experience in talent acquisition across software, finance, consulting, \
and operations.

Your role is to perform rigorous, evidence-based analysis of resumes against job descriptions. \
You:
- Identify precise skill matches with specific textual evidence from the resume
- Surface gaps with honest reasoning about why they matter for THIS role
- Understand ATS keyword optimization and what recruiters actually scan for
- Score candidates realistically — 80+ means genuinely competitive
- Create prioritized action plans ordered by highest ROI for interview success

Be specific, direct, and actionable. Vague feedback is useless to a job seeker."""

# Full JSON schema matching AnalysisResult so the model is forced to return
# structured data via tool use.
_ANALYSIS_TOOL = {
    "name": "submit_analysis",
    "description": "Submit the complete structured resume-vs-job-description analysis.",
    "input_schema": {
        "type": "object",
        "required": [
            "job_title",
            "company_name",
            "match_scores",
            "executive_summary",
            "matched_skills",
            "skill_gaps",
            "resume_edits",
            "action_items",
            "keywords_to_add",
            "strengths_to_emphasize",
        ],
        "properties": {
            "job_title": {"type": "string"},
            "company_name": {"type": "string"},
            "match_scores": {
                "type": "object",
                "required": [
                    "overall",
                    "technical_skills",
                    "experience_level",
                    "education_credentials",
                    "soft_skills_leadership",
                    "industry_knowledge",
                ],
                "properties": {
                    "overall": {"type": "integer", "minimum": 0, "maximum": 100},
                    "technical_skills": {"type": "integer", "minimum": 0, "maximum": 100},
                    "experience_level": {"type": "integer", "minimum": 0, "maximum": 100},
                    "education_credentials": {"type": "integer", "minimum": 0, "maximum": 100},
                    "soft_skills_leadership": {"type": "integer", "minimum": 0, "maximum": 100},
                    "industry_knowledge": {"type": "integer", "minimum": 0, "maximum": 100},
                },
            },
            "executive_summary": {"type": "string"},
            "matched_skills": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["skill", "evidence_in_resume", "job_requirement", "strength"],
                    "properties": {
                        "skill": {"type": "string"},
                        "evidence_in_resume": {"type": "string"},
                        "job_requirement": {"type": "string"},
                        "strength": {"type": "string", "enum": ["strong", "moderate", "weak"]},
                    },
                },
            },
            "skill_gaps": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "skill",
                        "importance",
                        "reasoning",
                        "how_to_address",
                        "addressable_quickly",
                    ],
                    "properties": {
                        "skill": {"type": "string"},
                        "importance": {
                            "type": "string",
                            "enum": ["critical", "important", "nice_to_have"],
                        },
                        "reasoning": {"type": "string"},
                        "how_to_address": {"type": "string"},
                        "addressable_quickly": {"type": "boolean"},
                    },
                },
            },
            "resume_edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["section", "issue", "suggested_change", "reasoning", "impact"],
                    "properties": {
                        "section": {"type": "string"},
                        "issue": {"type": "string"},
                        "suggested_change": {"type": "string"},
                        "reasoning": {"type": "string"},
                        "impact": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                },
            },
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": [
                        "priority",
                        "action",
                        "category",
                        "impact",
                        "effort",
                        "timeline",
                        "details",
                    ],
                    "properties": {
                        "priority": {"type": "integer"},
                        "action": {"type": "string"},
                        "category": {
                            "type": "string",
                            "enum": [
                                "skill_building",
                                "resume_edit",
                                "application_strategy",
                                "networking",
                                "certification",
                            ],
                        },
                        "impact": {"type": "string", "enum": ["high", "medium", "low"]},
                        "effort": {"type": "string", "enum": ["high", "medium", "low"]},
                        "timeline": {
                            "type": "string",
                            "enum": ["immediate", "1_week", "1_month", "3_months"],
                        },
                        "details": {"type": "string"},
                    },
                },
            },
            "keywords_to_add": {"type": "array", "items": {"type": "string"}},
            "strengths_to_emphasize": {"type": "array", "items": {"type": "string"}},
        },
    },
}


def run_analysis(resume_text: str, job_description: str) -> AnalysisResult:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Copy .env.example to .env and add your key, or set the environment variable."
        )

    client = anthropic.Anthropic(api_key=api_key)

    # The system prompt and job description are marked for prompt caching.
    # When iterating on resume versions, the job description cache hit
    # avoids re-processing the same text.
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        system=[
            {
                "type": "text",
                "text": _SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        tools=[_ANALYSIS_TOOL],
        tool_choice={"type": "tool", "name": "submit_analysis"},
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"<job_description>\n{job_description}\n</job_description>",
                        # Cache the job description so repeated iterations
                        # (same job, different resume versions) are cheaper.
                        "cache_control": {"type": "ephemeral"},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"<resume>\n{resume_text}\n</resume>\n\n"
                            "Analyze this resume against the job description above. "
                            "Be specific and evidence-based."
                        ),
                    },
                ],
            }
        ],
        betas=["prompt-caching-2024-07-31"],
    )

    tool_block = next(b for b in response.content if b.type == "tool_use")
    data = tool_block.input
    data["analysis_timestamp"] = datetime.now().isoformat()

    _log_cache_stats(response)
    return AnalysisResult(**data)


def _log_cache_stats(response) -> None:
    usage = response.usage
    if hasattr(usage, "cache_read_input_tokens") and usage.cache_read_input_tokens:
        saved = usage.cache_read_input_tokens
        print(f"  [dim]Prompt cache hit: {saved:,} tokens reused[/dim]")
