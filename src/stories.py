"""
Story linking + update judgement.

For each new (already exact-deduped) article:

  1. Compute/lookup its embedding.
  2. Shortlist existing stories by embedding cosine (cheap).
  3. Require entity overlap OR a high cosine before spending an LLM call
     (requirement 15: only call the LLM when a real candidate exists).
  4. Ask the LLM whether it is genuinely the *same* event — embedding
     similarity alone never decides this (requirement 7).
  5. If linked → LLM diff judgement → change_type + delta facts (an update).
     If not   → LLM fact extraction → new Story (a new_story).

Every LLM step is validated (Pydantic) with a bounded retry and a safe
fallback, so a bad response degrades to "new story / no change" rather than
crashing the run.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.db import Database
from src.embedding import Embedder, ensure_embedding
from src.llm import LLMClient
from src.models import Article, Story, StoryEvent
from src.schemas import ArticleFacts, StoryIdentity, UpdateDiff
from src.similarity import extract_entities, find_candidates

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    article: Article
    story: Optional[Story]
    change_type: str
    facts: Optional[ArticleFacts] = None
    diff: Optional[UpdateDiff] = None


def _article_blob(article: Article) -> str:
    return f"タイトル: {article.title}\n本文: {article.description}"


def _judge_identity(llm: LLMClient, article: Article, candidates: list) -> Optional[StoryIdentity]:
    lines = []
    for story, score in candidates:
        lines.append(f"[story_id={story.id}] {story.current_title} :: {story.rolling_summary}")
    system = (
        "あなたはニュース編集者です。新しい記事が、既存のストーリー候補のいずれかと"
        "『同一の出来事』を報じているか判定します。企業名・製品名・人物名・イベント種別が"
        "一致しない場合は別ストーリーです。類似していても別の出来事なら same_story=false。"
    )
    user = (
        f"新しい記事:\n{_article_blob(article)}\n\n"
        f"既存ストーリー候補:\n" + "\n".join(lines) +
        "\n\n同一なら matched_story_id に該当IDを入れて same_story=true、"
        "そうでなければ same_story=false を返してください。"
    )
    return llm.structured(system, user, StoryIdentity, max_tokens=400)


def _judge_diff(llm: LLMClient, article: Article, story: Story) -> Optional[UpdateDiff]:
    system = (
        "既存ストーリーに新しい記事が追加されました。前回までの内容と比較し、"
        "change_type を new_story / major_update / minor_update / no_meaningful_change から選び、"
        "新しく判明した事実・変更された事実・変わっていない主要事項を抽出してください。"
        "正式リリース・価格発表・提供開始・買収成立・規制決定・重大障害・数値や方針の大幅変更は major_update。"
        "コメント追加・対応地域追加・軽微な補足は minor_update。転載や言い換えだけで新事実が無ければ no_meaningful_change。"
    )
    user = (
        f"これまでのストーリー要約:\n{story.rolling_summary}\n\n"
        f"新しい記事:\n{_article_blob(article)}"
    )
    return llm.structured(system, user, UpdateDiff, max_tokens=600)


def _extract_facts(llm: LLMClient, article: Article) -> ArticleFacts:
    system = (
        "ニュース記事から客観的事実を抽出し、要約を生成します。"
        "summary(1-2文), why_it_matters, key_facts(箇条書き), category, entities(固有名詞), "
        "importance_score(0-1), source_type(primary/high_quality/secondary/aggregator) を返してください。"
    )
    facts = llm.structured(system, _article_blob(article), ArticleFacts, max_tokens=700)
    if facts is None:
        # Fallback summary so the article is never dropped silently.
        facts = ArticleFacts(
            summary=article.description[:280],
            category=article.genre,
            entities=sorted(extract_entities(f"{article.title} {article.description}")),
            importance_score=0.3,
            source_type="secondary",
        )
    return facts


def _worth_llm_check(article_entities: set, candidates: list, threshold: float) -> bool:
    """Only spend an identity LLM call when a plausible candidate exists."""
    for story, score in candidates:
        if score >= threshold:
            return True
        if score >= 0.30 and extract_entities(story.current_title) & article_entities:
            return True
    return False


def process_article(
    article: Article,
    db: Database,
    embedder: Embedder,
    llm: LLMClient,
    *,
    lookback_stories: list,
    similarity_threshold: float,
    candidate_limit: int,
    metrics=None,
) -> ProcessResult:
    ensure_embedding(article, embedder, metrics)
    article_entities = extract_entities(f"{article.title} {article.description}")
    candidates = find_candidates(article, lookback_stories, candidate_limit)

    matched_story: Optional[Story] = None
    if candidates and _worth_llm_check(article_entities, candidates, similarity_threshold):
        identity = _judge_identity(llm, article, candidates[:3])
        if identity and identity.same_story and identity.matched_story_id is not None:
            matched_story = next(
                (s for s, _ in candidates if s.id == identity.matched_story_id), None
            )

    now = datetime.now(timezone.utc)

    if matched_story is not None:
        # ── Update path ──────────────────────────────────────────────────────
        article.story_id = matched_story.id
        db.insert_article(article)
        diff = _judge_diff(llm, article, matched_story) or UpdateDiff(
            change_type="no_meaningful_change"
        )
        event = StoryEvent(
            id=None,
            story_id=matched_story.id,
            article_id=article.id,
            change_type=diff.change_type,
            new_facts=diff.new_facts,
            changed_facts=diff.changed_facts,
            unchanged_facts=diff.unchanged_facts,
            confidence=diff.confidence,
        )
        db.insert_story_event(event)

        if diff.change_type in ("major_update", "minor_update"):
            # Roll the new facts into the story summary.
            addition = " ".join(diff.new_facts) if diff.new_facts else ""
            if addition:
                matched_story.rolling_summary = (matched_story.rolling_summary + " " + addition).strip()
            matched_story.last_updated_at = now
            matched_story.current_title = article.normalized_title or matched_story.current_title
            db.update_story(matched_story)
        return ProcessResult(article, matched_story, diff.change_type, diff=diff)

    # ── New story path ───────────────────────────────────────────────────────
    facts = _extract_facts(llm, article)
    story = Story(
        id=None,
        current_title=article.normalized_title or article.title,
        rolling_summary=facts.summary or article.description[:280],
        representative_embedding=article.embedding,
        first_seen_at=now,
        last_updated_at=now,
        importance_score=facts.importance_score,
        category=facts.category or article.genre,
        status="active",
        summary_json=facts.model_dump(),
    )
    db.insert_story(story)
    article.story_id = story.id
    db.insert_article(article)
    db.insert_story_event(
        StoryEvent(
            id=None,
            story_id=story.id,
            article_id=article.id,
            change_type="new_story",
            new_facts=facts.key_facts,
            confidence=1.0,
        )
    )
    return ProcessResult(article, story, "new_story", facts=facts)
