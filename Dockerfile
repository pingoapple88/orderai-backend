FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY pyproject.toml ./
RUN pip install --no-cache-dir . || pip install --no-cache-dir \
    fastapi "uvicorn[standard]" sqlalchemy psycopg2-binary alembic pydantic-settings pyjwt httpx
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
