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



@dp.message_created(F.message.body.text)
async def echo(event: MessageCreated):
    rich.print(event)
    rich.print(event.chat.chat_id)
    result = chat_with_agent(event.chat.chat_id, event.message.body.text)
    await event.message.answer(f"ОТВЕТ: {result}")


async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
