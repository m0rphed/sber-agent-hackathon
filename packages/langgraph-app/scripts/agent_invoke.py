#!/usr/bin/env python
"""
Тест агента с простым запросом.

Usage:
    uv run python scripts/agent_invoke.py "найди МФЦ"
    uv run python scripts/agent_invoke.py  # default query
"""
import asyncio
import sys

from langchain_core.messages import HumanMessage

from langgraph_app.agent import hybrid_v2_graph


async def test(query: str):
    print(f"Query: {query}")
    print("---")
    
    result = await hybrid_v2_graph.ainvoke(
        {"messages": [HumanMessage(content=query)]},
        config={"configurable": {"thread_id": "test-thread"}},
    )
    
    print(f"Category: {result.get('category')}")
    
    # Check for interrupt (address selection, clarification, etc.)
    interrupt_data = result.get('__interrupt__')
    if interrupt_data:
        for interrupt in interrupt_data:
            value = interrupt.value if hasattr(interrupt, 'value') else interrupt
            print(f"\n⏸️  INTERRUPT: {value.get('type', 'unknown')}")
            print(f"   Message: {value.get('message', value.get('question', ''))}")
            candidates = value.get('candidates', [])
            if candidates:
                print("   Candidates:")
                for c in candidates:
                    print(f"     {c.get('index')}. {c.get('address')}")
        return
    
    # Check for clarification needed (slots_checker)
    clarification = result.get('needs_clarification')
    if clarification:
        print(f"\n❓ Clarification needed: {clarification.get('type')}")
        print(f"   Question: {clarification.get('question', clarification.get('message', ''))}")
        return
    
    print(f"Response: {result.get('final_response', 'No response')}")


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Привет, что ты умеешь?"
    asyncio.run(test(query))
