# LangGraph App - Agent Server
FROM python:3.12-slim

WORKDIR /app

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# copy workspace root files
COPY pyproject.toml uv.lock ./

# copy this package
COPY packages/langgraph-app ./packages/langgraph-app

# copy langgraph config to working directory
COPY packages/langgraph-app/langgraph.json ./langgraph.json

# copy shared libs
COPY libs ./libs

# install dependencies
RUN uv sync --frozen --package langgraph-app --no-dev

# copy data and prompts (if needed)
COPY data ./data
COPY prompts ./prompts

# expose port
EXPOSE 2024

# Environment
ENV HOST=0.0.0.0
ENV PORT=2024

# Run LangGraph server
CMD ["uv", "run", "--package", "langgraph-app", "langgraph", "dev", "--no-browser", "--host", "0.0.0.0", "--port", "2024"]