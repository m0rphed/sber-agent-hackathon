# backend/app.py
from typing import Any, Dict, Generator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph_client import (
    chat_sync,
    check_server_available,
    get_thread_history,
    stream_chat,
)
from pydantic import BaseModel

from agent_sdk.config import LOG_LEVEL

app = FastAPI(
    title='City Assistant API',
    version='1.0.0',
)

# ---- CORS, чтобы React мог ходить к API ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        'http://localhost:3000',
        'http://localhost:5173',
        # сюда добавишь домен продакшена
    ],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

# --------- Pydantic-модели запросов/ответов ---------


class ChatRequest(BaseModel):
    """
    Один вызов чата.
    chat_id: любой строковый ID чата (можно использовать id диалога из фронта)
    """
    chat_id: str
    message: str
    graph_id: str = 'supervisor'


class ChatResponse(BaseModel):
    reply: str


class HistoryResponse(BaseModel):
    chat_id: str
    messages: list[Dict[str, str]]


# -------------- Эндпоинты --------------


@app.get('/api/health')
def health_check() -> Dict[str, Any]:
    """
    Быстрая проверка: жив ли LangGraph-сервер.
    """
    alive = check_server_available()
    return {'status': 'ok' if alive else 'unavailable', 'langgraph_ok': alive}


@app.post('/api/chat', response_model=ChatResponse)
def chat_endpoint(req: ChatRequest) -> ChatResponse:
    """
    Не-стриминговый вызов: React ждёт полный ответ целиком.
    """
    try:
        reply = chat_sync(
            user_chat_id=req.chat_id,
            message=req.message,
            agent_graph_id=req.graph_id,
        )
        return ChatResponse(reply=reply)
    except Exception as e:
        if LOG_LEVEL == 'DEBUG':
            print('[chat_endpoint error]', e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post('/api/chat/stream')
def chat_stream_endpoint(req: ChatRequest):
    """
    Стриминговый вариант. Отдаём text/event-stream (SSE).
    В React можно слушать через EventSource.
    """

    def sse_generator() -> Generator[str, None, None]:
        try:
            for chunk in stream_chat(
                user_chat_id=req.chat_id,
                message=req.message,
                agent_graph_id=req.graph_id,
            ):
                # формат SSE: "data: <текст>\n\n"
                yield f'data: {chunk}\n\n'
        except Exception as e:
            yield f'data: ❌ Ошибка streaming: {e}\n\n'

    return StreamingResponse(sse_generator(), media_type='text/event-stream')


@app.get('/api/chat/history', response_model=HistoryResponse)
def chat_history(chat_id: str):
    """
    Отдаёт историю сообщений для данного chat_id из LangGraph.
    (Если ты хочешь хранить историю только на стороне LangGraph.)
    """
    try:
        messages = get_thread_history(chat_id)
        return HistoryResponse(chat_id=chat_id, messages=messages)
    except Exception as e:
        if LOG_LEVEL == 'DEBUG':
            print('[chat_history error]', e)
        raise HTTPException(status_code=500, detail=str(e))
