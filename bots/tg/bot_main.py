import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender
import rich

from agent_sdk.langgraph_functions import chat_with_agent
from bots.tg.config import LOG_LEVEL, TOKEN_TG

if not TOKEN_TG:
    raise ValueError('TOKEN_TG environment variable is not set.')

bot = Bot(token=TOKEN_TG)
dp = Dispatcher()


@dp.message(Command('start'))
async def command_start_handler(message: Message) -> None:
    await message.answer('Это чат-бот ИИ помощника для г. Санкт-Петербург! Чем могу помочь?')


@dp.message()
async def handle_message(message: types.Message):
    if message.text is None:
        await message.answer('Пожалуйста, отправьте текстовое сообщение.')
        return

    _user_id = str(message.from_user.id)
    # показываем "печатает..."
    async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
        try:
            agent_response = await chat_with_agent(_user_id, message.text)
            if not agent_response:
                agent_response = 'Извините, я не смог найти ответ на ваш запрос.'
            await message.answer(
                f'*Ответ помощника*:\n\n{agent_response}',
                # parse_mode='Markdown'
            )

        except Exception as e:
            await message.answer(f'Ошибка: {e}')

    if LOG_LEVEL == 'DEBUG':
        rich.print(
            f'[yellow]Message from [magenta]{_user_id}[/magenta] object:[/yellow]', message.text
        )
        rich.print('[yellow]Agent response:[/yellow]', agent_response)


async def main() -> None:
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
