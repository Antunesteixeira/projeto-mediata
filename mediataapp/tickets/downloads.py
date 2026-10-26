import mimetypes
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_http_methods

from core.tenancy import pode_acessar_financeiro, tickets_da_empresa
from .models import Anexo, Pagamentos, Recebimentos


PRIVATE_MEDIA_PREFIXES = frozenset({'nfe', 'comprovantes', 'anexos', 'recebimentos'})
INLINE_EXTENSIONS = frozenset({'.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp'})


@login_required
@require_http_methods(['GET', 'HEAD'])
def arquivo_privado(request, path):
    if not pode_acessar_financeiro(request.user):
        raise PermissionDenied('Seu perfil não permite acessar estes arquivos.')

    relative = PurePosixPath(path)
    if (
        not path or '\\' in path or '\x00' in path
        or relative.is_absolute() or relative.as_posix() != path
        or '..' in relative.parts or len(relative.parts) < 2
        or relative.parts[0] not in PRIVATE_MEDIA_PREFIXES
    ):
        raise Http404('Arquivo não encontrado.')

    tickets = tickets_da_empresa(request.user)
    authorized = (
        tickets.filter(nfe_path=path).exists()
        or Pagamentos.objects.filter(comprovante=path, ticket_pagamento__in=tickets).exists()
        or Recebimentos.objects.filter(comprovante_recebimento=path, ticket_recebimento__in=tickets).exists()
        or Anexo.objects.filter(arquivo=path, ticket_anexo__in=tickets).exists()
    )
    if not authorized:
        raise Http404('Arquivo não encontrado.')

    root = Path(settings.MEDIA_ROOT).resolve()
    try:
        file_path = (root / Path(*relative.parts)).resolve(strict=True)
        if not file_path.is_relative_to(root) or not file_path.is_file():
            raise Http404('Arquivo não encontrado.')
        file_handle = file_path.open('rb')
    except (OSError, RuntimeError, ValueError):
        raise Http404('Arquivo não encontrado.') from None

    content_type = mimetypes.guess_type(file_path.name)[0] or 'application/octet-stream'
    response = FileResponse(
        file_handle,
        as_attachment=file_path.suffix.lower() not in INLINE_EXTENSIONS,
        filename=relative.name,
        content_type=content_type,
    )
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    patch_vary_headers(response, ('Cookie',))
    return response
