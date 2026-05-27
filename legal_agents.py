from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_MODEL = "gemini-3.5-flash"


STOPWORDS = {
    "a",
    "about",
    "after",
    "am",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "can",
    "did",
    "do",
    "for",
    "from",
    "got",
    "had",
    "has",
    "have",
    "help",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "need",
    "of",
    "on",
    "or",
    "our",
    "the",
    "they",
    "this",
    "to",
    "was",
    "we",
    "with",
}


CASE_ALIASES = {
    "Personal Injury": [
        "accident",
        "car accident",
        "crash",
        "injured",
        "injury",
        "insurance",
        "slip",
        "truck",
    ],
    "Medical Malpractice": [
        "doctor mistake",
        "hospital",
        "malpractice",
        "medical error",
        "misdiagnosis",
        "surgery",
    ],
    "DUI (Driving Under the Influence)": [
        "bac",
        "breathalyzer",
        "dui",
        "dwi",
        "field sobriety",
        "pulled over",
    ],
    "Criminal Defense": [
        "arrest",
        "arrested",
        "assault",
        "charged",
        "criminal",
        "felony",
        "misdemeanor",
        "theft",
    ],
    "Family Law": [
        "child custody",
        "custody",
        "family",
        "parenting plan",
        "support",
        "visitation",
    ],
    "Divorce": [
        "alimony",
        "divorce",
        "marriage",
        "separation",
        "spouse",
        "split assets",
    ],
    "Immigration": [
        "asylum",
        "citizenship",
        "deported",
        "green card",
        "immigration",
        "visa",
    ],
    "Employment Law": [
        "discrimination",
        "employer",
        "fired",
        "harassment",
        "retaliation",
        "termination",
        "wage",
        "workplace",
    ],
    "Business Law": [
        "business",
        "contract",
        "llc",
        "partnership",
        "shareholder",
        "vendor",
    ],
    "Estate Planning": [
        "estate",
        "probate",
        "trust",
        "will",
    ],
}


URGENCY_KEYWORDS = {
    "high": [
        "arrested",
        "court date",
        "deadline",
        "deported",
        "eviction",
        "hospital",
        "served",
        "trial",
        "warrant",
    ],
    "medium": [
        "charged",
        "fired",
        "insurance",
        "injured",
        "letter",
        "police",
        "terminated",
    ],
}


@dataclass
class AgentStep:
    name: str
    role: str
    status: str
    summary: str
    used_model: bool = False
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "status": self.status,
            "summary": self.summary,
            "used_model": self.used_model,
            "details": self.details,
        }


def load_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a JSON list.")
    return data


def tokenize(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [word for word in words if word not in STOPWORDS and len(word) > 1]


def compact_text(text: str, limit: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def response_text(response: Any) -> str:
    candidates = getattr(response, "candidates", None) or []
    parts: List[str] = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            value = getattr(part, "text", None)
            if value:
                parts.append(value)
    if parts:
        return "\n".join(parts)

    text = getattr(response, "text", None)
    return text or ""


def parse_json_text(text: str) -> Optional[Dict[str, Any]]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned)
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    return parsed if isinstance(parsed, dict) else None


class GeminiGateway:
    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.25,
    ) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.temperature = temperature
        self.last_error: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate_text(self, prompt: str) -> Optional[str]:
        return self._generate(prompt, json_mode=False)

    def generate_json(self, prompt: str) -> Optional[Dict[str, Any]]:
        text = self._generate(prompt, json_mode=True)
        if not text:
            return None
        return parse_json_text(text)

    def _generate(self, prompt: str, json_mode: bool) -> Optional[str]:
        if not self.api_key:
            return None

        try:
            from google import genai
            from google.genai import types
        except Exception as exc:  # pragma: no cover - depends on local env
            self.last_error = f"google-genai unavailable: {exc}"
            return None

        try:
            client = genai.Client(api_key=self.api_key)
            config_kwargs: Dict[str, Any] = {"temperature": self.temperature}
            if json_mode:
                config_kwargs["response_mime_type"] = "application/json"
            try:
                config = types.GenerateContentConfig(**config_kwargs)
            except Exception:
                config = config_kwargs
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:  # pragma: no cover - requires live Gemini
            self.last_error = str(exc)
            return None

        return response_text(response)


