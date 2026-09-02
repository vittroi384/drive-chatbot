"""AI service — RAG 파이프라인 본체 (Search → Rerank → Generate → Validate).

이 모듈은 앱에서 **유일하게 generative AI API를 직접 호출**하는 곳이다
(다른 파일은 ai_service를 import만 한다 — 마스터 컨텍스트 원칙).

[SDK] google-genai (구 vertexai.generative_models는 2026-06-24 제거 예정 → 사용 안 함).
    - Vertex backend로 client 생성: genai.Client(vertexai=True, project, location)
    - 비동기 호출: client.aio.models.generate_content(...)
    - 모델명은 절대 하드코딩하지 않고 settings.gemini_model 사용.

[환각 방지] generate_answer의 system_instruction 5규칙 + validate_answer의
    별도 grounding 검증. 둘 다 핵심 자산이므로 아래 주석으로 강조.

[비용] 응답 1건당 LLM 호출 최대 3회 (rerank + generate + validate). 토큰은
    usage_metadata에서 누적 합산해 ask() 결과로 반환.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from google import genai
from google.genai import types

from app.config import get_settings
from app.search import SearchResult, get_search_backend

logger = logging.getLogger(__name__)

# 문서에서 답을 못 찾았을 때의 고정 문구. validate가 이 문구를 자동 통과시킨다.
NOT_FOUND_MESSAGE = "제공된 문서에서 해당 내용을 찾을 수 없습니다."

# 파이프라인 기본 파라미터 (필요 시 ask 인자로 override).
DEFAULT_TOP_K = 20  # 검색 candidate 수
DEFAULT_TOP_N = 5   # rerank 후 남길 수


# ──────────────────────────────────────────────────────────────────────────
# genai client (싱글톤) — Firestore client처럼 모듈 레벨에서 1회 생성 후 재사용
# ──────────────────────────────────────────────────────────────────────────
_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Vertex 백엔드 genai client를 lazy 싱글톤으로 반환.

    project는 GCP_PROJECT_ID, location은 GEMINI_LOCATION(us-central1) 사용.
    인증은 ADC(GOOGLE_APPLICATION_CREDENTIALS의 service account)로 자동 처리 →
    코드에 API key 노출 없음.
    """
    global _client
    if _client is None:
        s = get_settings()
        _client = genai.Client(
            vertexai=True,
            project=s.gcp_project_id,
            location=s.gemini_location,
        )
        logger.info(
            "[ai] genai client init (project=%s, location=%s, model=%s)",
            s.gcp_project_id,
            s.gemini_location,
            s.gemini_model,
        )
    return _client


async def _generate(
    prompt: str,
    *,
    temperature: float,
    max_output_tokens: int,
    json_mode: bool = False,
    system_instruction: str | None = None,
    disable_thinking: bool = False,
) -> tuple[str, int]:
    """단일 Gemini 호출 wrapper. (텍스트, 토큰 수)를 반환.

    json_mode=True면 response_mime_type=application/json으로 깔끔한 JSON 강제
    → "```json 코드펜스" 파싱 함정 거의 제거.
    disable_thinking=True면 thinking_budget=0으로 추론 토큰을 끈다. rerank/validate
    같은 단순 JSON 작업에서 thinking이 max_output_tokens를 먹어 출력이 비는 것 방지.
    [함정 1] 파라미터명은 max_tokens가 아니라 max_output_tokens (google-genai).
    [함정 2] thinking 설정은 모델 계열마다 다름(2.5=budget, 3.x=level). 모델 교체로
        인한 거부(400)를 대비해, thinking 관련 에러면 thinking 없이 1회 재시도한다.
    """
    s = get_settings()
    client = _get_client()

    cfg: dict[str, Any] = {
        "temperature": temperature,
        "max_output_tokens": max_output_tokens,
    }
    if json_mode:
        cfg["response_mime_type"] = "application/json"
    if system_instruction:
        cfg["system_instruction"] = system_instruction
    if disable_thinking:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=0)

    try:
        response = await client.aio.models.generate_content(
            model=s.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(**cfg),
        )
    except Exception as exc:  # noqa: BLE001
        # 모델이 thinking 설정을 거부하면(예: 3.x 계열로 교체) thinking 빼고 재시도.
        if disable_thinking and "thinking" in str(exc).lower():
            logger.warning("[ai] model rejected thinking_config → retry without it")
            cfg.pop("thinking_config", None)
            response = await client.aio.models.generate_content(
                model=s.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(**cfg),
            )
        else:
            raise

    text = (getattr(response, "text", None) or "").strip()

    # 토큰 사용량 — SDK 버전 차이를 대비해 getattr로 안전 접근.
    tokens = 0
    usage = getattr(response, "usage_metadata", None)
    if usage is not None:
        tokens = getattr(usage, "total_token_count", 0) or 0

    return text, tokens


