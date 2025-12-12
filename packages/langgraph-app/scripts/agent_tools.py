#!/usr/bin/env python
"""
Показать инструменты для категории.

Usage:
    uv run python scripts/agent_tools.py mfc
    uv run python scripts/agent_tools.py pets
    uv run python scripts/agent_tools.py  # показать все
"""
import sys

from langgraph_app.agent.models import ToolCategory
from langgraph_app.tools.registry import get_tools_for_category


def main():
    cat_name = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else ""
    
    if not cat_name:
        # Show all categories
        print("All categories and their tools:")
        print("=" * 60)
        for cat in ToolCategory:
            tools = get_tools_for_category(cat)
            print(f"\n{cat.value} ({len(tools)} tools):")
            for t in tools:
                print(f"  - {t.name}")
        return
    
    try:
        cat = ToolCategory(cat_name.lower())
        tools = get_tools_for_category(cat)
        print(f"Category: {cat.value}")
        print(f"Tools ({len(tools)}):")
        for t in tools:
            desc = t.description[:80] if len(t.description) > 80 else t.description
            print(f"  - {t.name}: {desc}")
    except ValueError:
        print(f"Unknown category: {cat_name}")
        print(f"Available: {[c.value for c in ToolCategory]}")


if __name__ == "__main__":
    main()