class CaseMatcher:
    def __init__(self, cases: Sequence[Dict[str, Any]]) -> None:
        self.cases = cases

    def canonical_case_type(self, value: str) -> Optional[str]:
        normalized = value.lower().strip()
        if not normalized:
            return None

        for case in self.cases:
            case_type = case["Case Type"]
            if normalized == case_type.lower():
                return case_type

        for case_type, aliases in CASE_ALIASES.items():
            if normalized == case_type.lower() or normalized in aliases:
                return case_type

        for case in self.cases:
            case_type = case["Case Type"]
            candidates = [case_type.lower()] + CASE_ALIASES.get(case_type, [])
            if any(candidate in normalized or normalized in candidate for candidate in candidates):
                return case_type

        return None

    def match(self, message: str) -> Tuple[Optional[Dict[str, Any]], float, List[str]]:
        message_lower = message.lower()
        message_tokens = set(tokenize(message))
        best_case: Optional[Dict[str, Any]] = None
        best_score = 0.0
        best_terms: List[str] = []

        for case in self.cases:
            case_type = case["Case Type"]
            aliases = CASE_ALIASES.get(case_type, [])
            corpus = " ".join(
                [
                    case_type,
                    case.get("Description", ""),
                    " ".join(case.get("Relevant Questions", [])),
                    " ".join(aliases),
                ]
            )
            corpus_tokens = set(tokenize(corpus))
            overlapping = sorted(message_tokens.intersection(corpus_tokens))
            score = float(len(overlapping) * 2)

            if case_type.lower() in message_lower:
                score += 6
                overlapping.append(case_type)

            for alias in aliases:
                if alias in message_lower:
                    score += 4 if " " in alias else 2
                    overlapping.append(alias)

            if score > best_score:
                best_case = case
                best_score = score
                best_terms = sorted(set(overlapping))

        if not best_case or best_score < 2:
            return None, 0.0, []

        confidence = min(0.94, 0.35 + best_score / 18)
        return best_case, round(confidence, 2), best_terms[:8]


class IntakeAgent:
    def __init__(self, gateway: GeminiGateway, matcher: CaseMatcher, cases: Sequence[Dict[str, Any]]) -> None:
        self.gateway = gateway
        self.matcher = matcher
        self.cases = cases

    def run(self, message: str) -> Tuple[Dict[str, Any], AgentStep]:
        local_case, local_confidence, matched_terms = self.matcher.match(message)
        case_names = [case["Case Type"] for case in self.cases]
        model_payload = self.gateway.generate_json(
            "\n".join(
                [
                    "You are IntakeAgent for LawyerUp, a legal intake routing demo.",
                    "Classify the user's message without giving legal advice.",
                    "Return JSON with keys: case_type, confidence, urgency, summary, facts, missing_info.",
                    f"Allowed case_type values: {', '.join(case_names)}. Use Unknown if none fit.",
                    f"User message: {message}",
                ]
            )
        )

        used_model = bool(model_payload)
        model_case_type = self.matcher.canonical_case_type(str(model_payload.get("case_type", ""))) if model_payload else None
        case = self._find_case(model_case_type) or local_case

        confidence = local_confidence
        if model_payload and isinstance(model_payload.get("confidence"), (int, float)):
            confidence = max(confidence, min(float(model_payload["confidence"]), 0.98))

        urgency = self._urgency(message)
        if model_payload and str(model_payload.get("urgency", "")).lower() in {"routine", "medium", "high"}:
            urgency = str(model_payload["urgency"]).lower()

        assessment = {
            "case_type": case["Case Type"] if case else "Unknown",
            "case_id": case.get("Case ID") if case else None,
            "confidence": round(confidence, 2) if case else 0.18,
            "urgency": urgency,
            "summary": compact_text(
                str(model_payload.get("summary", "")) if model_payload and model_payload.get("summary") else message
            ),
            "facts": as_list(model_payload.get("facts"))[:4] if model_payload else [compact_text(message, 140)],
            "matched_terms": matched_terms,
            "missing_info": self._missing_info(case, message, model_payload),
        }

        step = AgentStep(
            name="IntakeAgent",
            role="Classifies matter type and extracts the clean intake brief.",
            status="model-assisted" if used_model else "local-classifier",
            summary=f"Routed to {assessment['case_type']} with {int(assessment['confidence'] * 100)}% confidence.",
            used_model=used_model,
            details={
                "model": self.gateway.model if used_model else None,
                "matched_terms": matched_terms,
            },
        )
        return assessment, step

    def _find_case(self, case_type: Optional[str]) -> Optional[Dict[str, Any]]:
        if not case_type:
            return None
        for case in self.cases:
            if case["Case Type"] == case_type:
                return case
        return None

    def _missing_info(
        self,
        case: Optional[Dict[str, Any]],
        message: str,
        model_payload: Optional[Dict[str, Any]],
    ) -> List[str]:
        questions = as_list(model_payload.get("missing_info"))[:3] if model_payload else []
        if len(questions) >= 3:
            return questions

        message_lower = message.lower()
        for question in (case or {}).get("Relevant Questions", []):
            question_tokens = set(tokenize(question))
            if not question_tokens.intersection(tokenize(message_lower)):
                questions.append(question)
            if len(questions) == 3:
                break

        if not questions:
            questions = [
                "What happened, and when did it happen?",
                "Who else is involved?",
                "Do you have documents, photos, messages, or notices connected to it?",
            ]
        return questions[:3]

    def _urgency(self, message: str) -> str:
        message_lower = message.lower()
        if any(keyword in message_lower for keyword in URGENCY_KEYWORDS["high"]):
            return "high"
        if any(keyword in message_lower for keyword in URGENCY_KEYWORDS["medium"]):
            return "medium"
        return "routine"


