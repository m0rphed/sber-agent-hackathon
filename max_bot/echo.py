import asyncio
import logging
import os

from dotenv import load_dotenv
from maxapi import Bot, Dispatcher
from maxapi.filters import F
from maxapi.types import MessageCreated

load_dotenv()

logging.basicConfig(level=logging.INFO)

bot = Bot(os.getenv('TOKEN_MAX'))
dp = Dispatcher()


@dp.message_created(F.message.body.text)
async def echo(event: MessageCreated):
    await event.message.answer(f"Повторяю за вами: {event.message.body.text}")


async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())