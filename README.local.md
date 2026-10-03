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

## Dependências e produção

As dependências têm versões exatas em `mediataapp/requirements.txt`. Ao atualizar
pacotes, valide o ambiente e registre as novas versões. A imagem base Python
e o PostgreSQL ainda usam tags que recebem atualizações; isso não constitui um
lock completo de todas as dependências transitivas e do sistema operacional.
Este fluxo usa exclusivamente o Compose local. O deploy de produção permanece
no fluxo documentado em README.md. Não use credenciais de produção localmente.
