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

from sandix.metabase import get_metabase_config, metabase_get, metabase_post, metabase_put


@dataclass(frozen=True)
class QuestionSpec:
    title: str
    description: str
    query: str
    display: str = "table"
    visualization_settings: dict[str, object] | None = None
    previous_titles: tuple[str, ...] = ()


def ensure_dashboard(title: str, description: str) -> int:
    config = get_metabase_config()
    if config.dashboard_id:
        return config.dashboard_id

    dashboards = metabase_get("/api/dashboard")
    for dashboard in dashboards:
        if dashboard["name"] == title and dashboard.get("collection_id") == config.collection_id:
            return int(dashboard["id"])

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

    cards = metabase_get("/api/card")
    for card in cards:
        if card["name"] in (spec.title, *spec.previous_titles) and card.get("collection_id") == config.collection_id:
            metabase_put(
                f"/api/card/{card['id']}",
                {
                    "name": spec.title,
                    "description": spec.description,
                    "collection_id": config.collection_id,
                    "display": spec.display,
                    "dataset_query": {
                        "type": "native",
                        "native": {"query": spec.query},
                        "database": int(database_id),
                    },
                    "visualization_settings": spec.visualization_settings or {},
                },
            )
            return int(card["id"])

    payload = {
        "name": spec.title,
        "description": spec.description,
        "collection_id": config.collection_id,
        "display": spec.display,
        "dataset_query": {
            "type": "native",
            "native": {"query": spec.query},
            "database": int(database_id),
        },
        "visualization_settings": spec.visualization_settings or {},
    }
    result = metabase_post("/api/card", payload)
    return int(result["id"])


def set_dashboard_cards(dashboard_id: int, card_ids: list[int]) -> None:
    dashboard = metabase_get(f"/api/dashboard/{dashboard_id}")
    existing_dashcards = {card.get("card_id"): card for card in dashboard.get("dashcards", [])}
    dashcards: list[dict[str, object]] = []

    for index, card_id in enumerate(card_ids):
        dashcards.append(
            {
                "id": existing_dashcards.get(card_id, {}).get("id", -(index + 1)),
                "card_id": card_id,
                "row": index * 9,
                "col": 0,
                "size_x": 24,
                "size_y": 9,
            }
        )

    metabase_put(f"/api/dashboard/{dashboard_id}", {"width": "full", "dashcards": dashcards})


