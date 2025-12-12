#!/usr/bin/env python
"""
Тест агента со стримингом (реальное время).

Usage:
    uv run python scripts/agent_stream.py "найди ближайший МФЦ"
"""
import asyncio
import sys

from langchain_core.messages import HumanMessage

from langgraph_app.agent import hybrid_v2_graph


async def stream(query: str):
    print(f"Query: {query}")
    print("---")
    
    async for event in hybrid_v2_graph.astream_events(
        {"messages": [HumanMessage(content=query)]},
        config={"configurable": {"thread_id": "test-stream"}},
        version="v2",
    ):
        kind = event.get("event")
        
        if kind == "on_chat_model_stream":
            content = event.get("data", {}).get("chunk", {})
            if hasattr(content, "content") and content.content:
                print(content.content, end="", flush=True)
        
        elif kind == "on_chain_end" and event.get("name") == "hybrid_v2_graph":
            print("\n---")
            output = event.get("data", {}).get("output", {})
            print(f"Category: {output.get('category')}")


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Привет!"
    asyncio.run(stream(query))
