from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


DEFAULT_MODEL = "gemini-3.5-flash"


class AgentExecutionError(RuntimeError):
    def __init__(self, feature: str, message: str) -> None:
        super().__init__(message)
        self.feature = feature


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
    "Real Estate Law": [
        "closing",
        "eviction",
        "landlord",
        "lease",
        "property",
        "real estate",
        "tenant",
        "title",
    ],
}


@dataclass
class AgentStep:
    name: str
    role: str
    status: str
    summary: str
    used_model: bool = True
    details: Dict[str, Any] = field(default_factory=dict)
    children: List["AgentStep"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "role": self.role,
            "status": self.status,
            "summary": self.summary,
            "used_model": self.used_model,
            "details": self.details,
            "children": [child.to_dict() for child in self.children],
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
        temperature: float = 0.22,
    ) -> None:
        self.model = model or os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.temperature = temperature
        self.last_error: Optional[str] = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def generate_text(self, feature: str, prompt: str) -> str:
        return self._generate(feature, prompt, json_mode=False)

    def generate_json(self, feature: str, prompt: str) -> Dict[str, Any]:
        text = self._generate(feature, prompt, json_mode=True)
        parsed = parse_json_text(text)
        if parsed is None:
            raise AgentExecutionError(feature, f"{feature} returned malformed JSON.")
        return parsed

    def _generate(self, feature: str, prompt: str, json_mode: bool) -> str:
        if not self.api_key:
            raise AgentExecutionError(feature, "Gemini is not configured. Add GEMINI_API_KEY to .env.")

        try:
            from google import genai
            from google.genai import types
        except Exception as exc:  # pragma: no cover - depends on local env
            self.last_error = str(exc)
            raise AgentExecutionError(feature, "Gemini SDK is not installed or cannot be imported.") from exc

        try:
            client = genai.Client(api_key=self.api_key)
            config_kwargs: Dict[str, Any] = {"temperature": self.temperature}
            if json_mode:
                config_kwargs["response_mime_type"] = "application/json"
            config = types.GenerateContentConfig(**config_kwargs)
            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )
        except Exception as exc:  # pragma: no cover - requires live Gemini
            self.last_error = str(exc)
            raise AgentExecutionError(feature, f"{feature} could not reach Gemini.") from exc

        text = response_text(response)
        if not text.strip():
            raise AgentExecutionError(feature, f"{feature} returned an empty response.")
        return text.strip()


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

    def match_terms(self, message: str) -> List[str]:
        message_lower = message.lower()
        message_tokens = set(tokenize(message))
        matched: List[str] = []
        for case in self.cases:
            case_type = case["Case Type"]
            corpus_tokens = set(tokenize(case_type + " " + " ".join(CASE_ALIASES.get(case_type, []))))
            matched.extend(sorted(message_tokens.intersection(corpus_tokens)))
            for alias in CASE_ALIASES.get(case_type, []):
                if alias in message_lower:
                    matched.append(alias)
        return sorted(set(matched))[:10]