def main() -> int:
    dashboard_id = ensure_dashboard(
        "Sandix - konkurenti",
        "Sdílený dashboard pro všechny konkurenty a market-average srovnání.",
    )

    gap_formatting = {
        "table.column_formatting": [
            {"id": 10, "type": "single", "operator": ">", "value": 0, "columns": ["rozdil_%_vuci_konkurenci"], "color": "#ED6E6E", "highlight_row": True},
            {"id": 11, "type": "single", "operator": "<", "value": 0, "columns": ["rozdil_%_vuci_konkurenci"], "color": "#689735", "highlight_row": True},
            {"id": 12, "type": "single", "operator": "=", "value": 0, "columns": ["rozdil_%_vuci_konkurenci"], "color": "#999999", "highlight_row": True},
        ]
    }
    kpi_formatting = {
        "table.column_formatting": [
            {"id": 1, "type": "single", "operator": ">", "value": 0, "columns": ["sandix_drazsi"], "color": "#ED6E6E", "highlight_row": True},
            {"id": 2, "type": "single", "operator": ">", "value": 0, "columns": ["sandix_levnejsi"], "color": "#689735", "highlight_row": True},
            {"id": 3, "type": "single", "operator": ">", "value": 0, "columns": ["pocet_not_found"], "color": "#F2A86F", "highlight_row": True},
            {"id": 4, "type": "single", "operator": ">", "value": 0, "columns": ["pocet_chyb"], "color": "#ED6E6E", "highlight_row": True},
        ]
    }
    status_settings = {"series_settings": {"pocet_dotazu": {"color": "#689735"}}}
    original_price_query = """
        SELECT competitor_name AS nazev_konkurenta, sandix_part_number AS sandix_puvodni_identifikator,
               source_identifier AS sandix_vyhledavaci_identifikator, competitor_part_number AS konkurentni_identifikator,
               searched_identifier AS konkurentni_vyhledavaci_identifikator, product_name AS nazev_produktu,
               sandix_price_net AS sandix_cena_bez_dph, competitor_price_net AS konkurencni_cena_bez_dph,
               competitor_product_url AS odkaz_na_konkurenta, price_gap_net AS rozdil_bez_dph,
               price_gap_pct_vs_competitor AS "rozdil_%_vuci_konkurenci", raw_offer_count AS pocet_raw_nabidek,
               valid_offer_count AS pocet_platnych_nabidek, invalid_offer_count AS pocet_neplatnych_nabidek,
               search_request_count AS pocet_hledani, source_run_id AS zdrojovy_run_id, generated_at AS vygenerovano
        FROM reporting.competitor_latest_price_comparison_v
        WHERE comparison_scope = 'ORIGINAL'
    """
    alternative_price_query = """
        WITH latest_runs AS (
            SELECT DISTINCT ON (competitor_code, comparison_scope) source_run_id, competitor_code, comparison_scope, competitor_name
            FROM reporting.competitor_variant_batch_kpi
            WHERE comparison_scope = 'ALTERNATIVE'
            ORDER BY competitor_code, comparison_scope, generated_at DESC, batch_finished_at DESC NULLS LAST, source_run_id DESC
        )
        SELECT r.competitor_name AS nazev_konkurenta, p.sandix_part_number AS sandix_alternativni_identifikator,
               p.source_identifier AS sandix_vyhledavaci_identifikator, p.competitor_part_number AS konkurentni_alternativni_identifikator,
               p.searched_identifier AS konkurentni_vyhledavaci_identifikator, p.product_name AS nazev_produktu,
               p.sandix_price_net AS sandix_cena_bez_dph, p.competitor_price_net AS konkurencni_cena_bez_dph,
               p.competitor_product_url AS odkaz_na_konkurenta, p.price_gap_net AS rozdil_bez_dph,
               p.price_gap_pct_vs_competitor AS "rozdil_%_vuci_konkurenci", p.raw_offer_count AS pocet_raw_nabidek,
               p.valid_offer_count AS pocet_platnych_nabidek, p.invalid_offer_count AS pocet_neplatnych_nabidek,
               p.search_request_count AS pocet_hledani, p.source_run_id AS zdrojovy_run_id, p.generated_at AS vygenerovano
        FROM reporting.competitor_variant_price_comparison p
        JOIN latest_runs r ON r.source_run_id = p.source_run_id
        WHERE p.comparison_scope = 'SANDIX_ALTERNATIVE'
    """
    questions = [
        QuestionSpec("Konkurenti - Sandix ORIGINAL batch KPI", "Souhrn posledního dokončeného originálního porovnání.", """
            SELECT source_run_id AS zdrojovy_run_id, competitor_code AS kod_konkurenta, competitor_name AS nazev_konkurenta,
                   generated_at AS vygenerovano, batch_started_at AS zacatek_batchi, batch_finished_at AS konec_batchi,
                   queue_count AS pocet_hledanych_polozek, search_success_count AS pocet_ok, not_found_count AS pocet_not_found,
                   error_count AS pocet_chyb, raw_offer_count AS pocet_raw_nabidek, valid_offer_count AS pocet_validnich_nabidek,
                   invalid_offer_count AS pocet_neplatnych_nabidek, matched_product_count AS pocet_shodnych_produktu,
                   sandix_more_expensive_count AS sandix_drazsi, sandix_cheaper_count AS sandix_levnejsi,
                   equal_price_count AS stejna_cena, average_gap_pct_vs_competitor AS "prumerny_rozdil_%_vuci_konkurenci"
            FROM reporting.competitor_latest_batch_v WHERE comparison_scope = 'ORIGINAL' ORDER BY competitor_name
        """, visualization_settings=kpi_formatting, previous_titles=("Konkurenti - poslední batch",)),
        QuestionSpec("Konkurenti - Sandix ORIGINAL rozložení stavů hledání", "Distribuce OK, NOT_FOUND a ERROR pro originální porovnání.", """
            SELECT competitor_name AS nazev_konkurenta, search_status AS stav_hledani, request_count AS pocet_dotazu
            FROM reporting.competitor_latest_search_status_v WHERE comparison_scope = 'ORIGINAL'
            ORDER BY competitor_name, CASE search_status WHEN 'OK' THEN 1 WHEN 'NOT_FOUND' THEN 2 ELSE 3 END
        """, display="bar", visualization_settings=status_settings, previous_titles=("Konkurenti - stav hledání",)),
        QuestionSpec("Konkurenti - Sandix ORIGINAL cenové porovnání", "Originální Sandix PN proti nabídkám konkurentů.", original_price_query + " ORDER BY price_gap_pct_vs_competitor DESC NULLS LAST, price_gap_net DESC NULLS LAST, product_name LIMIT 50", visualization_settings=gap_formatting),
        QuestionSpec("Konkurenti - Sandix ORIGINAL dražší", "Položky, kde je Sandix dražší než konkurent.", original_price_query + " AND price_gap_pct_vs_competitor > 0 ORDER BY price_gap_pct_vs_competitor DESC NULLS LAST, price_gap_net DESC NULLS LAST, product_name LIMIT 10", visualization_settings=gap_formatting),
        QuestionSpec("Konkurenti - Sandix ORIGINAL levnější", "Položky, kde je Sandix levnější než konkurent.", original_price_query + " AND price_gap_pct_vs_competitor < 0 ORDER BY price_gap_pct_vs_competitor ASC NULLS LAST, price_gap_net ASC NULLS LAST, product_name LIMIT 10", visualization_settings=gap_formatting),
        QuestionSpec("Konkurenti - alternativní batch KPI", "Souhrn posledního alternativního porovnání podle konkurenta.", """
            WITH ranked AS (
                SELECT *, row_number() OVER (PARTITION BY competitor_code, comparison_scope ORDER BY generated_at DESC, batch_finished_at DESC NULLS LAST, source_run_id DESC) AS rn
                FROM reporting.competitor_variant_batch_kpi WHERE comparison_scope = 'ALTERNATIVE'
            )
            SELECT source_run_id AS zdrojovy_run_id, competitor_code AS kod_konkurenta, competitor_name AS nazev_konkurenta,
                   generated_at AS vygenerovano, request_count AS pocet_hledanych_polozek, search_success_count AS pocet_ok,
                   not_found_count AS pocet_not_found, error_count AS pocet_chyb, matched_product_count AS pocet_shodnych_produktu,
                   sandix_more_expensive_count AS sandix_drazsi, sandix_cheaper_count AS sandix_levnejsi,
                   average_gap_pct_vs_competitor AS "prumerny_rozdil_%_vuci_konkurenci"
            FROM ranked WHERE rn = 1 ORDER BY nazev_konkurenta
        """, visualization_settings=kpi_formatting),
        QuestionSpec("Konkurenti - alternativní rozložení stavů hledání", "Distribuce stavů pro alternativní porovnání.", """
            WITH latest_runs AS (
                SELECT DISTINCT ON (competitor_code, comparison_scope) source_run_id, competitor_code, comparison_scope, competitor_name
                FROM reporting.competitor_variant_batch_kpi WHERE comparison_scope = 'ALTERNATIVE'
                ORDER BY competitor_code, comparison_scope, generated_at DESC, batch_finished_at DESC NULLS LAST, source_run_id DESC
            )
            SELECT r.competitor_name AS nazev_konkurenta, s.search_status AS stav_hledani, s.request_count AS pocet_dotazu
            FROM reporting.competitor_variant_search_status s JOIN latest_runs r ON r.source_run_id = s.source_run_id AND r.comparison_scope = s.comparison_scope
            ORDER BY nazev_konkurenta, CASE s.search_status WHEN 'OK' THEN 1 WHEN 'NOT_FOUND' THEN 2 ELSE 3 END
        """, display="bar", visualization_settings=status_settings),
        QuestionSpec("Konkurenti - Sandix ALTERNATIVE vs konkurent ALTERNATIVE", "Alternativní Sandix PN proti alternativním nabídkám konkurentů.", alternative_price_query + " ORDER BY p.price_gap_pct_vs_competitor DESC NULLS LAST, p.price_gap_net DESC NULLS LAST, p.product_name LIMIT 50", visualization_settings=gap_formatting),
        QuestionSpec("Konkurenti - Sandix ALTERNATIVE dražší", "Alternativní položky, kde je Sandix dražší než konkurent.", alternative_price_query + " AND p.price_gap_pct_vs_competitor > 0 ORDER BY p.price_gap_pct_vs_competitor DESC NULLS LAST, p.price_gap_net DESC NULLS LAST, p.product_name LIMIT 10", visualization_settings=gap_formatting),
        QuestionSpec("Konkurenti - Sandix ALTERNATIVE levnější", "Alternativní položky, kde je Sandix levnější než konkurent.", alternative_price_query + " AND p.price_gap_pct_vs_competitor < 0 ORDER BY p.price_gap_pct_vs_competitor ASC NULLS LAST, p.price_gap_net ASC NULLS LAST, p.product_name LIMIT 10", visualization_settings=gap_formatting),
        QuestionSpec("Konkurenti - průměrná cena trhu", "Experimentální porovnání Sandix proti průměru napříč konkurenty.", """
            SELECT comparison_scope, product_name, sandix_part_number, competitor_count, avg_competitor_price_gross,
                   min_competitor_price_gross, max_competitor_price_gross, avg_price_gap_gross, avg_price_gap_pct_vs_competitor
            FROM reporting.competitor_market_price_comparison_v
            ORDER BY avg_price_gap_pct_vs_competitor DESC NULLS LAST, avg_price_gap_gross DESC NULLS LAST, product_name
        """),
        QuestionSpec("Filtr part numberů - stav konkurenta", "Coverage snapshot po source_domain pro poslední konkurentský běh.", """
            SELECT source_domain, search_coverage_status, row_count
            FROM reporting.part_number_filter_latest_coverage_summary_v
            ORDER BY source_domain, search_coverage_status
        """),
    ]

    card_ids: list[int] = []
    for spec in questions:
        card_ids.append(create_question(spec))

    set_dashboard_cards(dashboard_id, card_ids)

    print(f"Dashboard ready: {dashboard_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