class TriageAgent:
    def __init__(self, gateway: GeminiGateway) -> None:
        self.gateway = gateway

    def run(self, message: str, assessment: Dict[str, Any]) -> Tuple[Dict[str, Any], AgentStep]:
        prompt = "\n".join(
            [
                "You are TriageAgent for a legal intake routing demo.",
                "Return JSON with keys: next_questions, risk_flags, intake_priority.",
                "Write short, practical intake questions. Do not provide legal advice.",
                f"Assessment: {json.dumps(assessment, ensure_ascii=False)}",
                f"Original message: {message}",
            ]
        )
        model_payload = self.gateway.generate_json(prompt)
        used_model = bool(model_payload)

        next_questions = as_list(model_payload.get("next_questions"))[:3] if model_payload else []
        if len(next_questions) < 3:
            next_questions.extend(assessment.get("missing_info", []))

        risk_flags = as_list(model_payload.get("risk_flags"))[:3] if model_payload else []
        if not risk_flags:
            risk_flags = self._default_flags(message, assessment)

        priority = str(model_payload.get("intake_priority", "")) if model_payload else ""
        if priority.lower() not in {"standard", "priority", "same-day"}:
            priority = "same-day" if assessment.get("urgency") == "high" else "priority" if assessment.get("urgency") == "medium" else "standard"

        triage = {
            "next_questions": self._dedupe(next_questions)[:3],
            "risk_flags": self._dedupe(risk_flags)[:3],
            "intake_priority": priority,
        }

        step = AgentStep(
            name="TriageAgent",
            role="Identifies missing intake facts and time-sensitive signals.",
            status="model-assisted" if used_model else "rule-based",
            summary=f"Marked as {triage['intake_priority']} intake with {len(triage['next_questions'])} follow-up questions.",
            used_model=used_model,
            details={"risk_flags": triage["risk_flags"]},
        )
        return triage, step

    def _default_flags(self, message: str, assessment: Dict[str, Any]) -> List[str]:
        case_type = assessment.get("case_type")
        urgency = assessment.get("urgency")
        flags: List[str] = []
        if urgency == "high":
            flags.append("There may be an active deadline, court date, or immediate safety concern.")
        if case_type in {"Personal Injury", "Medical Malpractice"}:
            flags.append("Medical records, incident photos, and insurance contact details will matter.")
        if case_type in {"DUI (Driving Under the Influence)", "Criminal Defense"}:
            flags.append("Charging documents and hearing dates should be reviewed quickly.")
        if not flags:
            flags.append("The intake team should confirm dates, parties, documents, and preferred contact window.")
        return flags

    def _dedupe(self, values: Iterable[str]) -> List[str]:
        seen = set()
        output = []
        for value in values:
            cleaned = compact_text(value, 160)
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                output.append(cleaned)
        return output


