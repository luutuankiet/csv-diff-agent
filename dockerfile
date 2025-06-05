
FROM ghcr.io/astral-sh/uv:debian-slim
WORKDIR /app

# Create a non-root user
RUN adduser --disabled-password --gecos "" myuser

# Change ownership of /app to myuser
RUN chown -R myuser:myuser /app

# Switch to the non-root user
USER myuser

ENV PATH="/home/myuser/.local/bin:$PATH"

COPY --chown=myuser:myuser pyproject.toml /app/agent/
COPY --chown=myuser:myuser csv_diff_agent /app/agent/csv_diff_agent
WORKDIR /app/agent
RUN uv sync


EXPOSE 8000


CMD ["uv", "run", "adk", "web", "--port=8000", "--host=0.0.0.0", "/app/agent"]


# docker run --rm -p 8888:8000 \
#     -v /home/ken/.config/gcloud/application_default_credentials.json:/tmp/creds.json:ro \
#     --env GOOGLE_APPLICATION_CREDENTIALS=/tmp/creds.json \
#     dev-csv-diff
