# Kezpo Find Hub — contrato de identidade visual

> Estado: identidade visual implementada e validada até `KEZPO-VISUAL-QA-001` em 2026-10-21. Este documento é a fonte visual do frontend e não altera os contratos da API.

## 1. Fonte de verdade

A identidade deve derivar do site oficial [`kezposolutions.com`](https://kezposolutions.com/), observado em 2026-10-21. Não usar screenshots, aproximações de terceiros ou uma paleta criada apenas para este aplicativo como fonte principal.

| Recurso oficial observado | Uso | SHA-256 da versão observada |
|---|---|---|
| `https://kezposolutions.com/assets/index-CcYPwkxO.css` | tokens, fontes e breakpoints | `90702a586906d937dafd21d4694a4e11b810ec0b7bcca7270674573b0a5bed8d` |
| `https://kezposolutions.com/assets/logo-kezpo-DNm21ieP.webp` | referência do logotipo horizontal | `eba289398cef30e71f3f3f732cdccbeae13f5d2661e7313323ca5eab14e2fad5` |
| `https://kezposolutions.com/favicon.png` | referência do ícone | `03fd1dfd4e13fb3173d23c47d84bff464207f4ff900040eca6fd4918076fd2ca` |

Os nomes com hash podem mudar em um novo deploy do site. O próximo bloco de assets deve baixar uma cópia autorizada para o repositório, registrar sua origem e nunca depender desses endereços em runtime.

## 2. Personalidade visual

A interface deve comunicar engenharia, precisão, confiabilidade e escala global. O aplicativo é uma ferramenta operacional, portanto deve adaptar a marca sem copiar a estrutura promocional do site.

Direção aprovada:

- superfícies claras para dados, listas e controles;
- navy institucional para navegação e áreas de maior hierarquia;
- azul como ação primária e foco;
- dourado como destaque seletivo, nunca como cor dominante;
- composição limpa, geométrica e com alta legibilidade;
- fotografia industrial não é necessária dentro da operação do mapa;
- evitar o mint/cyan atual como identidade principal.

## 3. Tipografia

| Papel | Família | Pesos observados | Fallback |
|---|---|---|---|
| títulos, produto e números de destaque | `Outfit` | 600, 700, 800 | `Inter`, `Segoe UI`, sans-serif |
| corpo, botões, labels e dados | `Inter` | 400, 600, 700 | `Segoe UI`, Arial, sans-serif |
| coordenadas e diagnóstico técnico | fonte monoespaçada do sistema | 400, 600 | `Consolas`, monospace |

Regras:

- não carregar fontes diretamente do Google Fonts no modo operacional;
- preferir arquivos locais com licença preservada no bloco `KEZPO-TYPE-001`;
- manter corpo mínimo de `16px` em smartphone e `14px` em informação auxiliar;
- títulos usam `Outfit`, mas nomes de devices e dados continuam em `Inter`.

## 4. Tokens de cor

Os valores abaixo correspondem aos tokens publicados no CSS oficial na data da observação.

| Token do aplicativo | Origem Kezpo | HSL oficial | Hex de referência | Uso permitido |
|---|---|---:|---:|---|
| `--kezpo-navy` | `--brand-navy` | `225 50% 12%` | `#0f172e` | cabeçalho, navegação e fundo escuro |
| `--kezpo-blue-deep` | `--brand-blue-deep` | `225 85% 25%` | `#0a2576` | hover escuro e hierarquia |
| `--kezpo-blue` | `--brand-blue` | `225 80% 45%` | `#1745cf` | ação primária, links e foco |
| `--kezpo-blue-light` | `--brand-blue-light` | `199 90% 55%` | `#25b2f4` | informação, rede e realces secundários |
| `--kezpo-gold` | `--brand-gold` | `38 90% 55%` | `#f4a825` | seleção, marcador próprio e destaque |
| `--kezpo-gold-dark` | `--brand-gold-dark` | `35 80% 40%` | `#b87614` | borda/hover dourado |
| `--kezpo-gold-light` | `--brand-gold-light` | `40 85% 65%` | `#f2bf5a` | destaque sobre navy |
| `--kezpo-surface` | `--background` | `0 0% 100%` | `#ffffff` | fundo principal |
| `--kezpo-surface-soft` | `--brand-gray` | `220 10% 96%` | `#f4f5f7` | cards e grupos |
| `--kezpo-border` | `--border` | `220 15% 88%` | `#dde0e5` | divisórias e contornos |
| `--kezpo-danger` | `--destructive` | `0 84% 60%` | `#ef4444` | falha e ação destrutiva |

Regras semânticas do mapa:

- report da rede: `--kezpo-blue-light`;
- report próprio: `--kezpo-gold`;
- device selecionado: `--kezpo-blue` com anel de foco;
- histórico: `--kezpo-blue-deep`, variando traço/opacidade e não apenas cor;
- sucesso operacional: verde semântico separado da marca;
- erro: `--kezpo-danger`, acompanhado de ícone e texto;
- nenhuma informação pode depender somente da percepção de cor.

## 5. Forma, espaçamento e elevação

- raio-base oficial: `0.5rem` (`8px`);
- controles principais: raio entre `8px` e `12px`, sem aparência excessivamente arredondada;
- escala de espaçamento: `4, 8, 12, 16, 24, 32, 48px`;
- borda padrão: `1px solid var(--kezpo-border)`;
- sombras devem indicar elevação funcional, não decoração;
- painel móvel pode usar sombra superior; cards de lista permanecem discretos;
- alvos interativos devem ter pelo menos `44 × 44px`.

## 6. Marca no produto

Cabeçalho recomendado:

- logotipo Kezpo horizontal;
- nome do produto: `Find Hub Map`;
- descriptor curto: `Operações de localização`;
- estado de ambiente separado: `Demo`, `Local real` ou `Homologação`;
- não usar o logotipo como botão sem nome acessível;
- variante normal sobre superfície clara e variante invertida sobre navy.

O texto legal deve preservar as atribuições Leaflet e OpenStreetMap, sem sugerir que a Kezpo ou o Google são os provedores dos tiles.

## 7. Breakpoints e comportamento

Os breakpoints seguem a escala publicada pelo site oficial:

| Faixa | Contrato do aplicativo |
|---|---|
| `< 640px` | smartphone compacto; mapa prioritário e painel inferior |
| `640–767px` | smartphone amplo; ações podem formar duas colunas |
| `768–1023px` | tablet; painel recolhível sobre o mapa |
| `1024–1279px` | desktop; painel lateral persistente |
| `1280–1399px` | desktop amplo; mais contexto sem ampliar demais os cards |
| `≥ 1400px` | canvas máximo; mapa cresce e painel mantém largura controlada |

Também é obrigatório respeitar `prefers-reduced-motion: reduce`. Animações de mapa acionadas pelo usuário podem permanecer, mas transições decorativas devem ser reduzidas.

## 8. Acessibilidade e contraste

- foco visível azul com offset em superfícies claras;
- foco azul-claro ou dourado-claro em navy;
- contraste mínimo WCAG AA para textos e controles;
- dourado não deve ser usado para texto pequeno sobre branco;
- status usa texto, ícone e cor;
- cards clicáveis precisam ser operáveis por teclado;
- o mapa deve ter nome acessível e uma alternativa textual na lista de reports;
- respeitar zoom de navegador de pelo menos 200% sem perda de ação.

## 9. Mapeamento da interface atual

| Elemento atual | Direção Kezpo |
|---|---|
| fundo escuro integral | mapa com chrome navy e painéis de dados claros |
| título `Find Hub Map` isolado | lockup Kezpo + nome do produto + ambiente |
| botão mint | botão primário azul institucional |
| marcador próprio mint | marcador dourado com forma/ícone distinto |
| marcador de rede cyan | marcador azul-claro |
| cards translúcidos escuros | cards claros com borda neutra |
| único breakpoint em `760px` | cinco faixas alinhadas ao site oficial |
| sidebar fixa no mobile | painel inferior/recolhível com mapa prioritário |

## 10. Critérios para os próximos blocos

Uma implementação só pode afirmar que segue a identidade Kezpo quando:

1. utiliza os tokens deste documento, sem hex disperso nos componentes;
2. usa logo e fontes locais, com licença e origem documentadas;
3. mantém contraste e foco aprovados;
4. funciona nos cinco intervalos de breakpoint;
5. preserva todos os fluxos de sincronização, histórico e mapa;
6. não adiciona trackers, analytics ou chamadas ao site institucional;
7. passa pelos testes funcionais existentes e pela inspeção visual responsiva.

## 11. Estado da implementação

- assets e fontes locais com manifestos de origem;
- tipografia, cores e espaçamento aplicados por tokens;
- shell operacional e componentes responsivos;
- fluxos de cache, sincronização, atualização e histórico preservados;
- navegação por teclado, estados vazios e movimento reduzido validados;
- inspeção visual aprovada nas larguras `1440`, `1300`, `1200`, `900`, `700` e `390px`.

O guia operacional, a matriz responsiva e os comandos reproduzíveis de teste estão em [FRONTEND.md](FRONTEND.md).
