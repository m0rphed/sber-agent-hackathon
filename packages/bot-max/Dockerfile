# MAX Bot
FROM python:3.12-slim

WORKDIR /app

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# copy workspace root files
COPY pyproject.toml uv.lock ./

# copy this package
COPY packages/bot-max ./packages/bot-max

# copy shared libs
COPY libs ./libs

# install dependencies
RUN uv sync --frozen --package bot-max --no-dev

# run bot
CMD ["uv", "run", "--package", "bot-max", "python", "-m", "bot_max"]
