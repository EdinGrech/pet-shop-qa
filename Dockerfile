FROM python:3.13.7-slim

WORKDIR /app
COPY scripts/requirements*.txt ./
RUN pip install --no-cache-dir --disable-pip-version-check -r requirements.txt -r requirements-test.txt
COPY scripts/ ./

CMD ["python", "app.py"]
