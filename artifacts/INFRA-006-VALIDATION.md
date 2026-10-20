# INFRA-006 — Validação local da infraestrutura

Data: 2026-10-20

Projeto Compose isolado: `gfmt-infra006-20261020`

Imagem validada: `googlefindmytools-map:infra006`

ID curto da imagem: `11c88e8928e5`

Docker Engine: `29.6.2`

## Resultado

| Verificação | Resultado |
|---|---|
| Build com `--pull --no-cache` | aprovado |
| Usuário da imagem | `10001:10001` |
| Tamanho da imagem | 133.027.085 bytes |
| Healthcheck `/api/v1/health` | saudável |
| Smoke demo completo | 2 devices, 2 features, sync e refresh `SUCCEEDED` |
| Cache após recriar o contêiner | 2 devices e 2 features recuperados do volume |
| Suíte dentro da imagem | 77 testes; 76 aprovados e 1 E2E opt-in ignorado |
| Rede do serviço `tests` | `none` |
| Encerramento por `SIGTERM` | código de saída `0` |
| Variáveis sensíveis incorporadas | 0 ocorrências |
| Padrões de segredo no histórico de camadas | 0 ocorrências em 35 camadas |
| Padrões de segredo nos logs | 0 ocorrências |
| Chaves privadas e tokens OAuth no conteúdo da imagem | 0 ocorrências |
| Novos padrões de segredo no diff e arquivos novos | 0 ocorrências |
| Credencial de usuário e banco incorporados à imagem | ausentes |

## Correções descobertas pela execução

1. O servidor passou a tratar `SIGTERM` no processo principal para fechar HTTP, worker e banco antes de sair.
2. A imagem passou a conter os três manifestos usados pelos testes de contrato: `Dockerfile`, `.dockerignore` e `compose.yaml`.
3. O serviço `tests` passou a neutralizar as allowlists de exposição da imagem e usar loopback, evitando que testes CLI em porta efêmera herdem a política do serviço publicado.
4. A tag da imagem no Compose passou a aceitar `GFMT_IMAGE`, permitindo validar uma imagem isolada sem sobrescrever a tag local padrão.

## Limites da evidência

- O teste utiliza somente fixtures sintéticas e não autentica nem consulta serviços Google reais.
- `Auth/fcm_receiver.py`, idêntico ao `HEAD`, contém uma chave pública de configuração do cliente Firebase exigida pelo protocolo legado. A auditoria a distingue de credenciais de usuário, tokens OAuth e chaves privadas; nenhuma dessas credenciais privadas foi encontrada na imagem.
- O E2E com navegador é opt-in e foi ignorado dentro do contêiner; o contrato HTTP, frontend servido, API, jobs e GeoJSON foram exercitados pelos testes e pelo smoke.
- TLS e autenticação de borda continuam responsabilidade do proxy/gateway no deploy em nuvem.
- A imagem local foi preservada para revisão. Contêineres, rede e volumes sintéticos do projeto de validação são removidos ao final do bloco.
