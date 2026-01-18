
from typing import List
from pydantic import BaseModel, Field
from north_mcp_python_sdk import NorthMCPServer

_default_port = 3001

# update all the mcp tool functions to be <aubrey_marcelotanner>_<tool>
# since mcp tool names MUST be unique

mcp = NorthMCPServer(
    "Simple Calculator", host="0.0.0.0", port=_default_port
)

@mcp.tool()
def aubrey_marcelotanner_recipe_something(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b




# Use streamable-http transport to enable streaming responses over HTTP.
# This allows the server to send data to the client incrementally (in chunks),
# improving responsiveness for long-running or large operations.
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
