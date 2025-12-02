"""
Агент городского помощника

Доступные API:

1. Унифицированный API (рекомендуется):
   - chat(message, session_id, agent_type) -> str
   - chat_with_metadata(message, session_id, agent_type) -> tuple[str, dict]
   - AgentType.SUPERVISOR | AgentType.HYBRID | AgentType.LEGACY

2. Supervisor Graph (Вариант 2):
   - invoke_supervisor(query, session_id, chat_history) -> tuple[str, dict]

3. Hybrid Agent Graph (Вариант 3):
   - invoke_hybrid(query, session_id, chat_history) -> tuple[str, dict]

4. Legacy ReAct Agent:
   - create_city_agent(with_persistence) -> CompiledStateGraph
   - safe_chat(agent, user_message, session_id) -> str
"""

from app.agent.city_agent import (
    chat_supervisor,
    chat_with_memory,
    chat_with_persistence,
    create_city_agent,
    invoke_agent,
    safe_chat,
)
from app.agent.hybrid import (
    HybridIntent,
    HybridState,
    create_hybrid_graph,
    get_hybrid_graph,
    invoke_hybrid,
)
from app.agent.resilience import (
    AgentError,
    AgentErrorType,
    APITimeoutError,
    LLMServiceError,
    LLMTimeoutError,
    RateLimitError,
    create_error_state_update,
    get_api_retry_policy,
    get_llm_retry_policy,
    get_llm_with_timeout,
    should_retry_exception,
)
from app.agent.supervisor import (
    Intent,
    SupervisorState,
    create_supervisor_graph,
    get_supervisor_graph,
    invoke_supervisor,
)
from app.agent.unified import (
    DEFAULT_AGENT_TYPE,
    AgentType,
    benchmark_agents,
    chat,
    chat_with_metadata,
    print_benchmark_results,
)

__all__ = [
    # Unified API (recommended)
    'chat',
    'chat_with_metadata',
    'AgentType',
    'DEFAULT_AGENT_TYPE',
    'benchmark_agents',
    'print_benchmark_results',
    # Supervisor (Variant 2)
    'create_supervisor_graph',
    'get_supervisor_graph',
    'invoke_supervisor',
    'SupervisorState',
    'Intent',
    'chat_supervisor',  # legacy wrapper
    # Hybrid (Variant 3)
    'create_hybrid_graph',
    'get_hybrid_graph',
    'invoke_hybrid',
    'HybridState',
    'HybridIntent',
    # Legacy API
    'create_city_agent',
    'safe_chat',
    'invoke_agent',
    'chat_with_memory',
    'chat_with_persistence',
    # Resilience API
    'AgentErrorType',
    'AgentError',
    'LLMTimeoutError',
    'LLMServiceError',
    'RateLimitError',
    'APITimeoutError',
    'get_llm_retry_policy',
    'get_api_retry_policy',
    'should_retry_exception',
    'create_error_state_update',
    'get_llm_with_timeout',
]
