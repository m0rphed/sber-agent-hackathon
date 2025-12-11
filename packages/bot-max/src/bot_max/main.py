"""
MAX Bot для городского помощника.

Использует langgraph-client для связи с LangGraph API.

Запуск:
    uv run --package bot-max python main.py
"""

import asyncio
import logging
import os

from dotenv import load_dotenv

# from langgraph_client import chat_with_agent
from maxapi import Bot, Dispatcher
from maxapi.filters import F
from maxapi.types import Command, MessageCreated
from maxapi.types.updates import BotStarted
import structlog

load_dotenv()

# Конфигурация
TOKEN_MAX = os.getenv('TOKEN_MAX')
LANGGRAPH_API_URL = os.getenv('LANGGRAPH_API_URL', 'http://localhost:2024')
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()

logging.basicConfig(level=LOG_LEVEL)
log = structlog.get_logger()

if not TOKEN_MAX:
    raise ValueError('TOKEN_MAX environment variable is not set.')

bot = Bot(TOKEN_MAX)
dp = Dispatcher()


@dp.bot_started()
async def bot_started(event: BotStarted) -> None:
    """
    Вызывается при создании чата с ботом
    """
    await event.bot.send_message(
        chat_id=event.chat_id,
        text='👋 Привет! Я городской помощник Санкт-Петербурга. Отправьте /start для начала.',
    )


@dp.message_created(Command('start'))
async def start(event: MessageCreated) -> None:
    """
    Обработчик команды /start
    """
    await event.message.answer(
        '👋 Привет! Я городской помощник Санкт-Петербурга.\n\n'
        'Могу помочь найти:\n'
        '• МФЦ, поликлиники, школы\n'
        '• Мероприятия и события\n'
        '• Информацию об отключениях\n'
        '• И многое другое!\n\n'
        'Просто напишите ваш вопрос.'
    )


@dp.message_created(Command('help'))
async def help_command(event: MessageCreated) -> None:
    """
    Обработчик команды /help
    """
    await event.message.answer(
        '🔍 Примеры вопросов:\n\n'
        '• Где ближайший МФЦ к Невскому проспекту 1?\n'
        '• Какие мероприятия пройдут на этой неделе?\n'
        '• Есть ли отключения воды на Большевиков 10?\n'
        '• Расскажи про Центральный район'
    )


@dp.message_created(F.message.body.text)
async def respond_every_msg(event: MessageCreated) -> None:
    """
    Обработчик всех текстовых сообщений
    """
    user_id = str(event.chat.chat_id)
    text = event.message.body.text

    log.info('Received message', user_id=user_id, text=text[:50] if text else '')

    try:
        agent_response = None
        # agent_response = await chat_with_agent(user_id, text)

        if not agent_response:
            agent_response = 'Извините, я не смог найти ответ на ваш запрос.'

        await event.message.answer(agent_response)

        log.info('Sent response', user_id=user_id, response_len=len(agent_response))

    except Exception as e:
        log.error('Error processing message', user_id=user_id, error=str(e))
        await event.message.answer(
            '😔 Произошла ошибка при обработке запроса. Пожалуйста, попробуйте позже.'
        )


async def main() -> None:
    """
    Запуск бота
    """
    log.info('Starting MAX bot', api_url=LANGGRAPH_API_URL)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