class IntakeAgent:
    def __init__(self, gateway: GeminiGateway, matcher: CaseMatcher, cases: Sequence[Dict[str, Any]]) -> None:
        self.gateway = gateway
        self.matcher = matcher
        self.cases = cases

    def run(self, message: str) -> Tuple[Dict[str, Any], AgentStep]:
        case_names = [case["Case Type"] for case in self.cases]
        matched_terms = self.matcher.match_terms(message)
        payload = self.gateway.generate_json(
            "IntakeAgent",
            "\n".join(
                [
                    "You are IntakeAgent for LawyerUP, a legal intake routing product.",
                    "Classify the user's matter without giving legal advice.",
                    "Return JSON with keys: case_type, confidence, urgency, summary, facts, missing_info.",
                    "confidence must be a number between 0 and 1.",
                    "urgency must be one of routine, medium, high.",
                    f"Allowed case_type values: {', '.join(case_names)}. Use Unknown if none fit.",
                    f"Local lexical hints: {', '.join(matched_terms) if matched_terms else 'none'}",
                    f"User message: {message}",
                ]
            ),
        )

        case_type = self.matcher.canonical_case_type(str(payload.get("case_type", ""))) or "Unknown"
        confidence = payload.get("confidence", 0)
        if not isinstance(confidence, (int, float)):
            raise AgentExecutionError("IntakeAgent", "IntakeAgent returned an invalid confidence value.")

        urgency = str(payload.get("urgency", "routine")).lower()
        if urgency not in {"routine", "medium", "high"}:
            raise AgentExecutionError("IntakeAgent", "IntakeAgent returned an invalid urgency value.")

        assessment = {
            "case_type": case_type,
            "case_id": self._case_id(case_type),
            "confidence": round(max(0.0, min(float(confidence), 0.99)), 2),
            "urgency": urgency,
            "summary": compact_text(str(payload.get("summary", "")), 420),
            "facts": as_list(payload.get("facts"))[:5],
            "matched_terms": matched_terms,
            "missing_info": as_list(payload.get("missing_info"))[:4],
        }

        if not assessment["summary"] or not assessment["facts"]:
            raise AgentExecutionError("IntakeAgent", "IntakeAgent returned an incomplete intake brief.")

        step = AgentStep(
            name="IntakeAgent",
            role="Classifies matter type and extracts the clean intake brief.",
            status="gemini-required",
            summary=f"Routed to {assessment['case_type']} with {int(assessment['confidence'] * 100)}% confidence.",
            details={"model": self.gateway.model, "matched_terms": matched_terms},
        )
        return assessment, step

    def _case_id(self, case_type: str) -> Optional[int]:
        for case in self.cases:
            if case["Case Type"] == case_type:
                return case.get("Case ID")
        return None


class TriageAgent:
    def __init__(self, gateway: GeminiGateway) -> None:
        self.gateway = gateway

    def run(self, message: str, assessment: Dict[str, Any]) -> Tuple[Dict[str, Any], AgentStep]:
        payload = self.gateway.generate_json(
            "TriageAgent",
            "\n".join(
                [
                    "You are TriageAgent for LawyerUP.",
                    "Return JSON with keys: next_questions, risk_flags, intake_priority.",
                    "intake_priority must be one of standard, priority, same-day.",
                    "Write practical intake questions. Do not provide legal advice.",
                    "Do not cite statutes, day counts, year counts, jurisdiction-specific deadlines, or exact filing windows.",
                    "Phrase risk_flags as possible intake concerns that require attorney review, not legal conclusions.",
                    f"Assessment: {json.dumps(assessment, ensure_ascii=False)}",
                    f"Original message: {message}",
                ]
            ),
        )

        priority = str(payload.get("intake_priority", "")).lower()
        if priority not in {"standard", "priority", "same-day"}:
            raise AgentExecutionError("TriageAgent", "TriageAgent returned an invalid priority.")

        triage = {
            "next_questions": self._dedupe(as_list(payload.get("next_questions")))[:4],
            "risk_flags": self._safe_risk_flags(as_list(payload.get("risk_flags")))[:4],
            "intake_priority": priority,
        }
        if not triage["next_questions"]:
            raise AgentExecutionError("TriageAgent", "TriageAgent did not return next questions.")

        step = AgentStep(
            name="TriageAgent",
            role="Identifies missing intake facts and time-sensitive signals.",
            status="parallel-gemini",
            summary=f"Marked as {priority} intake with {len(triage['next_questions'])} follow-up questions.",
            details={"risk_flags": triage["risk_flags"]},
        )
        return triage, step

    def _dedupe(self, values: Iterable[str]) -> List[str]:
        seen = set()
        output = []
        for value in values:
            cleaned = compact_text(value, 180)
            key = cleaned.lower()
            if cleaned and key not in seen:
                seen.add(key)
                output.append(cleaned)
        return output

    def _safe_risk_flags(self, values: Iterable[str]) -> List[str]:
        guarded = []
        risky_pattern = re.compile(
            r"\b(\d+\s*(day|days|year|years)|statute|pip|florida|deadline|filing window|"
            r"compromise the claim|compromising the claim|legal action)\b",
            re.IGNORECASE,
        )
        for value in self._dedupe(values):
            lower_value = value.lower()
            if risky_pattern.search(value):
                if "statement" in lower_value or "adjuster" in lower_value or "insurance" in lower_value:
                    value = "Insurance contact history needs attorney review before any statement-related recommendation."
                elif "medical" in lower_value or "pain" in lower_value or "treatment" in lower_value:
                    value = "Medical treatment history is missing and should be documented for attorney review."
                else:
                    value = "Possible timing issue that needs attorney review before any deadline conclusion."
            elif "attorney review" not in lower_value:
                value = f"{value} Attorney review is needed before any conclusion."
            if value and value not in guarded:
                guarded.append(value)
        return guarded


