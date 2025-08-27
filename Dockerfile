FROM python:3.12-alpine
LABEL maintainer="antunesteixeira@outlook.com"

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Primeiro: copiar apenas o requirements.txt
COPY mediataapp/requirements.txt /tmp/requirements.txt

# Instalar dependências do sistema primeiro
RUN apk add --no-cache \
    jpeg-dev zlib-dev git gcc musl-dev python3-dev \
    pango cairo pango-dev cairo-dev \
    py3-pip py3-pillow py3-cffi \
    g++ libffi-dev gdk-pixbuf-dev giflib-dev fontconfig ttf-dejavu

# Criar venv e instalar dependências Python
RUN python -m venv /venv && \
    /venv/bin/pip install --upgrade pip && \
    /venv/bin/pip install -r /tmp/requirements.txt && \
    rm /tmp/requirements.txt

# Agora copiar o restante da aplicação
COPY mediataapp /mediataapp
COPY scripts /scripts

WORKDIR /mediataapp

EXPOSE 8000

# Configurações de usuário e permissões
RUN adduser --disabled-password --no-create-home duser && \
    mkdir -p /data/web/static && \
    mkdir -p /data/web/media && \
    chown -R duser:duser /venv /data/web /mediataapp /scripts && \
    chmod -R 755 /data/web && \
    chmod -R +x /scripts

ENV PATH="/scripts:/venv/bin:$PATH"

USER duser

CMD ["commands.sh"]
