FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY careloop ./careloop
RUN pip install --no-cache-dir .
RUN useradd --create-home app && mkdir /data && chown app /data
USER app
ENV CARELOOP_DB=/data/careloop.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8000/healthz')"
CMD ["uvicorn", "careloop.main:create", "--factory", "--host", "0.0.0.0", "--port", "8000"]
