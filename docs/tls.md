# Certificado HTTPS e renovação

O certificado de `mediatanordeste.com.br` e `www.mediatanordeste.com.br` é
renovado na própria VM. O timer `mediata-tls-renewal.timer` executa a rotina a
cada seis horas, com primeira verificação prevista cinco minutos após a
inicialização e atraso aleatório de até 15 minutos.
Essa rotina não depende de commits, GitHub Actions ou do computador de
desenvolvimento estar ligado.

O certificado ativo pertence à linhagem `mediatanordeste.com.br-0001`, dentro
do volume `certbot/conf`. O Nginx usa os arquivos dessa mesma linhagem. A
validação ACME utiliza `webroot`, com a pasta `certbot/www` compartilhada entre
Nginx e Certbot. Assim, a renovação não precisa interromper o atendimento HTTP.

## Instalar ou atualizar a rotina na VM

Disponibilize na VM as versões revisadas dos scripts e das unidades systemd.
O deploy da aplicação não atualiza automaticamente o checkout de produção.
Com Docker, Python 3, OpenSSL, curl, flock e systemd disponíveis, execute na VM:

```bash
cd /home/antuneszi/projeto-mediata
sudo ./scripts/install-tls-renewal.sh --project-dir /home/antuneszi/projeto-mediata
```

O instalador configura `mediata-tls-renewal.service` e
`mediata-tls-renewal.timer`. O executável instalado fica em
`/usr/local/lib/mediata/renew-tls.sh`, e a configuração local fica em
`/etc/mediata/tls.env`. Arquivos e estado anteriores ficam registrados em
um diretório de transição dentro de `/var/backups/mediata-tls`.

A migração deve manter apenas essa rotina como responsável pela renovação.
O serviço Certbot do Compose permanece disponível para executar comandos,
sem um segundo loop de renovação. O workflow do GitHub passa a monitorar o
HTTPS público, sem acesso SSH ou alteração da VM.

Antes de desativar uma rotina antiga, confirme qual configuração ela usa.
Nesta VM, o `certbot.timer` do host usava outro certificado em
`/etc/letsencrypt`, com `standalone`, e falhava porque a porta 80 já estava
ocupada pelo Nginx. Essa instalação é diferente do volume ativo dos
contêineres. O instalador testa a nova rotina antes de desativar esse timer e
preserva os arquivos antigos para auditoria. Na transição, aguarde o término
de qualquer execução antiga do GitHub antes de trocar seu workflow pelo
monitoramento externo.

## Verificar validade e funcionamento

A verificação pública funciona de qualquer computador com Python 3 e acesso
à internet. Ela valida domínio, cadeia de confiança e vencimento dos dois
endereços:

```bash
python3 scripts/check-tls.py
```

As saídas são `0` para pelo menos 30 dias de validade, `1` para sete dias ou
mais e menos de 30 dias, e `2` para menos de sete dias ou erro de
conexão/validação. O relatório JSON informa o vencimento em UTC e São Paulo,
o tempo restante e quando a verificação foi feita.

Na VM, use a rotina instalada para verificar o certificado servido pelo
Nginx e sua correspondência com o certificado ativo em disco:

```bash
sudo /usr/local/lib/mediata/renew-tls.sh --check
```

Para testar a renovação com o ambiente de testes da autoridade certificadora:

```bash
sudo /usr/local/lib/mediata/renew-tls.sh --dry-run
```

O teste usa staging e não substitui o certificado público. Ele também valida
a configuração, recarrega o Nginx com o certificado atual e confirma sua
correspondência com o arquivo em disco. Um teste bem-sucedido confirma essa
integração naquele momento; continue acompanhando o timer e a validade do
HTTPS público.

Para executar a rotina de produção fora do horário do timer:

```bash
sudo systemctl start mediata-tls-renewal.service
```

A execução normal renova quando necessário, valida a configuração do Nginx,
recarrega o proxy e verifica o certificado servido. Não use `--force-renewal`
como rotina: verificações frequentes não exigem nova emissão a cada execução.

## Consultar execução e logs

```bash
systemctl status mediata-tls-renewal.timer mediata-tls-renewal.service
systemctl list-timers mediata-tls-renewal.timer
sudo journalctl -u mediata-tls-renewal.service --since "2 days ago" --no-pager
```

O serviço é `oneshot`; estar inativo depois de uma execução concluída é
normal. Confira o resultado da última execução, os logs e o próximo horário
do timer. Uma falha exige revisar a mensagem registrada, conectividade,
resolução DNS, resposta HTTP na porta 80 e os contêineres Certbot/Nginx.

## Monitoramento e avisos

O workflow `.github/workflows/renew-certificates.yml` monitora o certificado
público diariamente. O cron está definido para 08:17 UTC, equivalente a
05:17 em São Paulo, mas o GitHub pode atrasar execuções. O relatório fica no
resumo da execução. Menos de 30 dias gera anotação de aviso e falha da
verificação; menos de sete dias ou erro TLS gera anotação de erro e falha.

As notificações de falha dependem das preferências da conta no GitHub.
Configure os destinatários/canais desejados e confira se as notificações de
GitHub Actions estão habilitadas. Este projeto não configura envio de e-mail,
Slack ou outras mensagens. Também não há garantia de notificação quando um
workflow deixa de executar.

Em repositórios públicos, o GitHub pode desativar workflows agendados após
60 dias sem atividade. Por isso, Actions é uma verificação adicional: a
renovação continua no timer local da VM. Consulte a
[documentação de agendamentos do GitHub](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Recuperação

Se a nova rotina apresentar erro, consulte os logs antes de gerar outro
certificado. Confirme os caminhos da linhagem ativa e o volume montado no
Nginx. Compare o certificado servido com o arquivo público `fullchain.pem`;
renovar o arquivo sem ativá-lo no proxy não atualiza o HTTPS atendido.

Para interromper temporariamente a rotina enquanto investiga:

```bash
sudo systemctl disable --now mediata-tls-renewal.timer
```

Essa ação mantém o certificado já instalado, mas interrompe futuras
renovações automáticas. Depois de corrigir a causa, valide com `--check` e
`--dry-run` e reative o timer:

```bash
sudo systemctl enable --now mediata-tls-renewal.timer
```

Não volte ao timer antigo do host com `standalone` nesta VM: ele usa a
configuração que conflita com o Nginx. Preserve um backup dos scripts e das
unidades anteriores para permitir restaurar a implementação sem apagar os
certificados ativos. O instalador tenta restaurar os arquivos e o estado
anteriores se a migração falhar; consulte o diretório de backup indicado no
log. `scripts/generate-certificate-now.sh` foi substituído por instruções para
os comandos seguros de instalação, teste e renovação. Não restaure a versão
antiga desse script, que apagava os diretórios locais do Certbot.

Certificados, chaves privadas, contas ACME e backups locais permanecem fora
do Git. Registre no repositório apenas configuração, procedimentos e scripts.
Detalhes sobre renovação e hooks estão no
[manual do Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html#renewing-certificates).