def _loads_lenient(text: str) -> Any:
    """JSON 파싱 (혹시 모를 ```json 코드펜스 방어 후 json.loads)."""
    t = (text or "").strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    return json.loads(t)


# ──────────────────────────────────────────────────────────────────────────
# 1) Re-ranking — top_k candidate를 Gemini로 다시 점수 매겨 top_n만 남김
# ──────────────────────────────────────────────────────────────────────────
RERANK_PROMPT = """당신은 검색 결과 re-ranker입니다.
사용자 질문과 아래 후보 문서들의 관련도를 평가하세요.

각 후보의 index와 0.0~1.0 사이 관련도 점수를 JSON으로만 출력하세요.
다른 말은 절대 출력하지 마세요.

출력 형식:
{{"ranking": [{{"index": 0, "score": 0.95}}, {{"index": 2, "score": 0.80}}]}}

[질문]
{query}

[후보 문서]
{candidates}
"""


async def rerank_results(
    query: str,
    results: list[SearchResult],
    top_n: int = DEFAULT_TOP_N,
) -> tuple[list[SearchResult], int]:
    """후보를 Gemini로 re-rank 해서 상위 top_n 반환. (결과, 토큰).

    후보가 top_n 이하면 호출 없이 그대로 반환 (불필요한 LLM 비용 절약).
    파싱/호출 실패 시 fallback: 원본 상위 top_n.
    """
    if len(results) <= top_n:
        return results[:top_n], 0

    # 후보를 [index] 제목 + 내용 400자 형식으로 포맷.
    candidates = "\n\n".join(
        f"[{i}] {r.source_title}\n{(r.content or '')[:400]}"
        for i, r in enumerate(results)
    )
    prompt = RERANK_PROMPT.format(query=query, candidates=candidates)

    try:
        raw, tokens = await _generate(
            prompt,
            temperature=0.1,
            max_output_tokens=1024,
            json_mode=True,
            disable_thinking=True,
        )
        data = _loads_lenient(raw)
        ranking = data.get("ranking", [])

        reranked: list[SearchResult] = []
        for item in sorted(ranking, key=lambda x: x.get("score", 0.0), reverse=True):
            idx = item.get("index")
            if isinstance(idx, int) and 0 <= idx < len(results):
                r = results[idx]
                r.score = float(item.get("score", r.score))
                reranked.append(r)
            if len(reranked) >= top_n:
                break

        if not reranked:  # 파싱은 됐지만 쓸 게 없으면 fallback.
            logger.warning("[ai] rerank produced no usable items → fallback")
            return results[:top_n], tokens

        logger.info("[ai] rerank %d → %d", len(results), len(reranked))
        return reranked, tokens
    except Exception:  # noqa: BLE001
        logger.error("[ai] rerank failed → fallback to top_n", exc_info=True)
        return results[:top_n], 0