class DeadlineSignalAgent:
    def __init__(self, gateway: GeminiGateway) -> None:
        self.gateway = gateway

    def run(self, message: str, assessment: Dict[str, Any]) -> Tuple[Dict[str, Any], AgentStep]:
        payload = self.gateway.generate_json(
            "DeadlineSignalAgent",
            "\n".join(
                [
                    "You are DeadlineSignalAgent for LawyerUP.",
                    "Return JSON with keys: deadline_signals, time_sensitive_actions.",
                    "Flag possible timing concerns in plain language for the intake team.",
                    "Do not give legal advice or tell the user what to do.",
                    "Do not tell the user to decline, avoid, hire, consult, contact counsel, or provide/refuse a statement.",
                    "Frame time_sensitive_actions as neutral intake data collection and attorney-review routing tasks.",
                    "Do not cite statutes, day counts, year counts, filing windows, jurisdiction-specific rules, or exact legal deadlines.",
                    "Every item must say that attorney review is needed before any deadline conclusion.",
                    f"Assessment: {json.dumps(assessment, ensure_ascii=False)}",
                    f"Original message: {message}",
                ]
            ),
        )
        data = {
            "deadline_signals": self._safe_deadline_items(as_list(payload.get("deadline_signals")))[:4],
            "time_sensitive_actions": self._safe_action_items(as_list(payload.get("time_sensitive_actions")))[:4],
        }
        step = AgentStep(
            name="DeadlineSignalAgent",
            role="Reviews the matter for time-sensitive intake signals.",
            status="spawned-gemini",
            summary=f"Found {len(data['deadline_signals'])} possible deadline signals.",
            details=data,
        )
        return data, step

    def _safe_deadline_items(self, values: Sequence[str]) -> List[str]:
        guarded = []
        risky_pattern = re.compile(
            r"\b(\d+\s*(day|days|year|years)|statute|requires|required|must|deadline is|filing window|"
            r"without representation|compromising the claim|critical period|immediate risk)\b",
            re.IGNORECASE,
        )
        for value in values:
            cleaned = compact_text(value, 220)
            if risky_pattern.search(cleaned):
                cleaned = "Possible timing issue that needs attorney review before any deadline or strategy conclusion."
            elif "attorney review" not in cleaned.lower():
                cleaned = f"{cleaned} Attorney review is needed before any deadline conclusion."
            if cleaned and cleaned not in guarded:
                guarded.append(cleaned)
        return guarded

    def _safe_action_items(self, values: Sequence[str]) -> List[str]:
        guarded = []
        advice_pattern = re.compile(
            r"\b(decline|do not|don't|avoid|refuse|consult|hire|contact counsel|secure legal counsel|"
            r"without legal counsel|without representation|provide any recorded|recorded statement|"
            r"written statement|as soon as possible|must|should not)\b",
            re.IGNORECASE,
        )
        for value in values:
            cleaned = compact_text(value, 220)
            cleaned = re.sub(r"\bimmediately\b", "promptly", cleaned, flags=re.IGNORECASE)
            if advice_pattern.search(cleaned):
                lower_value = cleaned.lower()
                if "statement" in lower_value or "adjuster" in lower_value or "insurance" in lower_value:
                    cleaned = (
                        "Record the insurance contact history and whether any statement has been requested "
                        "or provided before attorney review."
                    )
                elif "medical" in lower_value or "treatment" in lower_value or "pain" in lower_value:
                    cleaned = "Collect medical evaluation dates, provider names, symptoms, and records for attorney review."
                else:
                    cleaned = "Route the timing concern for attorney review before recommending any action."
            if cleaned and cleaned not in guarded:
                guarded.append(cleaned)
        return guarded


