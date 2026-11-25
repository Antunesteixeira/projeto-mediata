# WhatsApp por empresa

A integração usa Evolution API 2.3.8 pelo modo WhatsApp Web/Baileys. Cada empresa
ativa tem uma conexão independente, identificada internamente por UUID. Gerentes
configuram apenas a própria empresa; o administrador da plataforma escolhe a
empresa. Operadores, clientes, colaboradores e assinantes não acessam QR Codes,
configurações ou credenciais.

## Configuração da conexão

O menu **WhatsApp** permite conectar por QR Code, consultar o estado e desconectar
o número da empresa. O callback recebe apenas mudanças de estado da conexão.
As regras de autoria dos operadores continuam sendo aplicadas nos tickets.

A Evolution é executada como serviço separado. A API, o Redis e o PostgreSQL
adicionais têm limites de recursos e não publicam portas no computador ou na VM.
O banco do sistema e o banco da Evolution usam serviços e credenciais diferentes.
Instâncias e autenticação persistem nos volumes do projeto `mediata-whatsapp`.

## Envio do ticket ao responsável

No detalhe do ticket, o botão **Enviar pelo WhatsApp** abre uma prévia com o
responsável, o telefone mascarado e a mensagem. O envio ocorre somente depois
da confirmação. O destinatário é o único colaborador atualmente vinculado ao
ticket; ele precisa estar ativo, pertencer à mesma empresa e ter um telefone
válido cadastrado. Telefones brasileiros com DDD são normalizados com o DDI 55.

A mensagem usa os dados salvos no momento da prévia: número do ticket,
situação, previsão de finalização, descrição do serviço e indicação de
emergencial. Uma previsão não preenchida aparece como **Não informada**.
Se esses dados ou o responsável mudarem antes da confirmação, é necessário
reabrir a prévia. O destinatário e o texto são definidos no servidor.

O gerente e o administrador da plataforma podem enviar nos tickets a que têm
acesso. O operador só pode enviar nos tickets que ele cadastrou na própria
empresa. O envio sempre utiliza a conexão da empresa do ticket. O acesso do
operador ao botão não concede permissão para configurar ou desconectar números.

Cada confirmação tem identificação própria para impedir duplicação por clique
repetido. A auditoria registra autor, data, responsável, destino mascarado e
resultado; não guarda a mensagem completa nem o telefone integral. A aceitação
pelo provedor **não confirma entrega nem leitura** pelo responsável. Em timeout
ou falha cujo resultado não possa ser confirmado, confira a conversa no WhatsApp
antes de solicitar novo envio: o sistema não repete o envio automaticamente.
O mesmo conteúdo fica protegido contra repetição por dois minutos. Tentativas
que permanecerem em processamento por mais de cinco minutos são tratadas como
resultado incerto antes de qualquer nova tentativa manual.

