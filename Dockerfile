FROM python:3.12-alpine
LABEL mantainer="antunesteixeira@outlook.com"

ENV PYTHONDONTWRITEBYTECODE 1

ENV PYTHONUNBUFFERD 1

COPY mediataapp /mediataapp
COPY scripts /scripts

WORKDIR /mediataapp

EXPOSE 8000

RUN python -m venv /venv && \
    /venv/bin/pip install --upgrade pip && \
    /venv/bin/pip install -r /mediataapp/requirements.txt && \
    adduser --disabled-password --no-create-home duser && \
    mkdir -p /data/web/static && \
    mkdir -p /data/web/media && \
    chown -R duser:duser /venv && \
    chown -R duser:duser /data/web/static && \
    chown -R duser:duser /data/web/media && \
    chmod -R 755 /data/web/static && \
    chmod -R 755 /data/web/media && \
    chmod -R +x /scripts

ENV PATH="/scripts:/venv/bin:$PATH"

USER duser

CMD ["commands.sh"]

