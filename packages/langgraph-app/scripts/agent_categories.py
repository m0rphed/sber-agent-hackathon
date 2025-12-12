#!/usr/bin/env python
"""
Тест классификации категорий на примерах.

Usage:
    uv run python scripts/agent_categories.py
"""
import asyncio
from langchain_core.messages import HumanMessage
from langgraph_app.agent.nodes.category_classifier import classify_category_node


EXAMPLES = [
    # Address / Location
    ("Какой у меня район?", "district"),
    ("Найди адрес Тверская 1", "address"),
    
    # MFC
    ("Где ближайший МФЦ?", "mfc"),
    ("Найди МФЦ рядом с домом", "mfc"),
    
    # Medical
    ("Какая поликлиника обслуживает мой дом?", "polyclinic"),
    ("Нужна женская консультация", "polyclinic"),
    
    # Education
    ("В какую школу идти моему ребёнку?", "school"),
    ("Покажи школы в моём районе", "school"),
    ("Какие детские сады рядом?", "kindergarten"),
    ("Куда отдать ребёнка в садик?", "kindergarten"),
    
    # Pets
    ("Где ветеринарная клиника?", "pets"),
    ("Найди площадку для выгула собак", "pets"),
    ("Куда пристроить бездомного кота?", "pets"),
    
    # Housing
    ("Какая УК обслуживает мой дом?", "housing"),
    ("Когда капремонт?", "housing"),
    
    # Pensioners
    ("Что положено пенсионерам?", "pensioner"),
    ("Какие льготы для ветеранов?", "pensioner"),
    
    # Events
    ("Какие мероприятия сегодня?", "events"),
    ("Что интересного в Москве?", "events"),
    
    # Recreation  
    ("Где погулять с ребёнком?", "recreation"),
    ("Покажи парки рядом", "recreation"),
    
    # Infrastructure
    ("Где пункты переработки отходов?", "infrastructure"),
    ("Где сейчас ремонт дорог?", "infrastructure"),
    
    # Conversation
    ("Привет!", "conversation"),
    ("Что ты умеешь?", "conversation"),
    ("Спасибо за помощь", "conversation"),
]


async def test_classification():
    print("Testing category classification...")
    print("=" * 70)
    
    correct = 0
    wrong = []
    
    for query, expected in EXAMPLES:
        # classify_category_node expects state dict with 'messages'
        state = {"messages": [HumanMessage(content=query)]}
        result_state = classify_category_node(state)
        
        # Handle coroutine if async
        if asyncio.iscoroutine(result_state):
            result_state = await result_state
            
        category = result_state.get("category")
        actual = category.value if hasattr(category, 'value') else str(category)
        
        ok = actual == expected
        if ok:
            correct += 1
            status = "✓"
        else:
            wrong.append((query, expected, actual))
            status = "✗"
        
        print(f"{status} '{query[:40]:40}' → {actual:15} (expected: {expected})")
    
    print("=" * 70)
    print(f"Result: {correct}/{len(EXAMPLES)} correct ({100*correct/len(EXAMPLES):.1f}%)")
    
    if wrong:
        print("\nWrong classifications:")
        for q, exp, act in wrong:
            print(f"  '{q}' → got '{act}', expected '{exp}'")


if __name__ == "__main__":
    asyncio.run(test_classification())
