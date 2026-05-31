"""RAG / Agent değerlendirme scripti — HTTP API üzerinden ölçülebilir test.

Çalıştırma (proje kökünden):
    export PYTHONPATH=.
    python scripts/evaluate_rag.py --base-url http://localhost:8000 --flush-cache

Önce backend ayakta olmalı (ör. docker compose up).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_QUESTIONS_FILE = PROJECT_ROOT / "data" / "evaluation" / "eval_questions.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "evaluation"

BACKEND_UNREACHABLE_MSG = (
    "Backend is not reachable. Start docker compose up first."
)

FALLBACK_MARKERS = (
    "yeterli bilgi bulamadım",
    "yeterli bilgi yok",
    "doğrulanmış kaynaklarda",
    "kesin cevap veremiyorum",
    "bulunamadı",
    "eldeki kaynaklarda",
    "güvenli fallback",
)

TOOL_TO_INTENT: dict[str, str] = {
    "process_navigator": "process_guidance",
    "rag_search": "rag_question",
    "resource_recommender": "resource_recommendation",
    "redis_cache": "rag_question",
}


def _load_env() -> None:
    from backend.app.core.config import load_env

    load_env(reload_settings=True)


def _infer_intent_from_tool(selected_tool: str | None, question: str) -> str | None:
    if not selected_tool:
        return None
    if selected_tool in TOOL_TO_INTENT:
        if selected_tool == "redis_cache":
            from backend.app.agent.intent import classify_intent_rules

            return classify_intent_rules(question) or "rag_question"
        return TOOL_TO_INTENT[selected_tool]
    if selected_tool.startswith("unsupported_"):
        return selected_tool.replace("unsupported_", "", 1)
    return None


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _keyword_score(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    answer_norm = _normalize(answer)
    hits = sum(1 for kw in keywords if _normalize(kw) in answer_norm)
    return hits / len(keywords)


def _fallback_detected(answer: str) -> bool:
    lower = answer.lower()
    return any(marker in lower for marker in FALLBACK_MARKERS)


def _check_backend(base_url: str) -> None:
    url = f"{base_url.rstrip('/')}/health"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            response.raise_for_status()
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise SystemExit(BACKEND_UNREACHABLE_MSG) from exc
    except httpx.HTTPStatusError as exc:
        raise SystemExit(
            f"{BACKEND_UNREACHABLE_MSG} (HTTP {exc.response.status_code})"
        ) from exc


def _flush_redis_cache() -> None:
    try:
        import redis

        from backend.app.core.config import get_settings

        settings = get_settings()
        if not settings.enable_redis_cache:
            print("Warning: Redis cache disabled in settings; nothing to flush.")
            return

        client = redis.from_url(settings.redis_url, socket_connect_timeout=3)
        client.ping()
        deleted = 0
        for key in client.scan_iter(match="answer_cache:*", count=200):
            client.delete(key)
            deleted += 1
        print(f"Redis cache flush: {deleted} answer_cache key(s) removed.")
    except Exception as exc:
        print(f"Warning: Redis cache flush failed ({exc}). Continuing evaluation.")


def _post_chat(base_url: str, question: str) -> tuple[dict[str, Any], int]:
    url = f"{base_url.rstrip('/')}/chat"
    payload = {"question": question.strip()}
    start = time.perf_counter()
    with httpx.Client(timeout=120.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
    latency_ms = int((time.perf_counter() - start) * 1000)
    return response.json(), latency_ms


def _failed_result(case: dict[str, Any], *, failure_reason: str) -> dict[str, Any]:
    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "question": case.get("question"),
        "expected_intent": case.get("expected_intent"),
        "expected_tool": case.get("expected_tool"),
        "actual_intent": None,
        "actual_tool": None,
        "intent_match": False,
        "tool_match": False,
        "keyword_score": 0.0,
        "has_sources": False,
        "source_requirement_passed": False,
        "fallback_detected": False,
        "latency_ms": 0,
        "passed": False,
        "failure_reason": failure_reason,
    }


def _evaluate_case(case: dict[str, Any], response: dict[str, Any], latency_ms: int) -> dict[str, Any]:
    question = case["question"]
    answer = response.get("answer") or ""
    selected_tool = response.get("selected_tool")
    citations = response.get("citations") or []
    agent_steps = response.get("agent_steps") or response.get("steps") or []

    actual_intent = _infer_intent_from_tool(selected_tool, question)
    expected_intent = case.get("expected_intent")
    expected_tool = case.get("expected_tool")
    expected_keywords = case.get("expected_keywords") or []
    must_have_source = bool(case.get("must_have_source"))
    category = case.get("category", "general")

    intent_match = actual_intent == expected_intent if actual_intent else False
    tool_match = selected_tool == expected_tool
    kw_score = _keyword_score(answer, expected_keywords)
    has_sources = len(citations) > 0
    source_requirement_passed = has_sources if must_have_source else True
    fallback = _fallback_detected(answer)

    api_duration_ms = None
    for log in response.get("tool_call_logs") or []:
        if isinstance(log, dict) and log.get("duration_ms") is not None:
            api_duration_ms = log.get("duration_ms")

    if category == "safety":
        route_ok = intent_match or tool_match or fallback
        kw_ok = kw_score >= 0.5 or fallback
        passed = route_ok and kw_ok and source_requirement_passed
    else:
        route_ok = intent_match or tool_match
        passed = route_ok and kw_score >= 0.5 and source_requirement_passed

    failure_reasons: list[str] = []
    if not (intent_match or tool_match) and category != "safety":
        failure_reasons.append("intent/tool mismatch")
    elif category == "safety" and not (intent_match or tool_match or fallback):
        failure_reasons.append("no safe route or fallback")
    if kw_score < 0.5 and not (category == "safety" and fallback):
        failure_reasons.append(f"keyword score {kw_score:.2f} < 0.5")
    if not source_requirement_passed:
        failure_reasons.append("source requirement not met")
    if not answer.strip():
        passed = False
        failure_reasons.append("empty answer")

    return {
        "id": case.get("id"),
        "category": category,
        "question": question,
        "expected_intent": expected_intent,
        "expected_tool": expected_tool,
        "actual_intent": actual_intent,
        "actual_tool": selected_tool,
        "intent_match": intent_match,
        "tool_match": tool_match,
        "keyword_score": round(kw_score, 3),
        "has_sources": has_sources,
        "source_requirement_passed": source_requirement_passed,
        "fallback_detected": fallback,
        "latency_ms": latency_ms,
        "api_logged_duration_ms": api_duration_ms,
        "passed": passed,
        "failure_reason": "; ".join(failure_reasons) if failure_reasons else "",
        "answer_preview": answer[:200] + ("…" if len(answer) > 200 else ""),
        "citation_count": len(citations),
        "agent_step_count": len(agent_steps),
    }


def _run_evaluation(
    cases: list[dict[str, Any]],
    base_url: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        test_id = case.get("id", "?")
        print(f"Running {test_id}…", flush=True)
        try:
            response, latency_ms = _post_chat(base_url, case["question"])
            result = _evaluate_case(case, response, latency_ms)
        except httpx.HTTPStatusError as exc:
            result = _failed_result(case, failure_reason=f"HTTP {exc.response.status_code}")
        except Exception as exc:
            result = _failed_result(case, failure_reason=str(exc)[:200])
        results.append(result)
    return results


def _build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    failed = total - passed

    intent_denom = sum(1 for r in results if r.get("actual_intent") is not None)
    tool_denom = sum(1 for r in results if r.get("actual_tool") is not None)

    intent_hits = sum(1 for r in results if r.get("intent_match"))
    tool_hits = sum(1 for r in results if r.get("tool_match"))

    kw_scores = [r.get("keyword_score", 0) for r in results if "keyword_score" in r]
    source_checks = [r for r in results if "source_requirement_passed" in r]
    latencies = [r.get("latency_ms", 0) for r in results if r.get("latency_ms")]

    return {
        "total_tests": total,
        "passed": passed,
        "failed": failed,
        "intent_accuracy": round(intent_hits / intent_denom, 3) if intent_denom else 0.0,
        "tool_accuracy": round(tool_hits / tool_denom, 3) if tool_denom else 0.0,
        "average_keyword_score": round(sum(kw_scores) / len(kw_scores), 3) if kw_scores else 0.0,
        "source_requirement_pass_rate": round(
            sum(1 for r in source_checks if r.get("source_requirement_passed"))
            / len(source_checks),
            3,
        )
        if source_checks
        else 0.0,
        "average_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0.0,
    }


def _print_summary(summary: dict[str, Any], results: list[dict[str, Any]]) -> None:
    print("\n" + "=" * 60)
    print("Evaluation Summary")
    print("=" * 60)
    print(f"- Total tests: {summary['total_tests']}")
    print(f"- Passed: {summary['passed']}")
    print(f"- Failed: {summary['failed']}")
    print(f"- Intent accuracy: {summary['intent_accuracy']:.1%}")
    print(f"- Tool accuracy: {summary['tool_accuracy']:.1%}")
    print(f"- Average keyword score: {summary['average_keyword_score']:.3f}")
    print(f"- Source requirement pass rate: {summary['source_requirement_pass_rate']:.1%}")
    print(f"- Average latency: {summary['average_latency_ms']} ms")
    print("\nPer-test results:")
    print("-" * 60)
    for r in results:
        q = (r.get("question") or "")[:50]
        if len(r.get("question") or "") > 50:
            q += "…"
        status = "PASS" if r.get("passed") else "FAIL"
        print(
            f"  [{status}] {r.get('id')} ({r.get('category')}) | "
            f"tool: {r.get('actual_tool')} (exp {r.get('expected_tool')}) | "
            f"{r.get('latency_ms', 0)} ms"
        )
        if r.get("question"):
            print(f"         Q: {q}")
        if not r.get("passed") and r.get("failure_reason"):
            print(f"         Reason: {r.get('failure_reason')}")


def _write_reports(
    *,
    output_dir: Path,
    summary: dict[str, Any],
    results: list[dict[str, Any]],
    base_url: str,
    questions_file: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"eval_report_{ts}.json"
    md_path = output_dir / f"eval_report_{ts}.md"

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "questions_file": str(questions_file),
        "summary": summary,
        "results": results,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    failed = [r for r in results if not r.get("passed")]
    lines = [
        "# RAG / Agent Evaluation Report",
        "",
        "## Summary",
        f"- Date: {payload['generated_at']}",
        f"- Base URL: {base_url}",
        f"- Questions file: `{questions_file}`",
        f"- Total tests: {summary['total_tests']}",
        f"- Passed: {summary['passed']}",
        f"- Failed: {summary['failed']}",
        f"- Intent accuracy: {summary['intent_accuracy']:.1%}",
        f"- Tool accuracy: {summary['tool_accuracy']:.1%}",
        f"- Average keyword score: {summary['average_keyword_score']:.3f}",
        f"- Source requirement pass rate: {summary['source_requirement_pass_rate']:.1%}",
        f"- Average latency: {summary['average_latency_ms']} ms",
        "",
        "## Test Details",
        "",
    ]
    for r in results:
        lines.extend(
            [
                f"### {r.get('id')}",
                f"- Question: {r.get('question')}",
                f"- Expected intent/tool: `{r.get('expected_intent')}` / `{r.get('expected_tool')}`",
                f"- Actual intent/tool: `{r.get('actual_intent')}` / `{r.get('actual_tool')}`",
                f"- Keyword score: {r.get('keyword_score', 'n/a')}",
                f"- Source requirement passed: {r.get('source_requirement_passed', 'n/a')}",
                f"- Fallback detected: {r.get('fallback_detected', 'n/a')}",
                f"- Result: **{'PASS' if r.get('passed') else 'FAIL'}**",
                f"- Latency: {r.get('latency_ms', 0)} ms",
            ]
        )
        if r.get("failure_reason"):
            lines.append(f"- Failure reason: {r.get('failure_reason')}")
        lines.append("")

    lines.extend(["## Failed Tests", ""])
    if failed:
        for r in failed:
            lines.append(
                f"- **{r.get('id')}**: {r.get('failure_reason') or 'see details above'}"
            )
    else:
        lines.append("- None (all tests passed).")
    lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def _load_questions(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise SystemExit(f"Questions file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("Questions file must be a JSON array.")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG / Agent evaluation via HTTP API")
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_QUESTIONS_FILE,
        help="Evaluation questions JSON",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Backend base URL",
    )
    parser.add_argument(
        "--flush-cache",
        action="store_true",
        help="Flush Redis answer_cache keys before running tests",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Run only the first N questions",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for JSON/Markdown reports",
    )
    args = parser.parse_args()

    _load_env()
    _check_backend(args.base_url)

    if args.flush_cache:
        _flush_redis_cache()

    cases = _load_questions(args.file)
    if args.limit is not None:
        cases = cases[: max(0, args.limit)]

    print(f"Evaluating {len(cases)} question(s) against {args.base_url}")
    results = _run_evaluation(cases, args.base_url)
    summary = _build_summary(results)
    _print_summary(summary, results)

    json_path, md_path = _write_reports(
        output_dir=args.output_dir,
        summary=summary,
        results=results,
        base_url=args.base_url,
        questions_file=args.file,
    )
    print(f"\nReports saved:\n  {json_path}\n  {md_path}")

    sys.exit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
