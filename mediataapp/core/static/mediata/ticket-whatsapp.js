(function () {
    'use strict';

    var modal = document.getElementById('ticketWhatsAppModal');
    if (!modal) return;

    var form = document.getElementById('ticket-wa-form');
    var confirmation = document.getElementById('ticket-wa-confirmation');
    var confirmButton = document.getElementById('ticket-wa-confirm');
    var refreshButton = document.getElementById('ticket-wa-refresh');
    var cancelButton = document.getElementById('ticket-wa-cancel');
    var closeButtons = modal.querySelectorAll('[data-ticket-wa-close]');
    var loading = document.getElementById('ticket-wa-loading');
    var preview = document.getElementById('ticket-wa-preview');
    var recipientName = document.getElementById('ticket-wa-recipient-name');
    var recipientPhone = document.getElementById('ticket-wa-recipient-phone');
    var message = document.getElementById('ticket-wa-message');
    var result = document.getElementById('ticket-wa-result');
    var resultTitle = document.getElementById('ticket-wa-result-title');
    var resultMessage = document.getElementById('ticket-wa-result-message');
    var lastBlock = document.getElementById('ticket-wa-last');
    var lastState = document.getElementById('ticket-wa-last-state');
    var lastDetail = document.getElementById('ticket-wa-last-detail');
    var lastMessage = document.getElementById('ticket-wa-last-message');
    var review = document.getElementById('ticket-wa-review');
    var reviewed = document.getElementById('ticket-wa-reviewed');
    var csrfField = form.querySelector('[name="csrfmiddlewaretoken"]');
    var csrfToken = csrfField ? csrfField.value : '';
    var expectedCode = String(modal.dataset.ticketCodigo);
    var visible = false;
    var busy = null;
    var ready = false;
    var previewError = false;
    var outcome = null;
    var needsCheck = false;
    var uncertainCarry = false;
    var lastProcessing = false;
    var previewVersion = 0;
    var previewController = null;
    var states = ['processando', 'aceito', 'falhou', 'incerto'];
    var stateLabels = {
        processando: 'Em processamento', aceito: 'Aceito pelo WhatsApp',
        falhou: 'Falhou', incerto: 'Verificação necessária'
    };

    function scopedURL(value) {
        try {
            var url = new URL(value, window.location.origin);
            return value && url.origin === window.location.origin ? url.href : null;
        } catch (error) { return null; }
    }
    var previewURL = scopedURL(modal.dataset.urlPrevia);
    var sendURL = scopedURL(modal.dataset.urlEnviar);

    function text(element, value) { element.textContent = value || ''; }
    function safeMessage(payload, fallback) {
        return payload && typeof payload.mensagem === 'string' && payload.mensagem.length <= 1500 ? payload.mensagem : fallback;
    }
    function showResult(tone, heading, detail) {
        result.className = 'ticket-wa-result' + (tone ? ' is-' + tone : '');
        text(resultTitle, heading);
        text(resultMessage, detail);
        result.hidden = false;
    }
    function clearResult() {
        result.hidden = true;
        text(resultTitle, '');
        text(resultMessage, '');
    }
    function renderControls() {
        var sending = busy === 'send';
        var terminal = Boolean(outcome) || lastProcessing;
        var checkRequired = needsCheck && !reviewed.checked;
        confirmButton.disabled = Boolean(busy) || !ready || terminal || checkRequired;
        confirmButton.hidden = terminal;
        confirmButton.classList.toggle('is-busy', sending);
        text(confirmButton.querySelector('span'), sending ? 'Enviando…' : 'Confirmar envio');
        confirmButton.querySelector('i').className = sending ? 'bi bi-arrow-repeat' : 'bi bi-whatsapp';
        refreshButton.hidden = !(previewError || lastProcessing || outcome === 'falhou' || outcome === 'incerto' || outcome === 'processando');
        refreshButton.disabled = Boolean(busy) || outcome === 'incerto' && checkRequired;
        text(refreshButton.querySelector('span'), outcome === 'incerto' ? 'Carregar nova prévia' : 'Revisar prévia');
        review.hidden = !needsCheck;
        reviewed.disabled = Boolean(busy);
        closeButtons.forEach(function (button) { button.disabled = sending; });
        text(cancelButton, outcome ? 'Fechar' : 'Cancelar');
        modal.setAttribute('aria-busy', String(Boolean(busy)));
    }
    function maskedPhone(value) {
        return typeof value === 'string' && value.length <= 80 && /[*•●xX]/.test(value) && value.replace(/\D/g, '').length <= 8;
    }
    function renderLast(last) {
        lastBlock.hidden = !last || states.indexOf(last.estado) === -1;
        text(lastState, ''); text(lastDetail, ''); text(lastMessage, '');
        if (lastBlock.hidden) return;
        text(lastState, stateLabels[last.estado]);
        var detail = [];
        if (typeof last.criado_em === 'string') {
            var date = new Date(last.criado_em);
            if (!Number.isNaN(date.getTime())) detail.push(new Intl.DateTimeFormat('pt-BR', {dateStyle:'short', timeStyle:'short'}).format(date));
        }
        if (typeof last.usuario === 'string' && last.usuario) detail.push('por ' + last.usuario);
        text(lastDetail, detail.join(' · '));
        text(lastMessage, safeMessage(last, ''));
    }
    function validPreview(payload) {
        return payload && payload.ok === true && String(payload.numero_ticket) === expectedCode
            && payload.destinatario && typeof payload.destinatario.nome === 'string'
            && maskedPhone(payload.destinatario.telefone_mascarado)
            && typeof payload.mensagem === 'string' && payload.mensagem.length > 0
            && typeof payload.confirmacao === 'string' && payload.confirmacao.length > 0 && payload.confirmacao.length <= 16000;
    }
    async function loadPreview(acknowledged) {
        if (!visible || busy === 'send') return;
        var version = ++previewVersion;
        if (previewController) previewController.abort();
        var controller = new AbortController();
        previewController = controller;
        var timeout = window.setTimeout(function () { controller.abort(); }, 15000);
        busy = 'preview'; ready = false; previewError = false; outcome = null; lastProcessing = false;
        needsCheck = false; reviewed.checked = Boolean(acknowledged);
        preview.hidden = true; loading.hidden = false; lastBlock.hidden = true;
        text(recipientName, ''); text(recipientPhone, ''); text(message, '');
        clearResult(); renderControls();
        try {
            if (!previewURL) throw new Error();
            var response = await fetch(previewURL, {method:'GET', headers:{'Accept':'application/json'}, credentials:'same-origin', cache:'no-store', redirect:'error', signal:controller.signal});
            var payload = await response.json();
            if (!visible || version !== previewVersion) return;
            if (!response.ok || !payload || payload.ok !== true) {
                var error = new Error();
                error.uiMessage = safeMessage(payload, 'Revise os dados do responsável e a conexão do WhatsApp da empresa.');
                throw error;
            }
            if (!validPreview(payload)) throw new Error();
            confirmation.value = payload.confirmacao;
            text(recipientName, payload.destinatario.nome);
            text(recipientPhone, payload.destinatario.telefone_mascarado);
            text(message, payload.mensagem);
            renderLast(payload.ultimo_envio);
            preview.hidden = false; ready = true;
            var last = payload.ultimo_envio;
            if (last && last.estado === 'aceito') uncertainCarry = false;
            lastProcessing = Boolean(last && last.estado === 'processando');
            needsCheck = uncertainCarry || Boolean(last && last.estado === 'incerto');
            if (lastProcessing) {
                showResult('', 'Há um envio em processamento', 'Aguarde e confira o WhatsApp. Você pode revisar a prévia novamente para consultar o último envio.');
            } else if (needsCheck && !reviewed.checked) {
                showResult('warning', 'Confira o WhatsApp antes de prosseguir', 'O resultado da tentativa anterior não foi confirmado. Confira a conversa para evitar enviar o mesmo ticket novamente.');
            }
        } catch (error) {
            if (!visible || version !== previewVersion) return;
            previewError = true; ready = false;
            showResult('error', 'Não foi possível preparar a prévia', error.uiMessage || 'Tente revisar a prévia novamente. Nenhum envio é iniciado nesta etapa.');
        } finally {
            window.clearTimeout(timeout);
            if (version === previewVersion) {
                previewController = null; busy = null; loading.hidden = true; renderControls();
            }
        }
    }
    function showOutcome(next, payload) {
        outcome = next; ready = false;
        if (payload && payload.ultimo_envio) renderLast(payload.ultimo_envio);
        else lastBlock.hidden = true;
        if (next === 'aceito') {
            uncertainCarry = false; needsCheck = false;
            showResult('success', 'Envio aceito pelo WhatsApp', safeMessage(payload, 'A solicitação de envio foi aceita.') + '\nA aceitação ainda não confirma a entrega ao destinatário.');
        } else if (next === 'processando') {
            needsCheck = false;
            showResult('', 'Envio em processamento', safeMessage(payload, 'O envio já está sendo processado.') + '\nAguarde e confira o WhatsApp antes de iniciar outra tentativa.');
        } else if (next === 'incerto') {
            uncertainCarry = true; needsCheck = true; reviewed.checked = false;
            showResult('warning', 'Não foi possível confirmar o envio', safeMessage(payload, 'O serviço não confirmou o resultado desta tentativa.') + '\nConfira a conversa no WhatsApp antes de tentar novamente, para evitar o envio em duplicidade.');
        } else {
            uncertainCarry = false; needsCheck = false;
            showResult('error', 'Não foi possível enviar o ticket', safeMessage(payload, 'Revise os dados e prepare uma nova prévia antes de tentar novamente.'));
        }
        renderControls();
    }
    async function send(event) {
        event.preventDefault();
        if (!visible || busy || !ready || outcome || lastProcessing || needsCheck && !reviewed.checked) return;
        if (!sendURL || !csrfToken || !confirmation.value) {
            showOutcome('falhou', {mensagem:'Atualize a página e revise a prévia antes de enviar.'});
            return;
        }
        var token = confirmation.value;
        busy = 'send'; clearResult(); renderControls();
        var controller = new AbortController();
        var timeout = window.setTimeout(function () { controller.abort(); }, 35000);
        try {
            var body = new URLSearchParams({confirmacao:token});
            var response = await fetch(sendURL, {
                method:'POST', credentials:'same-origin', cache:'no-store', redirect:'error',
                headers:{'Accept':'application/json', 'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8', 'X-CSRFToken':csrfToken},
                body:body.toString(), signal:controller.signal
            });
            var payload = await response.json();
            var next = payload && states.indexOf(payload.estado) !== -1 ? payload.estado : response.status >= 400 && response.status < 500 ? 'falhou' : 'incerto';
            showOutcome(next, payload);
        } catch (error) {
            showOutcome('incerto', {mensagem:'A conexão foi interrompida antes da confirmação do resultado.'});
        } finally {
            window.clearTimeout(timeout); busy = null; renderControls();
        }
    }

    modal.addEventListener('show.bs.modal', function () { visible = true; loadPreview(false); });
    modal.addEventListener('hide.bs.modal', function (event) { if (busy === 'send') event.preventDefault(); });
    modal.addEventListener('hidden.bs.modal', function () {
        visible = false; ready = false; previewVersion += 1;
        if (previewController) previewController.abort();
        previewController = null; busy = null;
        preview.hidden = true;
        text(recipientName, ''); text(recipientPhone, ''); text(message, '');
    });
    form.addEventListener('submit', send);
    refreshButton.addEventListener('click', function () {
        if (outcome === 'incerto' && !reviewed.checked) return;
        loadPreview(reviewed.checked);
    });
    reviewed.addEventListener('change', renderControls);
    renderControls();
}());
