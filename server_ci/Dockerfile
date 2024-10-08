FROM python:3.11-slim

ARG GUARDRAILS_TOKEN
ARG GUARDRAILS_TEMPLATE="guard-template.json"

# Set environment variables to avoid writing .pyc files and to unbuffer Python output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV LOGLEVEL="DEBUG"
ENV GUARDRAILS_LOG_LEVEL="DEBUG"
ENV APP_ENVIRONMENT="production"
ENV GUARDRAILS_TEMPLATE=$GUARDRAILS_TEMPLATE

WORKDIR /app

# Install Git and necessary dependencies
RUN apt-get update && \
    apt-get install -y make git curl gcc jq pipx && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN pipx install poetry

# Ensure poetry is available in the PATH
ENV PATH="/root/.local/bin:$PATH"

# Copy the entrypoint script
COPY /server_ci/entry.sh /app/entry.sh
COPY ../ /app/guardrails

# Install guardrails, the guardrails API, and gunicorn
# openai optional. only used for integration testing
RUN pip install "gunicorn" "guardrails-api"

WORKDIR /app/guardrails

RUN poetry install

RUN pip install ./

RUN guardrails configure --enable-metrics --enable-remote-inferencing --token $GUARDRAILS_TOKEN

# bring in base template
COPY /server_ci/$GUARDRAILS_TEMPLATE /app/$GUARDRAILS_TEMPLATE

# Install Hub Deps and create config.py
RUN guardrails create --template /app/$GUARDRAILS_TEMPLATE


RUN cp -r /usr/local/lib/python3.11/site-packages/guardrails/hub/* /app/guardrails/guardrails/hub

# Expose port 8000 for the application
EXPOSE 8000

# Command to start the Gunicorn server with specified settings
CMD ["/bin/bash", "/app/entry.sh"]