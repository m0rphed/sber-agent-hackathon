# Telegram Bot
FROM python:3.12-slim

WORKDIR /app

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# copy workspace root files
COPY pyproject.toml uv.lock ./

# copy this package
COPY packages/bot-telegram ./packages/bot-telegram

# copy shared libs
COPY libs ./libs

# install dependencies
RUN uv sync --frozen --package bot-telegram --no-dev

# run bot
CMD ["uv", "run", "--package", "bot-telegram", "python", "-m", "bot_telegram"]