# ──────────────────────────────────────────────────────────────────────────
# 2) Answer generation — 검색 문서에만 근거해 답변 (환각 방지 system 규칙)
# ──────────────────────────────────────────────────────────────────────────
#
# ★★★ 환각 방지 핵심 ★★★  이 system_instruction이 약해지면 환각이 늘어난다.
#     5규칙은 절대 임의로 완화하지 말 것. (회사명/persona만 settings에서 주입)
def _build_system_instruction() -> str:
    s = get_settings()
    company = getattr(s, "company_name", None) or "회사"
    return (
        f"당신은 {company} 사내 문서 기반 QA 챗봇입니다.\n"
        "다음 규칙을 반드시 지키세요:\n"
        "1. 제공된 '검색된 문서'에 명시된 내용에만 근거해 답변한다.\n"
        f"2. 문서에서 답을 찾을 수 없으면 정확히 \"{NOT_FOUND_MESSAGE}\" 라고만 답한다.\n"
        "3. 답변 마지막에 근거 문서를 [1], [2] 형식으로 표기한다.\n"
        "4. 한국어로 친절하고 명확하게 답한다.\n"
        "5. 문서에 없는 사실을 추측하거나 지어내지 않는다. (환각 절대 금지)"
    )


ANSWER_PROMPT_TEMPLATE = """[검색된 문서]
{documents}

[최근 대화]
{history}

[질문]
{query}
"""


def _truncate_history(history: list[dict] | None, max_pairs: int = 5) -> str:
    """chat_history를 최근 max_pairs 문답(=max_pairs*2 메시지)만 남겨 포맷.

    토큰/비용 제어 (ADR 0008). history item은 {"role": "user"|"assistant"|"bot",
    "content": "..."} 형태를 가정. 비면 "(이전 대화 없음)".
    """
    if not history:
        return "(이전 대화 없음)"

    recent = history[-(max_pairs * 2):]
    lines: list[str] = []
    for msg in recent:
        role = (msg.get("role") or "").lower()
        speaker = "사용자" if role in ("user", "human") else "챗봇"
        lines.append(f"{speaker}: {msg.get('content', '')}")
    return "\n".join(lines) if lines else "(이전 대화 없음)"


async def generate_answer(
    query: str,
    documents: list[SearchResult],
    chat_history: list[dict] | None = None,
) -> tuple[str, int]:
    """검색 문서 기반으로 답변 생성. (답변 텍스트, 토큰).

    documents가 비면 LLM 호출 없이 즉시 NOT_FOUND_MESSAGE 반환.
    """
    if not documents:
        return NOT_FOUND_MESSAGE, 0

    docs_block = "\n\n".join(
        f"[{i + 1}] {r.source_title}\n{r.content or ''}"
        for i, r in enumerate(documents)
    )
    prompt = ANSWER_PROMPT_TEMPLATE.format(
        documents=docs_block,
        history=_truncate_history(chat_history),
        query=query,
    )

    try:
        answer, tokens = await _generate(
            prompt,
            temperature=0.2,
            max_output_tokens=2048,
            system_instruction=_build_system_instruction(),
        )
        if not answer:
            logger.warning("[ai] empty answer from model")
            return NOT_FOUND_MESSAGE, tokens
        return answer, tokens
    except Exception:  # noqa: BLE001 - 12단계 정식 handling
        logger.error("[ai] generate_answer failed", exc_info=True)
        return "[답변 생성 중 오류가 발생했습니다.]", 0


# ──────────────────────────────────────────────────────────────────────────
# 3) Validation — 생성된 답변이 문서에 실제로 grounded 되는지 재확인
# ──────────────────────────────────────────────────────────────────────────
VALIDATION_PROMPT = """당신은 사실 검증기(fact checker)입니다.
아래 '답변'이 '근거 문서'의 내용으로 뒷받침되는지 판단하세요.

- 답변 내용이 문서로 뒷받침되면 grounded=true
- 문서에 없는 내용을 포함하면 grounded=false

JSON으로만 출력하세요 (다른 말 금지):
{{"grounded": true, "confidence": 0.0~1.0, "reason": "간단한 근거"}}

[근거 문서]
{documents}

[답변]
{answer}
"""


