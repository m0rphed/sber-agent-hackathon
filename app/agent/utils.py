from typing import cast

from langchain_core.runnables.config import CONFIG_KEYS, COPIABLE_KEYS
from langgraph.checkpoint.sqlite import RunnableConfig


def langchain_cast_sqlite_config(config: dict[str, dict]) -> RunnableConfig:
    res = cast(
        'RunnableConfig',
        {
            k: v.copy() if k in COPIABLE_KEYS else v  # type: ignore[attr-defined]
            for k, v in config.items()
            if v is not None and k in CONFIG_KEYS
        },
    )
    return res
