FROM python:3.12-slim

ARG KUBECTL_VERSION=v1.31.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSLo /usr/local/bin/kubectl \
       "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl" \
    && chmod +x /usr/local/bin/kubectl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir . awscli

USER 65534:65534
EXPOSE 8787
CMD ["uvicorn", "cloudtxn.web:app", "--host", "0.0.0.0", "--port", "8787"]
