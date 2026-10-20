# Contrato de execução em contêiner

> Estado: implementado e validado localmente até o bloco INFRA-006. Dockerfile, Compose, smoke e evidências de execução estão disponíveis; publicação permanece pendente de autorização explícita.

## 1. Objetivo

Empacotar a aplicação em uma imagem reproduzível e fornecer um ambiente Docker Compose para execução, testes e homologação sem colocar banco, credenciais ou localizações reais dentro da imagem.

O contrato preserva a separação atual entre domínio, aplicação, infraestrutura e apresentação. Contêineres configuram o processo e seus recursos; não substituem os casos de uso nem os repositories.

## 2. Modos suportados

| Modo | Finalidade | Google real | Dados persistentes | Exposição |
|---|---|---:|---:|---|
| `demo` | desenvolvimento e homologação funcional | não | volume descartável ou nomeado | somente `127.0.0.1` no host |
| `test` | suíte automatizada determinística | não | temporários | sem porta pública e, quando possível, sem rede externa |
| `real-local` | validação manual opt-in | sim | SQLite e cache de autenticação em volumes separados | somente `127.0.0.1` no host |
| `cloud-single` | uma instância atrás de gateway privado | sim, condicional | volume persistente e secret store | somente por proxy autenticado com TLS |

`demo` será o modo padrão do Compose. O modo real deve exigir seleção explícita para impedir autenticação ou consultas externas acidentais.

## 3. Contrato da imagem

- base Linux com Python 3.12 em versão fixada;
- diretório de aplicação: `/app`;
- processo executado por usuário sem privilégios;
- porta interna: `8765/tcp`;
- código e dependências imutáveis dentro da imagem;
- bytecode e saída temporária fora do contexto versionado;
- execução sem tentativa de abrir navegador;
- saída operacional em `stdout` e `stderr`, sem tokens, IDs canônicos, payloads ou coordenadas;
- `SIGTERM` deve encerrar servidor, worker e conexões antes da parada;
- healthcheck deve consultar `GET /api/v1/health`.

Comando-alvo da imagem:

```text
python -B main.py --host 0.0.0.0 --port 8765 --database /data/find_hub.db --no-browser [--demo]
```

Esse comando funciona somente quando `GFMT_ALLOW_NON_LOOPBACK=true` e as allowlists de hosts e origens estão completas. Sem esse opt-in, o servidor continua rejeitando bind não loopback.

## 4. Configuração necessária

O bloco INFRA-002 adicionou configuração equivalente a:

| Variável | Padrão seguro | Uso |
|---|---|---|
| `GFMT_MODE` | `demo` no Compose | `demo` ou `real` |
| `GFMT_BIND_HOST` | `127.0.0.1` fora de contêiner | endereço interno do processo |
| `GFMT_PORT` | `8765` | porta HTTP interna |
| `GFMT_DATABASE_PATH` | `/data/find_hub.db` em contêiner | arquivo SQLite persistente |
| `GFMT_AUTH_FILE` | não configurado em demo | cache de autenticação montado externamente |
| `GFMT_TRUSTED_HOSTS` | somente hosts locais | allowlist de `Host` recebidos |
| `GFMT_TRUSTED_ORIGINS` | somente origens locais | allowlist exata para operações mutáveis |
| `GFMT_ALLOW_NON_LOOPBACK` | `false` | opt-in explícito para bind interno do contêiner |

Valores de host/origin não podem aceitar curingas em produção. Cabeçalhos de proxy só podem ser considerados quando vierem de um proxy confiável configurado.

## 5. Persistência

| Caminho lógico | Acesso | Conteúdo | Política |
|---|---|---|---|
| `/data` | leitura/escrita | SQLite, WAL e SHM | volume persistente; backup consistente |
| `/state/auth` | leitura/escrita no modo real | cache de autenticação | volume ou secret store privado; nunca imagem ou Git |
| `/tmp` | leitura/escrita | temporários | descartável e sem dados duráveis |
| `/app` | somente leitura em runtime | aplicação | não armazenar estado |

SQLite, `-wal` e `-shm` devem permanecer no mesmo volume. O modo `cloud-single` aceita somente uma réplica gravando no banco. Escala horizontal exige trocar a persistência por um banco compartilhado e está fora deste bloco.

O código atual fixa o cache em `Auth/secrets.json` e permite escrita. Antes do modo real containerizado, o caminho deve ser configurável ou receber um volume gravável exatamente nesse arquivo/diretório. Docker secrets somente leitura não atendem ao comportamento atual.

## 6. Rede e segurança

- Compose publica `127.0.0.1:8765:8765`; não publica em todas as interfaces.
- O processo pode escutar `0.0.0.0` somente dentro do namespace do contêiner e com opt-in explícito.
- Cloud deve colocar a aplicação atrás de TLS e autenticação/autorização externa.
- O backend continua validando `Host`, `Origin` e token CSRF.
- O serviço não deve confiar automaticamente em `X-Forwarded-*`.
- Banco, autenticação e endpoints mutáveis não podem ficar expostos diretamente à internet.
- Nenhuma credencial entra em `ARG`, `ENV` de build, camada da imagem, log ou arquivo Compose versionado.
- A imagem deve executar como usuário não root e, quando viável, com filesystem raiz somente leitura.

Saídas de rede:

- modo `test`: nenhuma dependência de Google, CDN ou tiles reais;
- modo `demo`: somente Leaflet CDN e tiles OpenStreetMap para visualização, salvo vendorização futura;
- modo `real`: dependências anteriores mais endpoints Google/Nova/Spot/FCM usados pelos adapters existentes.

## 7. Contrato do Docker Compose

O Compose deve reutilizar a mesma imagem em todos os modos e definir:

