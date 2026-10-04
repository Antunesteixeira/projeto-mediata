# Padrão visual do sistema

O dashboard é a referência visual das telas internas: fundo claro, cartões brancos, bordas suaves, títulos escuros e ações azuis.

- `mediataapp/templates/_layout/base.html`: navegação e estrutura das telas autenticadas.
- `mediataapp/templates/_layout/auth_base.html`: estrutura do login.
- `mediataapp/core/static/mediata/css/app.css`: cores, tipografia, cartões, formulários, tabelas, botões e navegação.
- `mediataapp/core/static/mediata/js/app.js`: navegação responsiva e identificação da seção ativa.

Use os componentes Bootstrap com o tema comum. Uma nova tela segue esta estrutura:

```django
{% extends '_layout/base.html' %}
{% block conteudo %}
<div class="app-page">
  <header class="app-page-header">
    <div>
      <h1 class="app-page-title">Título da tela</h1>
      <p class="app-page-description">Descrição da tarefa que esta tela permite realizar.</p>
    </div>
    <div class="app-page-actions">
      <!-- Ações principais da tela -->
    </div>
  </header>
  <div class="card"><div class="card-body">Conteúdo</div></div>
</div>
{% endblock %}
```

Estilos específicos devem usar uma classe da própria tela. Ajustes da estrutura principal usam uma classe definida pelo bloco `body_class`, como `has-payment-report`. Mantenha tabelas largas dentro de `.table-responsive` e preserve o acesso aos valores completos.

Os arquivos do tema são servidos com uma versão calculada pelo conteúdo usando a tag `theme_asset`. Alterações geram novas URLs para o cache do navegador. A inicialização de produção executa `collectstatic` a cada versão, preservando os arquivos existentes no volume.

Os PDFs mantêm sua própria apresentação para impressão.
