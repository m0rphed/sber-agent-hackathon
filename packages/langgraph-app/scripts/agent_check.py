#!/usr/bin/env python
"""
Проверка состояния агента (tools, categories, checkpointer).

Usage:
    uv run python scripts/agent_check.py
"""
from langgraph_app.agent import hybrid_v2_graph
from langgraph_app.agent.models import ToolCategory, API_CATEGORIES, NON_API_CATEGORIES
from langgraph_app.tools.registry import get_tools_for_category, get_all_tools
from langgraph_app.agent.nodes.slots_checker import REQUIRED_PARAMS_BY_CATEGORY


def main():
    print("=" * 60)
    print("AGENT STATUS CHECK")
    print("=" * 60)
    
    # Graph info
    print(f"\nGraph: {type(hybrid_v2_graph).__name__}")
    print(f"Checkpointer: {hybrid_v2_graph.checkpointer is not None}")
    
    # All tools
    all_tools = get_all_tools()
    print(f"Total tools: {len(all_tools)}")
    
    # Categories
    print(f"Total categories: {len(ToolCategory)}")
    print(f"  - API categories: {len(API_CATEGORIES)}")
    print(f"  - Non-API categories: {len(NON_API_CATEGORIES)}")
    
    print("\n" + "-" * 60)
    print("CATEGORIES BREAKDOWN:")
    print("-" * 60)
    
    for cat in ToolCategory:
        tools = get_tools_for_category(cat)
        params = REQUIRED_PARAMS_BY_CATEGORY.get(cat, [])
        status = "✓" if tools else "✗"
        print(f"  {cat.value:15} [{status}] tools={len(tools):2}  params={params}")
    
    print("\n" + "-" * 60)
    print("ALL TOOLS:")
    print("-" * 60)
    for i, tool in enumerate(all_tools, 1):
        print(f"  {i:2}. {tool.name}")
    
    print("\n" + "=" * 60)
    print("✓ Check complete")


if __name__ == "__main__":
    main()
