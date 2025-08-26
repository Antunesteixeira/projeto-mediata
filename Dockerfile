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

# Instalação de dependências do sistema gerador de PDF: WeasyPrint
RUN apk add --no-cache \
    jpeg-dev zlib-dev git gcc musl-dev python3-dev \
    pango cairo pango-dev cairo-dev
RUN apk add py3-pip py3-pillow py3-cffi \
    gcc musl-dev python3-dev pango \
    zlib-dev jpeg-dev openjpeg-dev g++ libffi-dev

# Instalar dependências do WeasyPrint
RUN apk add --no-cache \
    cairo-dev \
    pango-dev \
    gdk-pixbuf-dev \
    giflib-dev \
    musl-dev \
    libffi-dev \
    fontconfig \
    ttf-dejavu

ENV PATH="/scripts:/venv/bin:$PATH"

USER duser

CMD ["commands.sh"]

