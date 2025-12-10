# Streamlit UI
FROM python:3.12-slim

WORKDIR /app

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# copy workspace root files
COPY pyproject.toml uv.lock ./

# copy this package
COPY packages/streamlit-ui ./packages/streamlit-ui

# copy shared libs
COPY libs ./libs

# install dependencies
RUN uv sync --frozen --package streamlit-ui --no-dev

# expose port
EXPOSE 8501

# environment
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

# run streamlit
CMD ["uv", "run", "--package", "streamlit-ui", "streamlit", "run", "src/streamlit_ui/app.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
