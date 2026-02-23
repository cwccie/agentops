FROM python:3.14-slim

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/
COPY scenarios/ scenarios/
COPY README.md .

RUN pip install --no-cache-dir -e .

EXPOSE 8080 8888

ENTRYPOINT ["agentops"]
CMD ["start", "--host", "0.0.0.0", "--port", "8080"]
