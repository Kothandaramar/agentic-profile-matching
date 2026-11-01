"""LangGraph-powered candidate matching and screening agent."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph


class Requirements(TypedDict):
    must_have: list[str]
    nice_to_have: list[str]
    min_years: float | None
    keywords: list[str]


class Candidate(TypedDict, total=False):
    id: str
    name: str
    source: str
    text: str
    skills: list[str]
    years_experience: float | None
    retrieval_score: float
    score: float
    matched_must_have: list[str]
    missing_must_have: list[str]
    matched_nice_to_have: list[str]
    strengths: list[str]
    gaps: list[str]
    recommendation: str
    reasoning: str
    improvement_suggestion: str


class AgentState(TypedDict, total=False):
    user_query: str
    jd: str
    resume_dir: str
    conversation_history: list[dict[str, str]]
    requirements: Requirements
    candidates: list[Candidate]
    candidate_shortlist: list[Candidate]
    reasoning: dict[str, str]
    total_candidate_count: int
    report: str
    response: str
    intent: str
    human_feedback: str
    refinement_round: int
    max_refinement_rounds: int
    should_refine: bool


SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "React": ("react", "react.js", "reactjs"),
    "TypeScript": ("typescript", "ts"),
    "JavaScript": ("javascript", "js"),
    "Node.js": ("node.js", "nodejs", "node js"),
    "Python": ("python",),
    "Java": ("java",),
    "C#": ("c#", "c sharp"),
    ".NET": (".net", "dotnet"),
    "SQL": ("sql",),
    "PostgreSQL": ("postgresql", "postgres"),
    "MySQL": ("mysql",),
    "MongoDB": ("mongodb", "mongo"),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure",),
    "GCP": ("gcp", "google cloud"),
    "Docker": ("docker",),
    "Kubernetes": ("kubernetes", "k8s"),
    "GraphQL": ("graphql",),
    "REST": ("rest api", "restful"),
    "HTML": ("html",),
    "CSS": ("css",),
    "Vue": ("vue", "vue.js", "vuejs"),
    "Angular": ("angular",),
    "Django": ("django",),
    "Flask": ("flask",),
    "FastAPI": ("fastapi",),
    "Spring": ("spring", "spring boot"),
    "Machine Learning": ("machine learning", "ml"),
    "Pandas": ("pandas",),
    "TensorFlow": ("tensorflow",),
    "PyTorch": ("pytorch",),
    "Git": ("git",),
    "Linux": ("linux",),
}

_CANDIDATE_INDEX: dict[str, Candidate] = {}
_SKILL_PATTERNS = {
    skill: re.compile(
        r"(?<![\w+#])(?:"
        + "|".join(re.escape(alias) for alias in aliases)
        + r")(?![\w+#])",
        re.IGNORECASE,
    )
    for skill, aliases in SKILL_ALIASES.items()
}
_TOKEN_PATTERN = re.compile(r"[a-z0-9+#.]+", re.IGNORECASE)


def _skills_in(text: str) -> list[str]:
    return [skill for skill, pattern in _SKILL_PATTERNS.items() if pattern.search(text)]


def _years_in(text: str) -> float | None:
    patterns = (
        r"(?:at least|minimum(?: of)?|over|more than)\s*(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)",
        r"(\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?)(?:\s+of\s+experience)?",
        r"(\d+(?:\.\d+)?)\s*(?:years?|yrs?)(?:\s+of\s+(?:professional\s+)?experience)?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def extract_requirements(jd: str) -> Requirements:
    """Extract skills and an experience threshold from a job description/query."""
    nice_match = re.search(
        r"\b(?:nice[- ]to[- ]have|preferred|bonus|good[- ]to[- ]have)\b\s*[:\-]?",
        jd,
        re.IGNORECASE,
    )
    must_match = re.search(
        r"\b(?:must[- ]have|required|requirements?)\b\s*[:\-]?",
        jd,
        re.IGNORECASE,
    )

    if nice_match:
        must_text = jd[: nice_match.start()]
        nice_text = jd[nice_match.end() :]
        if must_match and must_match.start() > nice_match.start():
            must_text = jd[: nice_match.start()] + jd[must_match.end() : nice_match.start()]
    elif must_match:
        must_text = jd[must_match.end() :]
        nice_text = ""
    else:
        must_text, nice_text = jd, ""

    must_have = _skills_in(must_text)
    nice_to_have = [skill for skill in _skills_in(nice_text) if skill not in must_have]
    keywords = [
        term
        for term in ("leadership", "communication", "security", "testing", "agile", "analytics")
        if re.search(rf"\b{re.escape(term)}\b", jd, re.IGNORECASE)
    ]
    return {
        "must_have": must_have,
        "nice_to_have": nice_to_have,
        "min_years": _years_in(jd),
        "keywords": keywords,
    }


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(text)}


def _read_resume(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="replace")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError("Reading PDF resumes requires the pypdf dependency.") from exc
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("Reading DOCX resumes requires the python-docx dependency.") from exc
        return "\n".join(paragraph.text for paragraph in Document(str(path)).paragraphs)
    raise ValueError(f"Unsupported resume format: {path.suffix}")


def _candidate_from_file(path: Path) -> Candidate:
    text = _read_resume(path)
    candidate_id = hashlib.sha1(str(path.resolve()).encode("utf-8")).hexdigest()[:12]
    years = _years_in(text)
    return {
        "id": candidate_id,
        "name": path.stem.replace("_", " ").replace("-", " ").strip(),
        "source": str(path),
        "text": text,
        "skills": _skills_in(text),
        "years_experience": years,
    }


def search_resumes(
    query: str,
    resume_dir: str | Path = "resumes",
    limit: int = 100,
) -> list[Candidate]:
    """Retrieve resumes by lexical relevance; supports TXT, Markdown, PDF, and DOCX."""
    directory = Path(resume_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"Resume directory does not exist: {directory}")
    files = sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in {".txt", ".md", ".pdf", ".docx"}
    )
    query_tokens = _tokens(query)
    query_skills = _skills_in(query)
    candidates: list[Candidate] = []
    for path in files:
        candidate = _candidate_from_file(path)
        content_tokens = _tokens(candidate["text"])
        matched_tokens = query_tokens & content_tokens
        matched_skills = set(query_skills) & set(candidate["skills"])
        candidate["retrieval_score"] = (
            2 * len(matched_skills) + len(matched_tokens)
        ) / max(1, len(query_tokens) + len(query_skills))
        candidates.append(candidate)
    candidates.sort(
        key=lambda item: (item["retrieval_score"], item.get("years_experience") or 0),
        reverse=True,
    )
    selected = candidates[: max(0, limit)]
    _CANDIDATE_INDEX.update({candidate["id"]: candidate for candidate in selected})
    return selected


def compare_candidates(candidate_ids: list[str]) -> str:
    """Compare retrieved candidates using their match scores and evidence."""
    candidates = [_CANDIDATE_INDEX[cid] for cid in candidate_ids if cid in _CANDIDATE_INDEX]
    if len(candidates) != len(candidate_ids):
        unknown = [cid for cid in candidate_ids if cid not in _CANDIDATE_INDEX]
        raise ValueError(f"Unknown candidate ID(s): {', '.join(unknown)}")
    if len(candidates) < 2:
        return "Select at least two candidates to compare."
    lines = ["Candidate comparison:"]
    for candidate in sorted(candidates, key=lambda item: item.get("score", 0), reverse=True):
        lines.append(
            f"- {candidate['name']}: {candidate.get('score', 0):.0f}% match; "
            f"strengths: {', '.join(candidate.get('strengths', [])) or 'none identified'}; "
            f"gaps: {', '.join(candidate.get('gaps', [])) or 'none identified'}."
        )
    return "\n".join(lines)


def generate_interview_questions(candidate_id: str) -> list[str]:
    """Create screening questions grounded in a candidate's matched skills and gaps."""
    candidate = _CANDIDATE_INDEX.get(candidate_id)
    if candidate is None:
        raise ValueError(f"Unknown candidate ID: {candidate_id}")
    focus = candidate.get("gaps", []) or candidate.get("matched_must_have", [])
    questions = [
        f"Describe a recent project where you used {skill} and explain your specific contribution."
        for skill in focus[:3]
    ]
    questions.extend(
        [
            "How do you validate the quality and reliability of your work?",
            "Tell me about a technical trade-off you made and how you evaluated the alternatives.",
        ]
    )
    return questions