class EvidenceChecklistAgent:
    def __init__(self, gateway: GeminiGateway) -> None:
        self.gateway = gateway

    def run(self, message: str, assessment: Dict[str, Any]) -> Tuple[Dict[str, Any], AgentStep]:
        payload = self.gateway.generate_json(
            "EvidenceChecklistAgent",
            "\n".join(
                [
                    "You are EvidenceChecklistAgent for LawyerUP.",
                    "Return JSON with keys: evidence_checklist, document_requests.",
                    "List useful documents or facts the intake team should request. Do not give legal advice.",
                    f"Assessment: {json.dumps(assessment, ensure_ascii=False)}",
                    f"Original message: {message}",
                ]
            ),
        )
        data = {
            "evidence_checklist": as_list(payload.get("evidence_checklist"))[:5],
            "document_requests": as_list(payload.get("document_requests"))[:5],
        }
        step = AgentStep(
            name="EvidenceChecklistAgent",
            role="Builds the evidence and document request checklist.",
            status="spawned-gemini",
            summary=f"Prepared {len(data['document_requests'])} document requests.",
            details=data,
        )
        return data, step


class SubagentCoordinator:
    def __init__(self, gateway: GeminiGateway) -> None:
        self.deadline_agent = DeadlineSignalAgent(gateway)
        self.evidence_agent = EvidenceChecklistAgent(gateway)

    def run(self, message: str, assessment: Dict[str, Any]) -> Tuple[Dict[str, Any], AgentStep]:
        agents = {
            "deadlines": lambda: self.deadline_agent.run(message, assessment),
            "evidence": lambda: self.evidence_agent.run(message, assessment),
        }
        results: Dict[str, Any] = {}
        children: List[AgentStep] = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(agent): key for key, agent in agents.items()}
            for future in as_completed(futures):
                key = futures[future]
                data, step = future.result()
                results[key] = data
                children.append(step)

        step = AgentStep(
            name="SubagentCoordinator",
            role="Spawns focused deadline and evidence subagents when a matter is reviewed.",
            status="spawned-parallel",
            summary=f"Completed {len(children)} spawned subagents.",
            details={"spawned": [child.name for child in children]},
            children=sorted(children, key=lambda item: item.name),
        )
        return results, step


