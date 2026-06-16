import logging

import httpx
from mcp.server.fastmcp import FastMCP

from helpers import datagouv_api_client, tabular_api_client
from helpers.logging import MAIN_LOGGER_NAME, log_tool
from helpers.mcp_tool_defaults import READ_ONLY_EXTERNAL_API_TOOL

logger = logging.getLogger(MAIN_LOGGER_NAME)

# Garde-fous de pagination : on récupère TOUTES les lignes pour agréger.
FETCH_PAGE_SIZE = 200
MAX_PAGES = 500
SUPPORTED_OPS = {"sum", "mean", "min", "max", "count"}


def register_aggregate_resource_data_tool(mcp: FastMCP) -> None:
    @mcp.tool(
        title="Aggregate resource data",
        annotations=READ_ONLY_EXTERNAL_API_TOOL,
    )
    @log_tool
    async def aggregate_resource_data(
        resource_id: str,
        column: str,
        op: str = "sum",
        filter_column: str | None = None,
        filter_value: str | None = None,
        filter_operator: str = "exact",
    ) -> str:
        """
        Deterministically aggregate a column of a tabular resource over ALL rows.

        Computes sum / mean / min / max / count server-side (in Python) instead of
        relying on the model to add numbers — the result is exact and reproducible.
        Use this for any total/sum/average rather than computing it yourself.
        Provide the exact column name (preview with query_resource_data first if
        unsure). Optional filter_column/filter_value/filter_operator narrows rows.
        Filter operators: exact, contains, less, greater, strictly_less, strictly_greater.
        """
        try:
            op = op.lower()
            if op not in SUPPORTED_OPS:
                return (
                    "Error: invalid op. Supported values: "
                    f"{', '.join(sorted(SUPPORTED_OPS))}."
                )

            filter_operator = filter_operator.lower()
            operator_map = {
                "exact": "exact",
                "contains": "contains",
                "less": "less",
                "greater": "greater",
                "strictly_less": "strictly_less",
                "strictly_greater": "strictly_greater",
            }
            api_params = {}
            if filter_column and filter_value is not None:
                if filter_operator not in operator_map:
                    return (
                        "Error: invalid filter_operator. Supported values: "
                        f"{', '.join(sorted(operator_map.keys()))}."
                    )
                api_params[f"{filter_column}__{operator_map[filter_operator]}"] = (
                    filter_value
                )

            # Contexte (best effort, comme query_resource_data)
            try:
                rmeta = await datagouv_api_client.get_resource_metadata(resource_id)
                resource_title = rmeta.get("title", "Unknown")
            except Exception:  # noqa: BLE001
                resource_title = "Unknown"

            logger.info(
                f"Aggregating ({op}) column '{column}' on resource "
                f"{resource_title} (ID: {resource_id}), filters: {api_params}"
            )

            # Récupération de TOUTES les lignes via l'API tabulaire (pagination).
            values: list[float] = []
            n_total = 0
            n_skipped = 0
            page = 1
            try:
                while page <= MAX_PAGES:
                    tabular_data = await tabular_api_client.fetch_resource_data(
                        resource_id,
                        page=page,
                        page_size=FETCH_PAGE_SIZE,
                        params=api_params if api_params else None,
                    )
                    rows = tabular_data.get("data", []) or []
                    n_total += len(rows)
                    for row in rows:
                        v = row.get(column)
                        if v is None or v == "":
                            n_skipped += 1
                            continue
                        try:
                            values.append(float(v))
                        except (TypeError, ValueError):
                            n_skipped += 1
                    links = tabular_data.get("links", {}) or {}
                    if not rows or not links.get("next"):
                        break
                    page += 1
            except tabular_api_client.ResourceNotAvailableError as e:
                # Message « not available / not found in the Tabular API » : laissé
                # tel quel pour que l'orchestration le traite comme un signal.
                logger.warning(f"Resource not available: {resource_id} - {str(e)}")
                return f"⚠️  {str(e)}"
            except tabular_api_client.TabularApiRequestError as e:
                # Filtre/colonne invalide (HTTP 400) : signal de schéma.
                logger.warning(f"Tabular API request failed: {resource_id} - {str(e)}")
                return f"⚠️  {str(e)}"

            # Agrégation déterministe.
            if op == "count":
                result: float = len(values)
            elif not values:
                return (
                    f"Aggregation: column '{column}' has no numeric value "
                    f"(checked {n_total} row(s)). Verify the exact column name with "
                    f"query_resource_data or the catalog_schema resource."
                )
            elif op == "sum":
                result = sum(values)
            elif op == "mean":
                result = sum(values) / len(values)
            elif op == "min":
                result = min(values)
            else:  # max
                result = max(values)

            if isinstance(result, float) and result.is_integer():
                result = int(result)

            def _fmt(x: float):
                return int(x) if float(x).is_integer() else x

            lines = [
                "Aggregation result (deterministic, server-side):",
                f"Resource: {resource_title} (ID: {resource_id})",
                f"Column: {column} | Operation: {op}",
            ]
            if api_params:
                lines.append(f"Filter: {api_params}")
            lines.append(f"Result: {result}")
            lines.append(
                f"Rows used: {len(values)} | total: {n_total} | skipped: {n_skipped}"
            )
            if values and op != "count":
                lines.append(
                    f"Audit — min: {_fmt(min(values))} | max: {_fmt(max(values))}"
                )
            lines.append(
                "Unit is the column's own (e.g. a *_k_eur column is in thousands "
                "of euros)."
            )
            return "\n".join(lines)

        except httpx.HTTPStatusError as e:
            return f"Error: HTTP {e.response.status_code} - {str(e)}"
        except Exception as e:  # noqa: BLE001
            logger.exception(f"Unexpected error aggregating resource {resource_id}")
            return f"Error: {str(e)}"