def _intent(query: str) -> Literal["search", "compare", "explain", "interview"]:
    lowered = query.lower()
    if any(word in lowered for word in ("interview question", "screening question", "ask candidate")):
        return "interview"
    if "compare" in lowered or "side by side" in lowered:
        return "compare"
    if any(word in lowered for word in ("why", "explain", "rank higher", "reason")):
        return "explain"
    return "search"


def _merge_requirements(old: Requirements, new: Requirements) -> Requirements:
    min_years = new["min_years"] if new["min_years"] is not None else old["min_years"]
    return {
        "must_have": list(dict.fromkeys(old["must_have"] + new["must_have"])),
        "nice_to_have": list(
            dict.fromkeys(old["nice_to_have"] + new["nice_to_have"])
        ),
        "min_years": min_years,
        "keywords": list(dict.fromkeys(old["keywords"] + new["keywords"])),
    }


def _parse_jd(state: AgentState) -> dict[str, Any]:
    query = state.get("user_query", "").strip()
    intent = _intent(query) if query else "search"
    jd = query if intent == "search" and query else state.get("jd", "")
    if not jd:
        jd = query
    history = list(state.get("conversation_history", []))
    if query:
        history.append({"role": "user", "content": query})
    return {
        "jd": jd,
        "intent": intent,
        "conversation_history": history,
        "refinement_round": (
            0 if intent == "search" and query else state.get("refinement_round", 0)
        ),
    }