class AttorneyMatchAgent:
    def __init__(self, lawyers: Sequence[Dict[str, Any]], cases: Sequence[Dict[str, Any]]) -> None:
        self.lawyers = lawyers
        self.cases_by_type = {case["Case Type"]: case for case in cases}

    def run(self, assessment: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], AgentStep]:
        case_type = assessment.get("case_type", "Unknown")
        case = self.cases_by_type.get(case_type)
        recommended_sequence = case.get("Recommended Lawyer ID", []) if case else []
        recommended_ids = set(recommended_sequence)
        recommended_rank = {
            lawyer_id: index for index, lawyer_id in enumerate(recommended_sequence)
        }

        matches: List[Dict[str, Any]] = []
        for lawyer in self.lawyers:
            score, reasons = self._score_lawyer(
                lawyer,
                case_type,
                recommended_ids,
                recommended_rank,
            )
            if score < 32 and recommended_ids:
                continue
            if score < 26 and not recommended_ids:
                continue
            matches.append(self._format_match(lawyer, score, reasons))

        matches.sort(key=lambda item: item["match_score"], reverse=True)
        selected = matches[:3]

        step = AgentStep(
            name="AttorneyMatchAgent",
            role="Ranks sample attorneys by practice fit, data-backed recommendation, and experience.",
            status="deterministic-grounding",
            summary=f"Selected {len(selected)} attorney matches from {len(self.lawyers)} sample profiles.",
            used_model=False,
            details={"recommended_ids": sorted(recommended_ids)},
        )
        return selected, step

    def _score_lawyer(
        self,
        lawyer: Dict[str, Any],
        case_type: str,
        recommended_ids: set,
        recommended_rank: Dict[int, int],
    ) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []
        lawyer_id = lawyer.get("Lawyer ID")
        expertise = lawyer.get("Areas of Expertise", [])
        expertise_text = " ".join(expertise)
        experience = int(lawyer.get("Experience", 0))

        if lawyer_id in recommended_ids:
            score += 42 + max(0, 10 - recommended_rank.get(lawyer_id, 0) * 4)
            reasons.append("listed by the case routing table")

        if case_type != "Unknown" and case_type.lower() in expertise_text.lower():
            score += 32
            reasons.append(f"focuses on {case_type.lower()}")
        else:
            overlap = set(tokenize(case_type)).intersection(tokenize(expertise_text))
            if overlap:
                score += 12 + len(overlap) * 5
                reasons.append("has overlapping practice experience")

        score += min(experience, 22)
        if experience >= 12:
            reasons.append(f"{experience} years of experience")

        if not reasons:
            reasons.append("general intake coverage")

        return min(score, 98), reasons[:3]

    def _format_match(self, lawyer: Dict[str, Any], score: int, reasons: Sequence[str]) -> Dict[str, Any]:
        contact = lawyer.get("Contact Information", {})
        return {
            "id": lawyer.get("Lawyer ID"),
            "name": lawyer.get("Lawyer's Name"),
            "role": lawyer.get("Role", "Attorney"),
            "location": lawyer.get("Location", "Remote intake"),
            "email": contact.get("Email"),
            "phone": contact.get("Phone"),
            "expertise": lawyer.get("Areas of Expertise", []),
            "experience": lawyer.get("Experience"),
            "languages": lawyer.get("Languages", ["English"]),
            "match_score": score,
            "reason": "; ".join(reasons),
            "intake_note": lawyer.get("Intake Notes", "Available for an intake review."),
        }


