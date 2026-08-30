FROM python:3.12-slim
WORKDIR /app
RUN python -m pip install --no-cache-dir fastapi uvicorn 'psycopg[binary]>=3.2,<4'
COPY src/payment_lab ./payment_lab
USER 65534:65534
CMD ["uvicorn", "payment_lab.main:app", "--host", "0.0.0.0", "--port", "8080"]