O recurso utiliza o endpoint de
[envio de texto da Evolution API](https://github.com/evolution-foundation/evolution-api/blob/2.3.8/src/api/routes/sendMessage.router.ts).
Os testes de envio usam serviços fictícios e nunca disparam mensagens reais.

## Desenvolvimento local

```bash
./whatsapp.sh setup
./whatsapp.sh ps
```

O comando prepara o ambiente local e gera `dotenv_files/.env.whatsapp` com chave
de API e senha próprias, sem sobrescrever o arquivo existente. A geração usa um
contêiner Python; não exige Python instalado no computador. O arquivo tem modo
0600, fica fora do Git e nunca deve ser publicado. O modelo `.env.whatsapp.example`
serve somente de referência. Nenhuma credencial de produção deve ser copiada.

Acesse http://localhost:8000/whatsapp/ como gerente ou administrador. No celular,
abra **WhatsApp → Dispositivos conectados → Conectar dispositivo** e leia o QR
Code da empresa correspondente. O administrador repete o processo na outra
empresa. Use um número diferente para cada empresa.

O Django recebe automaticamente o ambiente opcional quando iniciado por
`local.sh` ou pelo Dev Container do VS Code. Use
[Docker Compose 2.24 ou superior](https://docs.docker.com/compose/how-tos/environment-variables/set-environment-variables/#additional-information-1)
para o arquivo de ambiente opcional. A Evolution acessa o callback local pelo nome
`mediataapp` na rede Docker. Mudanças de configuração exigem recriar o contêiner da aplicação; um
simples recarregamento de página não atualiza variáveis de ambiente.
O endereço de callback precisa estar configurado antes de gerar uma conexão.

```bash
./whatsapp.sh stop
./whatsapp.sh start
./local.sh up -d
```

Parar os serviços preserva sessões e banco. O comando `local.sh` continua
funcionando sem a integração quando não existe `.env.whatsapp`.

## Produção

Antes da ativação, confira memória e disco disponíveis, mantenha backup e
considere a margem de recursos para as duas conexões. As imagens são fixadas por
versão e digest. O limite inicial da API é 768 MiB, com heap de 384 MiB; Redis e
PostgreSQL possuem limites próprios. Isso protege o sistema principal, mas não
substitui a medição de carga e da sincronização dos números reais.

Copie para o diretório do projeto na VM `whatsapp.sh`,
`docker-compose.whatsapp.yml` e `scripts/prepare-whatsapp-env.py`, preservando
os arquivos existentes. A rede `projeto-mediata_mediata-network` precisa existir.
Na VM, execute:

```bash
./whatsapp.sh setup --production
./whatsapp.sh ps --production
```

O ambiente de produção é gerado na própria VM, com callback HTTPS no domínio do
sistema. Esse comando inicia apenas os serviços da integração. O deploy da
aplicação carrega o arquivo opcional `.env.whatsapp` e aplica as migrações
do aplicativo `whatsapp`. O fluxo de deploy faz backup do banco principal antes da troca.
Não é necessário expor a porta 8080 nem o painel global da Evolution na internet.

A configuração pode ser desativada com `EVOLUTION_ENABLED=false` e novo deploy
ou recriação da aplicação. A indisponibilidade da Evolution não impede login,
tickets ou financeiro; ações de conexão mostram uma mensagem de indisponibilidade.

## Segurança e operação

- Chave global e URL interna ficam somente no backend. A interface recebe apenas
  o QR da empresa autorizada e estados de conexão, com respostas sem cache.
- O webhook usa um identificador público aleatório, segredo exclusivo em header
  e validação do nome da instância. Não há credenciais na URL.
- Requisições de terceiros não podem escolher a instância por formulário.
- Criação e desconexão exigem POST e CSRF. Consultar o estado não cria sessões.
- Uma reserva temporária por conexão impede ações simultâneas entre workers.
- A consulta automática de status preserva o prazo de 120 minutos de
  inatividade da sessão; ela não é contabilizada como atividade do usuário.
- Mensagens, contatos, chats e histórico do WhatsApp não são persistidos pela
  configuração inicial da Evolution. Não ativar esses recursos antes de definir
  escopo, retenção e autorização do módulo de atendimento.
- Os volumes e o ambiente contêm material de autenticação. Faça backups privados
  antes de atualizações e preserve esses arquivos para recuperação.
- O modo por QR Code utiliza WhatsApp Web/Baileys e tem dependência das mudanças
  desse protocolo. Não é a integração oficial WhatsApp Cloud API da Meta.

## Licença e atribuição

A página de configuração mostra **Integração com Evolution API** e um link para
o projeto. O serviço é usado sem modificar seus componentes de frontend. A
licença declara Apache 2.0 com condições adicionais de identificação e marca:

- Projeto: https://github.com/evolution-foundation/evolution-api
- Licença da versão: https://github.com/evolution-foundation/evolution-api/blob/2.3.8/LICENSE
- Release utilizada: https://github.com/evolution-foundation/evolution-api/releases/tag/2.3.8

Nenhum contato real deve receber mensagens como parte da validação técnica.