### Serviço `app`

- perfil/default `demo`;
- porta publicada apenas em loopback;
- volume nomeado para `/data`;
- healthcheck com timeout e tentativas limitadas;
- `init: true` ou tratamento equivalente de sinais;
- `restart: unless-stopped` somente para homologação, não para testes;
- sem volume com o código-fonte no perfil de homologação.

### Serviço `app-real`

- profile explícito `real`;
- mesmo build do serviço demo;
- volume separado de autenticação;
- nenhuma credencial embutida no YAML;
- uma única réplica.

### Serviço `tests`

- profile `test`;
- comando `python -B -m unittest discover -s tests -v`;
- banco temporário;
- sem credenciais reais;
- sem acesso aos serviços Google;
- saída diferente de zero se algum teste falhar.

Um serviço Selenium/Chrome separado só será adicionado se o E2E containerizado exigir. Ele não é necessário para o primeiro Compose e não deve bloquear os testes unitários e de integração.

Não haverá serviço PostgreSQL, Redis ou fila enquanto a aplicação não os utilizar. Adicionar recursos fictícios não simula o sistema real.

## 8. Healthcheck e observabilidade

`GET /api/v1/health` é o contrato inicial de readiness porque verifica a API e o acesso ao SQLite. O healthcheck:

- não consulta Google;
- não retorna IDs, coordenadas ou caminhos;
- deve falhar quando o banco não puder ser aberto;
- deve funcionar sem autenticação Google;
- deve ser acessado internamente pelo contêiner.

Logs devem registrar somente inicialização, modo, estado de jobs e códigos de erro sanitizados. Dados privados não podem ser usados como labels, nomes de contêiner, métricas ou healthcheck.

## 9. Autenticação Google

A primeira autenticação pode exigir Chrome interativo. Portanto:

- `demo`, `test` e homologação sintética não dependem de Chrome;
- uma sessão real não pode ser criada automaticamente durante build ou startup;
- o cache não pode ser copiado da máquina do desenvolvedor para a imagem;
- `cloud-single` fica condicional a um fluxo documentado de provisionamento/renovação do cache;
- expiração deve produzir erro sanitizado e não reinício infinito.

A instalação de Chrome dentro da imagem de runtime não será presumida. Ela só será adicionada após teste que demonstre sua necessidade e um fluxo de autenticação compatível com o ambiente escolhido.

## 10. Contexto de build

O `.dockerignore` futuro deve excluir, no mínimo:

- `.git`, `.github` quando não necessária ao runtime e caches de ferramentas;
- `Auth/secrets.json` e outros arquivos de autenticação;
- `*.db`, `*.db-wal`, `*.db-shm`, `*.sqlite*`;
- `__pycache__`, `*.pyc`, `.pytest_cache` e ambientes virtuais;
- screenshots, artefatos de smoke e relatórios locais;
- firmware e binários que não participam do servidor, após confirmar que nenhum import runtime depende deles.

Após o build, a imagem deve ser inspecionada para provar que esses dados não aparecem em nenhuma camada.

## 11. Aceite dos próximos blocos

Antes de qualquer commit da infraestrutura:

1. `docker compose config` deve validar o arquivo;
2. a imagem deve ser construída do zero;
3. o contêiner deve executar como não root;
4. o healthcheck deve ficar saudável;
5. frontend e API devem abrir via porta publicada em loopback;
6. o fluxo demo deve sincronizar devices e localizações;
7. recriar o contêiner deve preservar o SQLite;
8. o serviço de testes deve concluir a suíte sem Google real;
9. parada normal deve encerrar servidor e worker;
10. logs e camadas devem passar por auditoria de segredos;
11. o comportamento e as limitações devem ser documentados no README;
12. o implementador deve revisar o diff e explicar cada decisão antes do commit.

O modo real terá teste separado, manual e opt-in. Falha ou ausência desse teste não pode ser escondida por resultados do modo demo.

## 12. Lacunas atuais e ordem de execução

| Ordem | Bloco | Estado | Entrega |
|---:|---|---|---|
| 1 | INFRA-001 | COMPLETO | contrato de runtime, segurança, volumes e aceite |
| 2 | INFRA-002 | COMPLETO | configuração container-aware e testes de Host/Origin/bind |
| 3 | INFRA-003 | COMPLETO | Dockerfile e `.dockerignore`; contrato estático aprovado, build aguarda o engine |
| 4 | INFRA-004 | COMPLETO | Compose validado para demo, real e testes isolados |
| 5 | INFRA-005 | COMPLETO | smoke localhost, persistência pós-reinício, README e validação Compose no CI |
| 6 | INFRA-006 | COMPLETO | build limpo, execução, persistência, testes e auditoria local aprovados |
| 7 | INFRA-007 | COMPLETO | revisão final, commit, push e PR sucessor após autorização explícita |

Em 2026-10-20, o Docker Engine `29.6.2` executou o INFRA-006. A imagem foi construída sem cache, executada como usuário não root, validada por healthcheck e smoke, recriada com persistência do SQLite e auditada sem indícios de segredos nas variáveis, camadas ou logs. A evidência sanitizada está em [`artifacts/INFRA-006-VALIDATION.md`](artifacts/INFRA-006-VALIDATION.md).

O INFRA-007 publica este conjunto em uma branch rastreada e em um pull request sucessor. O PR anterior já estava mesclado e permanece imutável; nenhuma operação de merge faz parte deste bloco.

## 13. Regra reutilizável

Uma imagem só é publicável quando o mesmo artefato passa por testes, homologação e inspeção de segredos; diferenças entre ambientes entram por configuração e volumes, nunca por credenciais ou código incorporado à imagem.
