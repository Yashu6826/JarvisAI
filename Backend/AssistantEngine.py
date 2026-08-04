"""Public streaming interface for the LangGraph NEXA agent."""

from Backend.JarvisAgent import AgentStream


async def AssistantStream(query: str, location: dict | None = None, history_query: str | None = None):
    async for event in AgentStream(query, location, history_query=history_query):
        yield event
