FROM python:3.13-alpine

WORKDIR /app

RUN apk add --no-cache gcc postgresql17 postgresql17-dev
RUN pip3 install --upgrade uv

COPY pyproject.toml .
COPY uv.lock .

RUN uv sync

COPY main.py .
COPY auth.py .
COPY database.py .
COPY get_me.py .

STOPSIGNAL SIGKILL

ENTRYPOINT ["uv", "run", "main.py"]