def _extract_node(state: AgentState) -> dict[str, Any]:
    previous = state.get(
        "requirements",
        {"must_have": [], "nice_to_have": [], "min_years": None, "keywords": []},
    )
    extracted = extract_requirements(state.get("jd", ""))
    has_existing = bool(
        previous["must_have"] or previous["nice_to_have"] or previous["min_years"] is not None
    )
    feedback_round = state.get("refinement_round", 0) > 0
    if has_existing and feedback_round:
        feedback = state.get("jd", "")
        requirements = _merge_requirements(previous, extracted)
        removal = re.search(
            r"\b(?:remove|drop|exclude|no longer need|instead of|rather than)\b\s+([^.;]+)",
            feedback,
            re.IGNORECASE,
        )
        if removal:
            removed_skills = _skills_in(
                re.split(r"\b(?:but|and add|and require|instead use|instead require|use)\b",
                         removal.group(1), maxsplit=1, flags=re.IGNORECASE)[0]
            )
            requirements["must_have"] = [
                skill for skill in requirements["must_have"] if skill not in removed_skills
            ]
            requirements["nice_to_have"] = [
                skill for skill in requirements["nice_to_have"] if skill not in removed_skills
            ]
    else:
        requirements = extracted
    return {"requirements": requirements}


def _search_node(state: AgentState) -> dict[str, Any]:
    requirements = state.get("requirements", {})
    search_terms = " ".join(
        requirements.get("must_have", [])
        + requirements.get("nice_to_have", [])
        + requirements.get("keywords", [])
    )
    candidates = search_resumes(
        search_terms or state.get("jd", ""),
        resume_dir=state.get("resume_dir", "resumes"),
        limit=100,
    )
    # Round one retrieves broadly; detailed screening evaluates only the top ten.
    total_candidate_count = len(candidates)
    candidates = candidates[:10]
    return {"candidates": candidates, "total_candidate_count": total_candidate_count}