class AttorneyMatchAgent:
    def __init__(self, lawyers: Sequence[Dict[str, Any]], cases: Sequence[Dict[str, Any]]) -> None:
        self.lawyers = lawyers
        self.cases_by_type = {case["Case Type"]: case for case in cases}

    def run(self, assessment: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], AgentStep]:
        case_type = assessment.get("case_type", "Unknown")
        case = self.cases_by_type.get(case_type)
        recommended_sequence = case.get("Recommended Lawyer ID", []) if case else []
        recommended_ids = set(recommended_sequence)
        recommended_rank = {lawyer_id: index for index, lawyer_id in enumerate(recommended_sequence)}

        matches: List[Dict[str, Any]] = []
        for lawyer in self.lawyers:
            score, reasons = self._score_lawyer(lawyer, case_type, recommended_ids, recommended_rank)
            if score >= 26:
                matches.append(self._format_match(lawyer, score, reasons))

        matches.sort(key=lambda item: item["match_score"], reverse=True)
        selected = matches[:3]
        step = AgentStep(
            name="AttorneyMatchAgent",
            role="Ranks sample attorneys by practice fit, data-backed recommendation, and experience.",
            status="parallel-deterministic",
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
        subagent_results: Dict[str, Any],
        matches: Sequence[Dict[str, Any]],
    ) -> Tuple[str, AgentStep]:
        text = self.gateway.generate_text(
            "ResponseAgent",
            "\n".join(
                [
                    "You are ResponseAgent for LawyerUP, a legal intake routing product.",
                    "Write a concise response that summarizes the matter, asks the next questions, and names sample attorney matches.",
                    "Do not provide legal advice, promises, or definitive conclusions.",
                    "Do not say anyone will contact the user. Avoid assurances about representation or outcomes.",
                    "Use plain text only. Do not use Markdown, headings, bullets, bold, or italics.",
                    "Refer to attorney results as sample matches, not guaranteed representation.",
                    "Keep the response under 170 words.",
                    f"User message: {message}",
                    f"Assessment: {json.dumps(assessment, ensure_ascii=False)}",
                    f"Triage: {json.dumps(triage, ensure_ascii=False)}",
                    f"Subagent results: {json.dumps(subagent_results, ensure_ascii=False)}",
                    f"Attorney matches: {json.dumps(list(matches), ensure_ascii=False)}",
                ]
            ),
        )
        step = AgentStep(
            name="ResponseAgent",
            role="Composes the user-facing intake response from grounded agent outputs.",
            status="gemini-required",
            summary="Generated the final intake response.",
            details={"model": self.gateway.model},
        )
        return compact_text(text, 1100), step


class LegalAgentSystem:
    def __init__(self, lawyer_path: Path, case_path: Path) -> None:
        self.lawyers = load_json(lawyer_path)
        self.cases = load_json(case_path)
        self.gateway = GeminiGateway()
        self.matcher = CaseMatcher(self.cases)
        self.intake_agent = IntakeAgent(self.gateway, self.matcher, self.cases)
        self.triage_agent = TriageAgent(self.gateway)
        self.match_agent = AttorneyMatchAgent(self.lawyers, self.cases)
        self.subagent_coordinator = SubagentCoordinator(self.gateway)
        self.response_agent = ResponseAgent(self.gateway)

    def health(self) -> Dict[str, Any]:
        if not self.gateway.configured:
            status = "missing_configuration"
        elif self.gateway.last_error:
            status = "provider_error"
        else:
            status = "ready"

        return {
            "status": status,
            "model": self.gateway.model,
            "gemini_configured": self.gateway.configured,
            "last_model_error": self.gateway.last_error,
            "lawyer_count": len(self.lawyers),
            "case_count": len(self.cases),
            "fallbacks_enabled": False,
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
        clean_message = compact_text(message, 3000)
        steps: List[AgentStep] = []

        assessment, intake_step = self.intake_agent.run(clean_message)
        steps.append(intake_step)

        parallel_tasks = {
            "triage": lambda: self.triage_agent.run(clean_message, assessment),
            "matches": lambda: self.match_agent.run(assessment),
            "subagents": lambda: self.subagent_coordinator.run(clean_message, assessment),
        }
        parallel_results: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(task): name for name, task in parallel_tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                data, step = future.result()
                parallel_results[name] = data
                steps.append(step)

        triage = parallel_results["triage"]
        matches = parallel_results["matches"]
        subagent_results = parallel_results["subagents"]
        reply, response_step = self.response_agent.run(
            clean_message,
            assessment,
            triage,
            subagent_results,
            matches,
        )
        steps.append(response_step)

        return {
            "reply": reply,
            "case_assessment": assessment,
            "triage": triage,
            "recommended_lawyers": matches,
            "subagent_results": subagent_results,
            "agent_trace": [item.to_dict() for item in steps],
            "model": self.gateway.model,
            "mode": "gemini-required",
            "disclaimer": "LawyerUP is an intake routing product and does not provide legal advice.",
        }