async def validate_answer(
    answer: str,
    documents: list[SearchResult],
) -> tuple[dict, int]:
    """답변의 grounding 여부를 Gemini로 검증. (validation dict, 토큰).

    NOT_FOUND 답변은 자동 통과(grounded=True, 호출 없음).
    실패 시 fallback: grounded=True, confidence=0.5 (운영을 막지 않되 로그 남김).
    """
    if answer.strip() == NOT_FOUND_MESSAGE:
        return {"grounded": True, "confidence": 1.0, "reason": "no-answer auto-pass"}, 0

    docs_block = "\n\n".join(
        f"- {r.source_title}: {(r.content or '')[:500]}" for r in documents
    )
    # [함정] 답변의 [1],[2] 참조 표시가 검증을 헷갈리게 할 수 있어 제거 후 검증.
    clean_answer = re.sub(r"\[\d+\]", "", answer).strip()
    prompt = VALIDATION_PROMPT.format(documents=docs_block, answer=clean_answer)

    try:
        raw, tokens = await _generate(
            prompt,
            temperature=0.0,
            max_output_tokens=1024,
            json_mode=True,
            disable_thinking=True,
        )
        data = _loads_lenient(raw)
        return {
            "grounded": bool(data.get("grounded", True)),
            "confidence": float(data.get("confidence", 0.5)),
            "reason": str(data.get("reason", "")),
        }, tokens
    except Exception:  # noqa: BLE001
        logger.error("[ai] validate_answer failed → fallback grounded=True", exc_info=True)
        return {"grounded": True, "confidence": 0.5, "reason": "Validation error"}, 0


# ──────────────────────────────────────────────────────────────────────────
# 4) Main pipeline — Search → Rerank → Generate → Validate
# ──────────────────────────────────────────────────────────────────────────
async def ask(
    query: str,
    user_email: str,
    user_oauth_token: str | None = None,
    chat_history: list[dict] | None = None,
) -> dict:
    """RAG 전체 파이프라인. 단계별 시간/토큰을 측정해 dict로 반환.

    Returns:
        {
          "answer": str,
          "sources": [{"title", "uri", "score"}, ...],   # top_n
          "tokens_used": int,        # rerank+generate+validate 합산
          "response_time_ms": int,
          "validation": {"grounded", "confidence", "reason"},
          "timings_ms": {"search", "rerank", "generate", "validate"},
        }
    """
    s = get_settings()
    t0 = time.time()

    # 1) Search (top_k)
    backend = get_search_backend()
    raw_results = await backend.search(
        query,
        user_email=user_email,
        user_oauth_token=user_oauth_token,
        top_k=DEFAULT_TOP_K,
    )
    t_search = time.time()

    # 2) Rerank (top_n)
    reranked, rerank_tokens = await rerank_results(query, raw_results, top_n=DEFAULT_TOP_N)
    t_rerank = time.time()

    # 3) Generate
    answer, gen_tokens = await generate_answer(query, reranked, chat_history)
    t_gen = time.time()

    # 4) Validate (env로 on/off)
    if getattr(s, "enable_validation", True):
        validation, val_tokens = await validate_answer(answer, reranked)
    else:
        validation, val_tokens = (
            {"grounded": None, "confidence": None, "reason": "validation disabled"},
            0,
        )
    t_end = time.time()

    sources = [
        {"title": r.source_title, "uri": r.source_uri, "score": round(r.score, 4)}
        for r in reranked
    ]
    total_tokens = rerank_tokens + gen_tokens + val_tokens

    result = {
        "answer": answer,
        "sources": sources,
        "tokens_used": total_tokens,
        "response_time_ms": int((t_end - t0) * 1000),
        "validation": validation,
        "timings_ms": {
            "search": int((t_search - t0) * 1000),
            "rerank": int((t_rerank - t_search) * 1000),
            "generate": int((t_gen - t_rerank) * 1000),
            "validate": int((t_end - t_gen) * 1000),
        },
    }
    logger.info(
        "[ai] ask done: %d sources, %d tokens, %d ms, grounded=%s",
        len(sources),
        total_tokens,
        result["response_time_ms"],
        validation.get("grounded"),
    )
    return result