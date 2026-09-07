from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import sys

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

load_dotenv(Path(__file__).resolve().parent / ".env")

from sandix.metabase import metabase_post, get_metabase_config


@dataclass(frozen=True)
class QuestionSpec:
    title: str
    description: str
    query: str


def ensure_dashboard(title: str, description: str) -> int:
    config = get_metabase_config()
    if config.dashboard_id:
        return config.dashboard_id
    payload = {
        "name": title,
        "description": description,
        "collection_id": config.collection_id,
    }
    result = metabase_post("/api/dashboard", payload)
    return int(result["id"])


def create_question(spec: QuestionSpec) -> int:
    config = get_metabase_config()
    database_id = os.getenv("METABASE_DATABASE_ID")
    if not database_id:
        raise RuntimeError("Missing required environment variable: METABASE_DATABASE_ID")
    payload = {
        "name": spec.title,
        "description": spec.description,
        "collection_id": config.collection_id,
        "display": "table",
        "dataset_query": {
            "type": "native",
            "native": {"query": spec.query},
            "database": int(database_id),
        },
        "visualization_settings": {},
    }
    result = metabase_post("/api/card", payload)
    return int(result["id"])


def add_card_to_dashboard(dashboard_id: int, card_id: int, row: int) -> None:
    metabase_post(
        f"/api/dashboard/{dashboard_id}/cards",
        {
            "cardId": card_id,
            "row": row,
            "col": 0,
            "size_x": 18,
            "size_y": 6,
        },
    )


def main() -> int:
    dashboard_id = ensure_dashboard(
        "Sandix - konkurenti",
        "Sdílený dashboard pro všechny konkurenty a market-average srovnání.",
    )

    questions = [
        QuestionSpec(
            title="Konkurenti - poslední batch",
            description="Souhrn posledního úspěšného běhu podle `competitor_code` a `comparison_scope`.",
            query="""
                SELECT
                    competitor_code,
                    competitor_name,
                    comparison_scope,
                    queue_count,
                    search_success_count,
                    not_found_count,
                    error_count,
                    matched_product_count,
                    average_gap_pct_vs_competitor
                FROM reporting.competitor_latest_batch_v
                ORDER BY competitor_code, comparison_scope
            """,
        ),
        QuestionSpec(
            title="Konkurenti - stav hledání",
            description="Distribuce stavů posledních běhů po konkurentech.",
            query="""
                SELECT
                    competitor_code,
                    competitor_name,
                    comparison_scope,
                    search_status,
                    request_count,
                    request_pct
                FROM reporting.competitor_latest_search_status_v
                ORDER BY competitor_code, comparison_scope, search_status
            """,
        ),
        QuestionSpec(
            title="Konkurenti - průměrná cena trhu",
            description="Porovnání Sandix proti průměru napříč všemi konkurenty.",
            query="""
                SELECT
                    comparison_scope,
                    product_name,
                    sandix_part_number,
                    competitor_count,
                    avg_competitor_price_gross,
                    min_competitor_price_gross,
                    max_competitor_price_gross,
                    avg_price_gap_gross,
                    avg_price_gap_pct_vs_competitor
                FROM reporting.competitor_market_price_comparison_v
                ORDER BY avg_price_gap_pct_vs_competitor DESC NULLS LAST, avg_price_gap_gross DESC NULLS LAST, product_name
            """,
        ),
        QuestionSpec(
            title="Filtr part numberů - stav konkurenta",
            description="Coverage snapshot po `source_domain` pro poslední konkurentský běh.",
            query="""
                SELECT
                    source_domain,
                    search_coverage_status,
                    row_count
                FROM reporting.part_number_filter_latest_coverage_summary_v
                ORDER BY source_domain, search_coverage_status
            """,
        ),
    ]

    card_ids: list[int] = []
    for spec in questions:
        card_ids.append(create_question(spec))

    for index, card_id in enumerate(card_ids, start=1):
        add_card_to_dashboard(dashboard_id, card_id, row=(index - 1) * 6)

    print(f"Dashboard ready: {dashboard_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
