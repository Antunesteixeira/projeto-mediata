# Desenvolvimento local

Pré-requisitos: Git, Docker e Docker Compose v2 com suporte a `up --wait`.
No Windows, use Docker Desktop com integração WSL e execute os comandos no WSL.
No Linux, seu usuário precisa ter acesso ao Docker. Não execute o launcher com sudo.

Depois de clonar o repositório:

```bash
./local.sh setup
```

O comando gera `dotenv_files/.env.dev` com segredos aleatórios se o arquivo não
existir, constrói o ambiente Python no contêiner, inicia PostgreSQL, aplica as
migrações existentes, aguarda o healthcheck e cria o administrador inicial se
não existir. Configuração, senhas e usuários existentes são preservados.
Não é necessário instalar Python ou PostgreSQL na máquina.

Acesse http://localhost:8000 e http://localhost:8000/accounts/login/.
Consulte `DJANGO_SUPERUSER_USERNAME` e `DJANGO_SUPERUSER_PASSWORD` no `.env.dev`.
O modelo versionado é `dotenv_files/.env.dev.example`; não use seus placeholders
como credenciais nem versione o arquivo real.

```bash
./local.sh up -d
./local.sh ps
./local.sh logs -f mediataapp
./local.sh stop
./local.sh start
./local.sh exec mediataapp python manage.py check
./local.sh exec mediataapp python manage.py test
./local.sh exec mediataapp python manage.py makemigrations
```

O código é montado no contêiner e o Django recarrega as alterações. Crie e
versione migrações explicitamente; a inicialização só aplica migrações existentes.
Depois de alterar dependências ou Dockerfile, execute `./local.sh setup` novamente.

## VS Code

Instale a extensão **Dev Containers** e execute **Dev Containers: Reopen in Container**.
A configuração prepara o `.env.dev` e abre o repositório no contêiner com Python
em `/venv/bin/python`, Pylance e terminal na pasta da aplicação. Execute `setup`
antes da primeira abertura para criar o administrador. Ao fechar o editor,
os serviços continuam rodando; use `./local.sh stop` para pará-los.
Não é criada uma `.venv` no computador.

## Dados locais

O projeto Compose é `mediata-local`. PostgreSQL usa o volume persistente
`mediata-local_pgdata_dev`; uploads usam `media_dev`. Os estáticos compartilhados
vêm de `data/web/static` no repositório, montados para leitura pela aplicação.
Os uploads antigos em `data/web/media` continuam na máquina, mas não são
copiados automaticamente para o novo volume.
`./local.sh down` mantém os dados; `./local.sh down -v` apaga os volumes locais.
O banco novo começa vazio e o dashboard pode solicitar o cadastro da empresa.

## Grupo assinante

As migrações garantem os grupos `gerente`, `operador`, `cliente`, `colaborador` e
`assinante`, preservando grupos e vínculos existentes. No cadastro ou na edição
de um usuário, o administrador da plataforma seleciona `assinante` para liberar apenas a abertura de tickets e
o acompanhamento dos chamados da própria conta. O status inicial é Levantamento.

O assinante consulta o status e o histórico e pode editar o número e a descrição
dos próprios tickets somente enquanto estiverem em Levantamento. Ao avançar para
outro status, a edição fica bloqueada. Não pode excluir tickets nem acessar
orçamentos, pagamentos, recebimentos ou cadastros administrativos. No perfil,
pode consultar seus dados e alterar a própria senha.

## Níveis de acesso

| Perfil | Acesso |
| --- | --- |
| Administrador da plataforma | Gestão e valores de todas as empresas. |
| Gerente | Gestão, orçamento, financeiro e relatórios da própria empresa ativa. |
| Operador | Somente tickets cadastrados por ele na própria empresa, com edição operacional, status, histórico e associação de cliente/colaborador. |
| Cliente/colaborador | Acompanhamento dos tickets da própria empresa, sem valores internos. |
| Assinante | Cadastro e acompanhamento dos próprios tickets, conforme as regras de Levantamento. |

O operador tem dashboard operacional limitado aos tickets que cadastrou e acesso
ao próprio perfil. A autoria (`Ticket.usuario`) e a empresa precisam corresponder
à conta: estar atribuído como responsável não concede acesso a tickets de terceiros.
O filtro também vale para busca, detalhes, edição, histórico e associações,
inclusive usando URLs conhecidas. A fila compartilhada e a assunção de tickets
são reservadas à gestão para os perfis operacionais. Orçamentos,
preços de insumos, BDI, pagamentos, recebimentos, documentos financeiros, PDFs
completos, exclusão de tickets e cadastros administrativos ficam reservados à
gestão. As mesmas restrições valem para URLs diretas, requisições POST, arquivos
e dados dos gráficos. Campos financeiros enviados na edição operacional não
são aplicados. Anexos de orçamento seguem a autorização financeira.

A migração `usuarios.0005` remove permissões administrativas antigas do grupo
operador e suas cópias diretas nos operadores, preservando gerentes,
administradores, grupos e vínculos entre usuários e empresas.

## Empresas e fila de atendimento

Em **Configurações → Empresas**, o administrador cadastra as empresas. Em
**Usuários**, associa cada gerente, operador, cliente ou colaborador à empresa
correspondente. O gerente administra apenas a equipe da própria empresa; o
administrador da plataforma acessa todas. Assinantes permanecem sem empresa.
Uma conta interna sem empresa ativa não tem acesso aos módulos de operação.

