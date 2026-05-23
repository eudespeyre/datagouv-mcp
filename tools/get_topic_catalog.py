from typing import Optional
from mcp.server.fastmcp import FastMCP
from helpers import datagouv_api_client


def register_get_topic_catalog_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_topic_catalog(topic_id: str) -> dict:
        """
        Get the contextualization catalog of a data.gouv.fr topic.

        Reads the topic's `extras.mcp.catalog_dataset_id` field and
        returns the associated catalog dataset, which documents the
        datasets of the topic and their column schemas.

        This tool implements the trust space convention: a topic that
        declares a catalog dataset via `extras.mcp.catalog_dataset_id`
        is treated as a documented perimeter, and its catalog can be
        queried via the standard tabular API to discover and select
        datasets.

        Parameters:
        - topic_id: topic slug or ID, e.g. "univers-culture-deps"

        Returns a dict with:
        - catalog_dataset_id: ID of the catalog dataset
        - catalog_version: version of the convention (e.g. "1.0")
        - resources: list of resources of the catalog dataset, each
          with title, id, type, and tabular resource_id if available
        - status: "ok" if the catalog is declared and accessible,
          otherwise "no_catalog_declared" or "catalog_unreachable"
        """
        topic = await datagouv_api_client.get_topic_details(topic_id)

        extras = topic.get("extras") or {}
        mcp_extras = extras.get("mcp") or {}
        catalog_dataset_id = mcp_extras.get("catalog_dataset_id")
        catalog_version = mcp_extras.get("version")

        if not catalog_dataset_id:
            return {
                "status": "no_catalog_declared",
                "topic_id": topic_id,
                "message": (
                    "This topic does not declare a contextualization "
                    "catalog via extras.mcp.catalog_dataset_id. "
                    "Use list_topic_elements to browse its datasets "
                    "directly."
                ),
            }

        try:
            dataset = await datagouv_api_client.get_dataset_details(
                catalog_dataset_id
            )
        except Exception as exc:
            return {
                "status": "catalog_unreachable",
                "topic_id": topic_id,
                "catalog_dataset_id": catalog_dataset_id,
                "error": str(exc),
            }

        resources = [
            {
                "title": r.get("title"),
                "id": r.get("id"),
                "type": r.get("type"),
                "format": r.get("format"),
                "url": r.get("url"),
            }
            for r in dataset.get("resources", [])
        ]

        return {
            "status": "ok",
            "topic_id": topic_id,
            "catalog_dataset_id": catalog_dataset_id,
            "catalog_version": catalog_version,
            "catalog_title": dataset.get("title"),
            "resources": resources,
        }
