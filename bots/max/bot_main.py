import asyncio
import logging
import os

from dotenv import load_dotenv
from langgraph_func import chat_with_agent
from maxapi import Bot, Dispatcher
from maxapi.filters import F
from maxapi.types import MessageCreated
import rich

load_dotenv()

logging.basicConfig(level=logging.INFO)

bot = Bot(os.getenv('TOKEN_MAX'))
dp = Dispatcher()

@dp.bot_started()
async def bot_started(event):
    await event.bot.send_message(
        chat_id=event.chat_id,
        text='Привет! Отправь мне /start'
    )

@dp.message_created(F.message.body.text)
async def echo(event: MessageCreated):
    result = await chat_with_agent(event.chat.chat_id, event.message.body.text)
    rich.print(result)
    print('-----------------------------')
    print(f"ОТВЕТ: {result}")
    print('-----------------------------')
    await event.message.answer(f"ОТВЕТ: {result}")


async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