class ResponseAgent:
    def __init__(self, gateway: GeminiGateway) -> None:
        self.gateway = gateway

    def run(
        self,
        message: str,
        assessment: Dict[str, Any],
        triage: Dict[str, Any],
        matches: Sequence[Dict[str, Any]],
    ) -> Tuple[str, AgentStep]:
        prompt = "\n".join(
            [
                "You are ResponseAgent for LawyerUp, a legal intake routing demo.",
                "Write a warm, concise response that summarizes the matter, asks the next questions, and names attorney matches.",
                "Do not provide legal advice, promises, or definitive conclusions.",
                "Use plain text only. Do not use Markdown, bold, italics, headings, or bullets.",
                "Refer to matches as sample attorney matches, not guaranteed representation.",
                "Keep the response under 180 words.",
                f"User message: {message}",
                f"Assessment: {json.dumps(assessment, ensure_ascii=False)}",
                f"Triage: {json.dumps(triage, ensure_ascii=False)}",
                f"Attorney matches: {json.dumps(list(matches), ensure_ascii=False)}",
            ]
        )
        model_text = self.gateway.generate_text(prompt)
        used_model = bool(model_text)
        reply = compact_text(model_text, 1100) if model_text else self._fallback_reply(assessment, triage, matches)

        step = AgentStep(
            name="ResponseAgent",
            role="Composes the user-facing intake response from grounded agent outputs.",
            status="model-assisted" if used_model else "template-fallback",
            summary="Generated the final intake response.",
            used_model=used_model,
            details={"model": self.gateway.model if used_model else None},
        )
        return reply, step

    def _fallback_reply(
        self,
        assessment: Dict[str, Any],
        triage: Dict[str, Any],
        matches: Sequence[Dict[str, Any]],
    ) -> str:
        case_type = assessment.get("case_type", "Unknown")
        summary = assessment.get("summary") or "your situation"

        lines = [
            f"I read this as a {case_type.lower()} intake based on: {summary}",
            "",
            "The next useful details are:",
        ]
        lines.extend(f"{index}. {question}" for index, question in enumerate(triage.get("next_questions", []), start=1))

        if matches:
            lines.append("")
            lines.append("Good starting matches:")
            for lawyer in matches:
                lines.append(
                    f"- {lawyer['name']}, {lawyer['role']} ({lawyer['match_score']}% fit): {lawyer['reason']}."
                )
        else:
            lines.append("")
            lines.append("I do not have enough detail yet to route this to a specific attorney.")

        lines.append("")
        lines.append("This is intake routing only, not legal advice.")
        return "\n".join(lines)


class LegalAgentSystem:
    def __init__(self, lawyer_path: Path, case_path: Path) -> None:
        self.lawyers = load_json(lawyer_path)
        self.cases = load_json(case_path)
        self.gateway = GeminiGateway()
        self.matcher = CaseMatcher(self.cases)
        self.intake_agent = IntakeAgent(self.gateway, self.matcher, self.cases)
        self.triage_agent = TriageAgent(self.gateway)
        self.match_agent = AttorneyMatchAgent(self.lawyers, self.cases)
        self.response_agent = ResponseAgent(self.gateway)

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "model": self.gateway.model,
            "gemini_configured": self.gateway.configured,
            "last_model_error": self.gateway.last_error,
            "lawyer_count": len(self.lawyers),
            "case_count": len(self.cases),
        }

    def case_options(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": case.get("Case ID"),
                "case_type": case.get("Case Type"),
                "description": case.get("Description"),
            }
            for case in self.cases
        ]

    def run(self, message: str) -> Dict[str, Any]:
        clean_message = compact_text(message, 1200)
        steps: List[AgentStep] = []

        assessment, step = self.intake_agent.run(clean_message)
        steps.append(step)

        triage, step = self.triage_agent.run(clean_message, assessment)
        steps.append(step)

        matches, step = self.match_agent.run(assessment)
        steps.append(step)

        reply, step = self.response_agent.run(clean_message, assessment, triage, matches)
        steps.append(step)

        return {
            "reply": reply,
            "case_assessment": assessment,
            "triage": triage,
            "recommended_lawyers": matches,
            "agent_trace": [item.to_dict() for item in steps],
            "model": self.gateway.model,
            "mode": "gemini-assisted" if any(item.used_model for item in steps) else "local-fallback",
            "disclaimer": "LawyerUp is an intake routing prototype and does not provide legal advice.",
        }
