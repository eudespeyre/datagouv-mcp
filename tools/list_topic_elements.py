from typing import Optional

from mcp.server.fastmcp import FastMCP

from helpers import datagouv_api_client


def register_list_topic_elements_tool(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_topic_elements(
        topic_id: str,
        page: int = 1,
        page_size: int = 20,
        class_: Optional[str] = "Dataset",
    ) -> dict:
        """
        List elements attached to a data.gouv.fr topic.

        Use this tool to explore a thematic document perimeter defined by a topic
        slug or ID. By default, it returns datasets attached to the topic.

        Parameters:
        - topic_id: topic slug or ID, e.g. "univers-culture-deps"
        - page: page number, default 1
        - page_size: results per page, default 20, max 100
        - class_: optional API class filter, e.g. "Dataset" or "Reuse"
        """

        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)

        return await datagouv_api_client.get_topic_elements(
            topic_id=topic_id,
            page=page,
            page_size=page_size,
            class_name=class_,
        )