def _rank_node(state: AgentState) -> dict[str, Any]:
    requirements = state.get("requirements", {})
    must_have = requirements.get("must_have", [])
    nice_to_have = requirements.get("nice_to_have", [])
    min_years = requirements.get("min_years")
    ranked: list[Candidate] = []
    reasoning: dict[str, str] = {}

    for original in state.get("candidates", []):
        candidate = dict(original)
        skills = candidate.get("skills", [])
        matched_must = [skill for skill in must_have if skill in skills]
        missing_must = [skill for skill in must_have if skill not in skills]
        matched_nice = [skill for skill in nice_to_have if skill in skills]
        years = candidate.get("years_experience")
        experience_match = min_years is None or (years is not None and years >= min_years)
        denominator = max(1, len(must_have) + len(nice_to_have) + (1 if min_years else 0))
        points = len(matched_must) * 70 / max(1, len(must_have))
        points += len(matched_nice) * 20 / max(1, len(nice_to_have)) if nice_to_have else 0
        points += 10 if experience_match and min_years is not None else 0
        score = min(100, points * (1 if must_have or nice_to_have or min_years else 0))
        # Normalize the weighted score when only a subset of requirement types is present.
        available_weight = (70 if must_have else 0) + (20 if nice_to_have else 0) + (10 if min_years is not None else 0)
        score = round(score * 100 / max(1, available_weight), 1)
        strengths = matched_must + matched_nice
        if experience_match and min_years is not None:
            strengths.append(f"{years:g}+ years experience" if years is not None else "Experience threshold met")
        gaps = missing_must[:]
        if min_years is not None and not experience_match:
            gaps.append(f"at least {min_years:g} years experience")
        if nice_to_have and len(matched_nice) < len(nice_to_have):
            gaps.extend(skill for skill in nice_to_have if skill not in matched_nice)
        if score >= 70 and not missing_must and experience_match:
            recommendation = "Hire recommendation"
        elif score >= 45:
            recommendation = "Borderline - further screening recommended"
        else:
            recommendation = "No-hire recommendation"
        candidate.update(
            {
                "score": score,
                "matched_must_have": matched_must,
                "missing_must_have": missing_must,
                "matched_nice_to_have": matched_nice,
                "strengths": strengths,
                "gaps": list(dict.fromkeys(gaps)),
                "recommendation": recommendation,
                "reasoning": (
                    f"Matched {len(matched_must)}/{len(must_have)} must-have skills, "
                    f"{len(matched_nice)}/{len(nice_to_have)} nice-to-have skills; "
                    f"{'meets' if experience_match else 'does not meet'} the experience threshold."
                ),
                "improvement_suggestion": (
                    "Ask for project evidence covering: " + ", ".join(gaps)
                    if recommendation.startswith("Borderline")
                    else ""
                ),
            }
        )
        ranked.append(candidate)
        reasoning[candidate["id"]] = candidate["reasoning"]

    ranked.sort(key=lambda item: (item["score"], item.get("retrieval_score", 0)), reverse=True)
    _CANDIDATE_INDEX.update({candidate["id"]: candidate for candidate in ranked})
    return {"candidate_shortlist": ranked, "reasoning": reasoning}


def _find_candidate(query: str, candidates: list[Candidate]) -> Candidate | None:
    lowered = query.lower()
    return next(
        (candidate for candidate in candidates if candidate["name"].lower() in lowered),
        None,
    )


