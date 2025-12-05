import asyncio

from maxapi import Bot, Dispatcher
from maxapi.enums.parse_mode import ParseMode
from maxapi.filters import F
from maxapi.types import Command, MessageCreated
from maxapi.types.updates import BotStarted
import rich

from agent_sdk.langgraph_functions import chat_with_agent
from bots.max.config import LOG_LEVEL, TOKEN_MAX

if not TOKEN_MAX:
    raise ValueError('TOKEN_MAX environment variable is not set.')

bot = Bot(TOKEN_MAX)
dp = Dispatcher()


# присылает сообщение при создании чата с ботом
@dp.bot_started()
async def bot_started(event: BotStarted):
    await event.bot.send_message(chat_id=event.chat_id, text='Привет! Отправь мне /start')


# ответ бота на команду /start
# TODO: изменить приветственное сообщение на список того что умеет бот - должен получать это от агента
@dp.message_created(Command('start'))
async def start(event: MessageCreated):
    await event.message.answer('Это чат-бот ИИ помощника для г. Санкт-Петербург! Чем могу помочь?')


# перехватывает любые сообщения с текстом
@dp.message_created(F.message.body.text)
async def respond_every_msg(event: MessageCreated):
    agent_response = await chat_with_agent(event.chat.chat_id, event.message.body.text)
    if LOG_LEVEL == 'DEBUG':
        rich.print(f'[yellow]Agent response:[/yellow] {agent_response}')

    if not agent_response:
        agent_response = 'Извините, я не смог найти ответ на ваш запрос.'

    await event.message.answer(
        f'*Ответ помощника*:\n\n{agent_response}',
        # parse_mode=ParseMode.MARKDOWN,
    )


async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
