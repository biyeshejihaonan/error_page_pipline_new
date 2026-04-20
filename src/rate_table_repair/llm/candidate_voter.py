import json
from pathlib import Path
from typing import Any, Dict, List

from rate_table_repair.llm.client import OpenAICompatibleClient
from rate_table_repair.llm.json_parser import parse_json_object
from rate_table_repair.schemas.evidence import EvidencePackage
from rate_table_repair.schemas.review import FinalJudgeResult, ReviewResult


PROMPT_PATH = Path(__file__).resolve().parents[3] / "prompts" / "candidate_vote.txt"


def _candidate_payload_from_review(source: str, result: ReviewResult) -> Dict[str, Any]:
    return {
        "source": source,
        "is_real_error": result.is_real_error,
        "confidence": result.confidence,
        "reason": result.reason,
        "target_location": result.target_location.model_dump(exclude_none=True),
        "correction": result.correction.model_dump(by_alias=True, exclude_none=True),
        "concerns": result.concerns[:3],
    }


def _candidate_payload_from_final(source: str, result: FinalJudgeResult) -> Dict[str, Any]:
    return {
        "source": source,
        "final_decision": result.final_decision,
        "should_modify_html": result.should_modify_html,
        "confidence": result.confidence,
        "reason": result.reason,
        "target_location": result.target_location.model_dump(exclude_none=True),
        "correction": result.correction.model_dump(by_alias=True, exclude_none=True),
        "patches": [
            {
                "target_location": patch.target_location.model_dump(exclude_none=True),
                "correction": patch.correction.model_dump(by_alias=True, exclude_none=True),
                "reason": patch.reason,
            }
            for patch in result.patches[:4]
        ],
    }


def _normalize_vote_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    scores = payload.get("scores")
    if not isinstance(scores, list):
        scores = []
    normalized_scores: List[Dict[str, Any]] = []
    for item in scores:
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        score = item.get("score")
        if not isinstance(source, str):
            continue
        try:
            score_value = int(score)
        except Exception:
            continue
        normalized_scores.append(
            {
                "source": source,
                "score": max(0, min(10, score_value)),
                "reason": str(item.get("reason") or ""),
            }
        )
    winner = payload.get("winner")
    return {
        "winner": winner if isinstance(winner, str) else "",
        "scores": normalized_scores,
    }


class CandidateVoter:
    def __init__(self, model_config, dry_run: bool = False) -> None:
        self.model_config = model_config
        self.dry_run = dry_run
        self.client = OpenAICompatibleClient(model_config) if not dry_run else None

    def vote(
        self,
        evidence: EvidencePackage,
        primary_result: ReviewResult,
        peer_result: ReviewResult,
        final_judge: FinalJudgeResult,
    ) -> Dict[str, Any]:
        if self.dry_run:
            return {
                "voter_model": str(self.model_config["name"]),
                "winner": "",
                "scores": [],
            }
        assert self.client is not None
        candidates = [
            _candidate_payload_from_review("primary", primary_result),
            _candidate_payload_from_review("peer", peer_result),
            _candidate_payload_from_final("final_judge", final_judge),
        ]
        extra = "候选结果：\n%s" % json.dumps(candidates, ensure_ascii=False, indent=2)
        prompt = self.client.build_prompt(
            PROMPT_PATH,
            evidence,
            extra_text=extra,
            html_limit=5000,
            table_limit=1800,
            max_tables=1,
        )
        raw_text = self.client.chat_json(
            str(self.model_config["model_id"]),
            prompt,
            evidence,
            image_first=False,
            max_tokens=2500,
        )
        raw_json = _normalize_vote_json(parse_json_object(raw_text))
        raw_json["voter_model"] = str(self.model_config["name"])
        raw_json["raw_text"] = raw_text
        return raw_json
