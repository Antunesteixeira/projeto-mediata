(function () {
    'use strict';

    var config = document.getElementById('whatsapp-config');
    if (!config) return;

    var available = config.dataset.disponivel === 'true';
    var companyId = String(config.dataset.empresaId);
    var state = config.dataset.estado || 'desconectado';
    var states = ['desconectado', 'conectando', 'aguardando_qr', 'conectado', 'erro'];
    if (states.indexOf(state) === -1) state = 'desconectado';
    var sessionStarted = state === 'conectado' || state === 'conectando' || state === 'aguardando_qr';
    var busy = false;
    var locked = false;
    var active = true;
    var failures = 0;
    var requestId = 0;
    var pollTimer = null;
    var controller = null;
    var qrValue = null;
    var tokenField = document.querySelector('#wa-csrf-form [name="csrfmiddlewaretoken"]');
    var csrfToken = tokenField ? tokenField.value : '';

    var status = document.getElementById('wa-status');
    var statusLabel = document.getElementById('wa-status-label');
    var title = document.getElementById('wa-state-title');
    var description = document.getElementById('wa-state-description');
    var feedback = document.getElementById('wa-feedback');
    var connectButton = document.getElementById('wa-connect');
    var refreshButton = document.getElementById('wa-refresh');
    var disconnectRow = document.getElementById('wa-disconnect-row');
    var disconnectOpen = document.getElementById('wa-disconnect-open');
    var disconnectConfirm = document.getElementById('wa-disconnect-confirm');
    var disconnectCancel = document.getElementById('wa-disconnect-cancel');
    var disconnectError = document.getElementById('wa-disconnect-error');
    var stage = document.getElementById('wa-qr-stage');
    var placeholder = document.getElementById('wa-qr-placeholder');
    var placeholderIcon = document.querySelector('#wa-qr-placeholder-icon i');
    var placeholderTitle = document.getElementById('wa-qr-placeholder-title');
    var placeholderText = document.getElementById('wa-qr-placeholder-text');
    var image = document.getElementById('wa-qr-image');
    var caption = document.getElementById('wa-qr-caption');
    var lastCheck = document.getElementById('wa-last-check');

    var labels = {
        desconectado: ['Desconectado', 'Conecte o WhatsApp da empresa', 'Gere o QR Code e faça a leitura com o número que será utilizado por esta empresa.'],
        conectando: ['Conectando', 'Aguardando a conexão', 'Conclua a leitura pelo celular. O status será atualizado automaticamente enquanto esta página estiver aberta.'],
        aguardando_qr: ['Aguardando QR Code', 'Leia o QR Code pelo celular', 'Abra Dispositivos conectados no WhatsApp e faça a leitura do código desta empresa.'],
        conectado: ['Conectado', 'WhatsApp conectado', 'A conexão está ativa para a empresa selecionada. Acompanhe o status ou desconecte o número por aqui.'],
        erro: ['Status indisponível', 'Não foi possível verificar a conexão', 'Tente atualizar o status. Se o problema continuar, procure o administrador do sistema.']
    };

    function setText(element, value) {
        if (element.textContent !== value) element.textContent = value;
    }

    function clearQR() {
        qrValue = null;
        image.hidden = true;
        image.removeAttribute('src');
        caption.hidden = true;
        placeholder.hidden = false;
    }

    function setFeedback(message, inModal) {
        var target = inModal ? disconnectError : feedback;
        setText(target, message || '');
        target.hidden = !message;
    }

    function renderControls() {
        var disabled = !available || locked || busy;
        connectButton.disabled = disabled;
        refreshButton.disabled = disabled;
        disconnectOpen.disabled = disabled;
        disconnectConfirm.disabled = disabled;
        disconnectCancel.disabled = busy;
        connectButton.hidden = state === 'conectado';
        disconnectRow.hidden = !sessionStarted;
        var connectLabel = state === 'aguardando_qr' || state === 'conectando' ? 'Gerar novo QR Code' : 'Conectar WhatsApp';
        setText(connectButton.querySelector('span'), connectLabel);
        config.setAttribute('aria-busy', String(busy));
    }

    function renderState(nextState) {
        state = nextState;
        config.dataset.estado = state;
        if (state === 'conectado' || state === 'conectando' || state === 'aguardando_qr') sessionStarted = true;
        if (state === 'desconectado') {
            sessionStarted = false;
        }
        if (state !== 'aguardando_qr' && state !== 'conectando') clearQR();
        status.className = 'wa-status wa-status-' + state;
        setText(statusLabel, labels[state][0]);
        setText(title, labels[state][1]);
        setText(description, labels[state][2]);
        stage.classList.toggle('is-connected', state === 'conectado');
        placeholderIcon.className = state === 'conectado' ? 'bi bi-check2-circle' : state === 'erro' ? 'bi bi-wifi-off' : 'bi bi-qr-code-scan';
        var pending = state === 'aguardando_qr' || state === 'conectando';
        setText(placeholderTitle, state === 'conectado' ? 'Conexão confirmada' : pending ? 'Aguardando confirmação' : state === 'erro' ? 'Status indisponível' : 'Pronto para conectar');
        setText(placeholderText, state === 'conectado' ? 'O QR Code foi removido. O WhatsApp está conectado a esta empresa.' : pending ? 'Se o código não aparecer ou tiver expirado, clique em “Gerar novo QR Code”.' : state === 'erro' ? 'Atualize o status para verificar a conexão ou tente gerar o QR Code novamente.' : 'Clique em “Conectar WhatsApp” para gerar o QR Code desta empresa.');
        if (qrValue && pending) {
            image.hidden = false;
            placeholder.hidden = true;
            caption.hidden = false;
        }
        renderControls();
    }

    function stopPolling() {
        if (pollTimer !== null) window.clearTimeout(pollTimer);
        pollTimer = null;
    }

    function schedulePolling() {
        stopPolling();
        if (!active || !available || locked || document.hidden) return;
        var pending = state === 'aguardando_qr' || state === 'conectando';
        if (!pending && state !== 'conectado' && !failures) return;
        var delay = failures ? Math.min(120000, 10000 * Math.pow(2, Math.min(failures, 4))) : pending ? 10000 : 30000;
        pollTimer = window.setTimeout(function () { request('status', false); }, delay);
    }

    function scopedURL(value) {
        try {
            var url = new URL(value, window.location.origin);
            return value && url.origin === window.location.origin ? url.href : null;
        } catch (error) {
            return null;
        }
    }

    var urls = {
        conectar: scopedURL(config.dataset.urlConectar),
        status: scopedURL(config.dataset.urlStatus),
        desconectar: scopedURL(config.dataset.urlDesconectar)
    };

    function uiError(message, permanent) {
        var error = new Error();
        error.uiMessage = message;
        error.permanent = Boolean(permanent);
        return error;
    }

    function applyResponse(payload) {
        if (!payload || String(payload.empresa_id) !== companyId) {
            throw uiError('Não foi possível confirmar a empresa desta conexão. Atualize a página.', true);
        }
        if (states.indexOf(payload.estado) === -1) {
            throw uiError('Não foi possível confirmar o status. Tente atualizar a conexão.');
        }
        if (payload.qr_code) {
            if (typeof payload.qr_code !== 'string' || payload.qr_code.length > 2000000 || !/^data:image\/png;base64,[A-Za-z0-9+/=\r\n]+$/.test(payload.qr_code)) {
                throw uiError('O QR Code não pôde ser exibido. Gere um novo código.');
            }
            qrValue = payload.qr_code;
            image.src = qrValue;
        }
        renderState(payload.estado);
        setText(lastCheck, new Intl.DateTimeFormat('pt-BR', {hour:'2-digit', minute:'2-digit', second:'2-digit'}).format(new Date()));
    }

    async function request(kind, manual) {
        if (!active || !available || locked || busy) return;
        if (!urls[kind] || kind !== 'status' && !csrfToken) {
            locked = true;
            clearQR();
            renderState('erro');
            setFeedback('Não foi possível preparar esta conexão. Atualize a página.');
            return;
        }
        stopPolling();
        busy = true;
        renderControls();
        var inModal = kind === 'desconectar';
        if (manual) setFeedback('', inModal);
        var currentRequest = ++requestId;
        var requestController = new AbortController();
        controller = requestController;
        var timeout = window.setTimeout(function () { requestController.abort(); }, 30000);
        var refreshIcon = refreshButton.querySelector('i');
        refreshIcon.classList.add('wa-loading-icon');
        if (kind === 'conectar') {
            clearQR();
            setText(placeholderTitle, 'Gerando QR Code');
            setText(placeholderText, 'Aguarde enquanto a conexão desta empresa é preparada.');
        }
        try {
            var response = await fetch(urls[kind], {
                method: kind === 'status' ? 'GET' : 'POST',
                credentials: 'same-origin',
                cache: 'no-store',
                redirect: 'error',
                headers: Object.assign({'Accept':'application/json'}, kind === 'status' ? {} : {'X-CSRFToken':csrfToken}, kind === 'status' && !manual ? {'X-Mediata-Poll':'1'} : {}),
                signal: requestController.signal
            });
            var payload = await response.json();
            if (!active || currentRequest !== requestId) return;
            if (!payload || String(payload.empresa_id) !== companyId) {
                throw uiError('Não foi possível confirmar a empresa desta conexão. Atualize a página.', true);
            }
            if (!response.ok || payload.ok === false || payload.estado === 'erro') {
                var message = typeof payload.mensagem === 'string' && payload.mensagem.length <= 350 ? payload.mensagem : 'Não foi possível concluir a operação. Atualize o status e tente novamente.';
                throw uiError(message, response.status === 403 || response.status === 404);
            }
            failures = 0;
            setFeedback('');
            setFeedback('', true);
            applyResponse(payload);
            if (kind === 'desconectar' && window.bootstrap) {
                var modal = window.bootstrap.Modal.getInstance(document.getElementById('waDisconnectModal'));
                if (modal) modal.hide();
            }
        } catch (error) {
            if (!active || currentRequest !== requestId) return;
            failures += 1;
            locked = locked || Boolean(error.permanent);
            clearQR();
            renderState('erro');
            setFeedback(error.uiMessage || 'Não foi possível consultar o serviço. Tente atualizar o status novamente.', inModal);
        } finally {
            window.clearTimeout(timeout);
            if (active && currentRequest === requestId) {
                controller = null;
                busy = false;
                refreshIcon.classList.remove('wa-loading-icon');
                renderControls();
                schedulePolling();
            }
        }
    }

    connectButton.addEventListener('click', function () { request('conectar', true); });
    refreshButton.addEventListener('click', function () { request('status', true); });
    disconnectConfirm.addEventListener('click', function () { request('desconectar', true); });
    disconnectOpen.addEventListener('click', function () { setFeedback('', true); });
    image.addEventListener('error', function () {
        if (!qrValue || image.hidden) return;
        clearQR();
        renderState('erro');
        setFeedback('Não foi possível carregar o QR Code. Tente conectar novamente.');
        stopPolling();
    });
    statusLabel.parentElement.setAttribute('aria-live', 'polite');
    document.addEventListener('visibilitychange', function () {
        if (document.hidden) stopPolling();
        else if (active && available && !locked) request('status', false);
    });
    window.addEventListener('pagehide', function () {
        active = false;
        stopPolling();
        clearQR();
        if (controller) controller.abort();
    });
    window.addEventListener('pageshow', function (event) {
        if (!event.persisted) return;
        active = true;
        busy = false;
        clearQR();
        renderControls();
        if (available && !locked) request('status', false);
    });

    if (!available) {
        renderControls();
        setText(placeholderTitle, 'Ativação pendente');
        setText(placeholderText, 'A conexão poderá ser configurada quando o serviço estiver disponível.');
        return;
    }
    renderState(state);
    request('status', false);
}());