def _report_node(state: AgentState) -> dict[str, Any]:
    ranked = state.get("candidate_shortlist", [])
    requirements = state.get("requirements", {})
    intent = state.get("intent", "search")
    query = state.get("user_query", "")
    if intent == "compare":
        ids = [candidate["id"] for candidate in ranked[:3]]
        response = compare_candidates(ids) if len(ids) >= 2 else "Not enough candidates to compare."
    elif intent == "interview":
        candidate = _find_candidate(query, ranked)
        if candidate is None and ranked:
            candidate = ranked[0]
        response = (
            "\n".join(f"- {question}" for question in generate_interview_questions(candidate["id"]))
            if candidate else "No candidate is available for interview-question generation."
        )
    elif intent == "explain":
        named = [candidate for candidate in ranked if candidate["name"].lower() in query.lower()]
        if len(named) >= 2:
            named.sort(key=lambda item: item["score"], reverse=True)
            high, low = named[0], named[-1]
            response = (
                f"{high['name']} ranked higher ({high['score']:.0f}% vs {low['score']:.0f}%) because "
                f"{high['reasoning']} {low['name']}: {low['reasoning']}"
            )
        elif named:
            candidate = named[0]
            response = f"{candidate['name']} scored {candidate['score']:.0f}%. {candidate['reasoning']}"
        else:
            response = "No named candidates from the current shortlist matched that question."
    else:
        if not ranked:
            response = "No resumes were found. Add TXT, Markdown, PDF, or DOCX files to the resume folder."
        else:
            lines = [
                f"Retrieved {state.get('total_candidate_count', len(ranked))} resumes and "
                f"detailed-screened the top {len(ranked)}. Requirements: must-have "
                f"{', '.join(requirements.get('must_have', [])) or 'not specified'}; "
                f"nice-to-have {', '.join(requirements.get('nice_to_have', [])) or 'not specified'}; "
                f"minimum experience {requirements.get('min_years') or 'not specified'} years.",
                "",
            ]
            for index, candidate in enumerate(ranked, start=1):
                lines.append(
                    f"{index}. {candidate['name']} - {candidate['score']:.0f}% "
                    f"({candidate['recommendation']})"
                )
                lines.append(f"   Strengths: {', '.join(candidate['strengths']) or 'none identified'}")
                lines.append(f"   Gaps: {', '.join(candidate['gaps']) or 'none identified'}")
                lines.append(f"   Reasoning: {candidate['reasoning']}")
                if candidate["improvement_suggestion"]:
                    lines.append(f"   Next step: {candidate['improvement_suggestion']}")
            response = "\n".join(lines)
    history = list(state.get("conversation_history", []))
    history.append({"role": "assistant", "content": response})
    return {"response": response, "report": response, "conversation_history": history}


def _feedback_node(state: AgentState) -> dict[str, Any]:
    feedback = state.get("human_feedback", "").strip()
    round_number = state.get("refinement_round", 0)
    max_rounds = state.get("max_refinement_rounds", 3)
    if not feedback or round_number >= max_rounds:
        return {"human_feedback": "", "should_refine": False}
    history = list(state.get("conversation_history", []))
    history.append({"role": "user", "content": f"Refinement: {feedback}"})
    return {
        "jd": feedback,
        "human_feedback": "",
        "refinement_round": round_number + 1,
        "intent": "search",
        "should_refine": True,
        "conversation_history": history,
    }


def _route_feedback(state: AgentState) -> Literal["refine", "finish"]:
    return "refine" if state.get("should_refine", False) else "finish"


def build_agent():
    """Construct the compiled LangGraph state machine."""
    workflow = StateGraph(AgentState)
    workflow.add_node("parse_jd", _parse_jd)
    workflow.add_node("extract_requirements", _extract_node)
    workflow.add_node("search_resumes", _search_node)
    workflow.add_node("rank_candidates", _rank_node)
    workflow.add_node("generate_report", _report_node)
    workflow.add_node("human_feedback", _feedback_node)
    workflow.add_edge(START, "parse_jd")
    workflow.add_edge("parse_jd", "extract_requirements")
    workflow.add_edge("extract_requirements", "search_resumes")
    workflow.add_edge("search_resumes", "rank_candidates")
    workflow.add_edge("rank_candidates", "generate_report")
    workflow.add_edge("generate_report", "human_feedback")
    workflow.add_conditional_edges(
        "human_feedback",
        _route_feedback,
        {"refine": "extract_requirements", "finish": END},
    )
    return workflow.compile()


agent = build_agent()