Os tickets novos de assinantes entram em **Tickets disponíveis**. Empresas ativas
podem consultar a solicitação; um gerente usa **Assumir ticket** para
reservá-la. O administrador também pode assumir, selecionando uma empresa.
Quando duas empresas tentam assumir simultaneamente, apenas uma consegue; a
outra recebe uma mensagem de indisponibilidade. Repetir a operação na mesma
empresa mantém a primeira reserva e não duplica o histórico.

Após a reserva, o ticket sai da fila compartilhada e passa a aparecer na lista,
no dashboard e nos relatórios da empresa responsável. As demais empresas não
acessam o ticket ou seus dados financeiros, mesmo usando URLs conhecidas. O
assinante continua acompanhando o chamado e pode editar número e descrição
somente em Levantamento. A reserva conserva o autor, o código e o status, e
registra separadamente a empresa, o responsável e a data de assunção.

As migrações associam os dados anteriores à empresa de menor ID, mantendo os
IDs, códigos, status e vínculos existentes. O responsável antigo é preservado
sem inventar uma data de assunção. Clientes, colaboradores e insumos são
separados por empresa; CPF, CNPJ e código de insumo podem se repetir entre
empresas, enquanto o código do ticket permanece único no sistema.

Notas fiscais, comprovantes e anexos usam download autenticado em
`/media/nfe/`, `/media/comprovantes/`, `/media/anexos/` e `/media/recebimentos/`.
O Nginx encaminha esses diretórios ao Django para verificar a empresa e o acesso
financeiro do gerente ou administrador; o
servidor local aplica a mesma autorização. A imagem inclui a configuração do
Nginx para o fluxo de deploy instalá-la e validá-la junto com a aplicação.

## Numeração dos tickets

O código é opcional no cadastro. Quando ficar em branco, o sistema usa ano e mês
com dois dígitos cada, seguidos de uma sequência mensal de três dígitos:
`2610001`, `2610002`, etc. Códigos informados manualmente e números existentes
são preservados. Se já houver `2610111`, o próximo automático será `2610112`.

A sequência é compartilhada por todos os usuários, protegida contra cadastros
simultâneos e não reutiliza números de tickets excluídos. Cada mês inicia em
`001`, com limite de `999`; ao atingir o limite, o cadastro pede um código único
informado manualmente. Na edição, deixar o campo em branco mantém o número atual.

## Financeiro

O menu **Financeiro** (`/financeiro/`) reúne pagamentos e recebimentos dos
tickets e lançamentos manuais em uma lista própria, com uma linha por lançamento. Gerentes consultam somente a empresa ativa da conta; o administrador da plataforma consulta todas.
Operadores, perfis de acompanhamento e assinantes não acessam os valores internos.

Filtros disponíveis:

- Operação: créditos e débitos, somente créditos ou somente débitos.
- Situação: todas, pago, recebido, vencido ou em aberto (a vencer).
- Vencimento: todos os períodos, próximos 30/60/90 dias ou personalizado.
- Datas inicial e final inclusivas; os atalhos incluem hoje em N dias.

Vencido significa pendente com vencimento anterior ao dia local atual. Em aberto
significa pendente vencendo hoje ou futuramente. Registros sem vencimento ficam
identificados em Todos os períodos; não recebem uma data presumida. O período
filtra o vencimento do lançamento, sem depender da criação do ticket ou da data
de quitação. Filtros inválidos exibem erros e não retornam lançamentos.

Os indicadores somam todos os registros filtrados, inclusive outras páginas,
com valores recebidos, pagos, a receber, a pagar e vencidos. Valores ausentes
ficam identificados e não entram nas somas. Orçamentos permanecem fora da lista;
os totais descrevem os lançamentos registrados, sem representar saldo bancário.

Use **Editar** ou **Corrigir** na própria lista para atualizar um lançamento e
voltar aos filtros anteriores. Para os registros originados de tickets, os mesmos
campos financeiros são utilizados nas duas telas. Novos registros exigem valor positivo e vencimento; uma nova quitação
exige data efetiva, sem permitir datas futuras. Nos recebimentos, o status é a
fonte única e a confirmação acompanha esse status ao salvar pelo formulário.
Reabrir um lançamento remove sua data efetiva; datas pendentes incoerentes
podem ser corrigidas explicitamente sem apagar dados omitidos na edição.

**Novo lançamento** abre um modal na própria consulta para registrar créditos e
débitos independentes de ticket,
com descrição, cliente/favorecido opcional, valor, vencimento e quitação. A empresa
é definida pela conta; o administrador da plataforma deve escolher uma empresa
ativa. A autoria é registrada no cadastro e a empresa permanece fixa na edição.
Os registros aparecem como **Manual** na coluna de origem e participam dos mesmos
filtros, totais e paginação. Erros de cadastro reabrem o modal com os valores
informados; salvar retorna aos filtros e à página da consulta. Reabrir remove a
data da quitação. A migração
`financeiro.0001` cria a tabela própria sem alterar registros dos tickets.

A migração `tickets.0038` mantém valores, status e datas históricas. Acrescenta
`Pagamentos.data_vencimento` e `data_pagamento_realizado`, sem preencher datas
por suposição; `data_pagamento` anterior é preservada e passa a ser opcional.
Dados antigos incompletos são sinalizados para revisão. A inicialização local
e a de produção aplicam essa migração normalmente.

## Dependências e produção

As dependências têm versões exatas em `mediataapp/requirements.txt`. Ao atualizar
pacotes, valide o ambiente e registre as novas versões. A imagem base Python
e o PostgreSQL ainda usam tags que recebem atualizações; isso não constitui um
lock completo de todas as dependências transitivas e do sistema operacional.
Este fluxo usa exclusivamente o Compose local. O deploy de produção permanece
no fluxo documentado em README.md. Não use credenciais de produção localmente.
