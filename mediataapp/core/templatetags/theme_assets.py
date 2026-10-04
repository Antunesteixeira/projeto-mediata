from functools import lru_cache
from hashlib import sha256
from pathlib import Path

from django import template
from django.conf import settings
from django.templatetags.static import static


register = template.Library()
THEME_ROOT = Path(__file__).resolve().parent.parent / 'static' / 'mediata'
THEME_FILES = {'css/app.css', 'js/app.js'}


def _read_digest(name):
    return sha256((THEME_ROOT / name).read_bytes()).hexdigest()[:12]


_cached_digest = lru_cache(maxsize=2)(_read_digest)


@register.simple_tag
def theme_asset(name):
    """Uma alteração do tema gera uma nova URL, inclusive com cache no Nginx."""
    if name not in THEME_FILES:
        raise ValueError(f'Arquivo de tema não reconhecido: {name}')
    digest = _read_digest(name) if settings.DEBUG else _cached_digest(name)
    return f'{static(f"mediata/{name}")}?v={digest}'
