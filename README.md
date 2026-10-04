# Projeto Mediata

Sistema Django de cadastro de tickets da MEDIATA.

## Projeto nesta máquina

O clone de desenvolvimento está na Ubuntu WSL:

```bash
cd ~/projetos/projeto-mediata
```

GitHub: `Antunesteixeira/projeto-mediata`. Imagem: `antuneszi/projeto-mediata`.

## Desenvolvimento local

Com Docker e Docker Compose instalados, execute `./local.sh setup`.
Acesse http://localhost:8000. Consulte [README.local.md](README.local.md) para
credenciais, comandos e integração do VS Code com Dev Containers.

## Publicar uma alteração

Cada push na branch `main` inicia automaticamente o GitHub Actions. Ele constrói a imagem, publica no Docker Hub e atualiza a aplicação na VM, mesmo quando o PC estiver desligado após o push.

```bash
git status
git add caminho/do/arquivo-alterado
git commit -m "Descreve a alteração"
git push origin main
```

Para acompanhar ou executar novamente o fluxo:

```bash
gh run list --workflow docker-publish.yml
gh run watch
gh workflow run docker-publish.yml --ref main
```

O fluxo publica as tags `latest` e o SHA completo do commit. O deploy usa a tag do commit que iniciou o workflow. Antes de substituir a aplicação, ele cria um backup PostgreSQL; depois verifica `/health/` e volta à imagem anterior se a aplicação não responder.

O rollback da imagem não desfaz migrações de banco. Alterações de schema exigem planejamento de compatibilidade e restauração do backup quando necessário.

## VM de produção

```bash
ssh google-vm
```

- Projeto Google Cloud: `mediatanordeste`.
- Instância: `instance-20260225-230253`, zona `southamerica-east1-a`.
- IP: `34.39.181.211`. Usuário: `antuneszi`.
- Diretório: `/home/antuneszi/projeto-mediata`.
- Aplicação: `mediataapp_prod`. Banco: `psql_prod`. Proxy: `nginx_prod`.
- Healthcheck público: `https://mediatanordeste.com.br/health/`.

O deploy atualiza apenas o contêiner da aplicação, mantendo os volumes de mídia, os arquivos de ambiente e os ajustes locais da VM. Não atualiza automaticamente o checkout Git nem substitui o Compose da produção.

## Configuração do GitHub Actions

Secrets do repositório:

- `DOCKERHUB_USERNAME` e `DOCKERHUB_TOKEN`.
- `VM_HOST`, `VM_USER` e `VM_SSH_PRIVATE_KEY`.
- `VM_SSH_KNOWN_HOSTS`: chave pública do servidor, obtida de uma conexão verificada.

As credenciais da aplicação ficam em `dotenv_files/.env.prod` na VM. Arquivos `.env`, certificados, uploads e backups não devem ser adicionados ao Git ou à imagem Docker.

A renovação TLS e a recarga do Nginx são executadas pelo timer local da VM,
independentemente do GitHub Actions. O workflow `renew-certificates.yml` monitora
o certificado público e registra avisos de vencimento. Instalação, verificação e
recuperação estão documentadas em [docs/tls.md](docs/tls.md).
