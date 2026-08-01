"""
Delivery-time summarisation.

The daily digest polishes only the *selected* items (a handful) into engaging,
Japanese, news-style briefs — a strong headline, a 2-3 sentence lede, concrete
facts, and a reason to care. This is where reader-facing quality is set, so it
uses the best prompt on the freshest available article text (requirement 15:
final summary only for delivery targets).
"""
from __future__ import annotations

import logging
from typing import Optional

from src.llm import LLMClient
from src.schemas import ArticleFacts

logger = logging.getLogger(__name__)

_NEW_SYSTEM = (
    "あなたは日本語の速報ニュース編集者です。以下の記事から、読者が思わず読みたくなる"
    "簡潔なニュースブリーフを日本語で作成します。\n"
    "- headline: 具体的で引きのある日本語の見出し(30字前後、体言止め可)。誇張・煽り・クリック誘導は禁止。\n"
    "- summary: 2〜3文の日本語リード。『何が・いつ・誰によって』起きたかを具体的に。"
    "固有名詞・数字・日付を可能な限り含める。『この記事は』等のメタ表現は禁止。\n"
    "- key_facts: 事実に基づく要点を2〜4個(数字・名称・変化点など)。\n"
    "- why_it_matters: なぜ読む価値があるかを1文で、具体的な影響とともに。\n"
    "- category: 主要カテゴリを1つ(例: AI, ビジネス, 政治, 経済, テクノロジー)。\n"
    "- importance_score: 0〜1。\n"
    "元タイトルが英語でも、出力はすべて日本語にすること。"
)

_UPDATE_SYSTEM = (
    "既報のニュースに続報が入りました。日本語で、続報として読みやすくまとめます。\n"
    "- headline: 続報の要点を表す日本語の見出し(30字前後)。\n"
    "- summary: 前回から『何が新しくなったか』を1〜2文の日本語で。数字・名称を含める。\n"
    "- key_facts: 新しく判明した事実を2〜3個。\n"
    "- why_it_matters: この続報が重要な理由を1文で。\n"
    "- category: 主要カテゴリを1つ。\n"
    "出力はすべて日本語にすること。"
)


def _article_text(title: str, description: str) -> str:
    return f"元タイトル: {title}\n本文: {description}".strip()


def summarize_new(llm: LLMClient, title: str, description: str) -> Optional[ArticleFacts]:
    return llm.structured(_NEW_SYSTEM, _article_text(title, description), ArticleFacts, max_tokens=700)


def summarize_update(
    llm: LLMClient, story_title: str, rolling_summary: str, new_facts: list, changed_facts: list
) -> Optional[ArticleFacts]:
    user = (
        f"既報の要約: {rolling_summary}\n"
        f"新しく判明したこと: {', '.join(new_facts) if new_facts else '(なし)'}\n"
        f"変更されたこと: {', '.join(changed_facts) if changed_facts else '(なし)'}"
    )
    return llm.structured(_UPDATE_SYSTEM, user, ArticleFacts, max_tokens=500)
