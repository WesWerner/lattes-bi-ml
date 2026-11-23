# Interface do painel (Power BI Desktop)

## Preparação (uma vez)
1. **Exibir → Tamanho da página → 16:9** (1280 x 720). As coordenadas abaixo usam esse tamanho.
2. Crie 7 páginas: Capa, Visão geral, Perfil dos pesquisadores, Temas da produção, Temas: tópicos e perfil, Internacionalização, Qualidade e obras distintas.
3. Em cada página: **Formatar página → Tela de fundo → Imagem → Procurar**, escolha o arquivo da pasta `fundos/`
   (`capa.png`, `pag1_visao_geral.png`, `pag2_perfil.png`, `pag3_temas.png`, `pag4_topicos.png`, `pag5_internacionalizacao.png`, `pag6_qualidade.png`), **Ajuste: Ajustar**, **Transparência: 0%**.
4. As imagens `mapa_*.png` são só guias: mostram onde posicionar cada gráfico (x, y, largura, altura).
   Para posicionar: selecione o visual → **Formatar visual → Geral → Propriedades → Tamanho e posição** e digite os valores.
5. Em cada gráfico: **Formatar visual → Geral → Efeitos → Plano de fundo: desligado** (o cartão branco já vem da imagem),
   e **Título** ligado, fonte Segoe UI Semibold 12, cor #262626.

## Elementos fixos de cada página de conteúdo
| Elemento | Como criar | Posição |
|---|---|---|
| Título da página | Inserir → Caixa de texto, Segoe UI Semibold 20, branco | x16 y10 w700 h40 |
| Navegador | Inserir → Botões → Navegador → Navegador de páginas (horizontal); estilo: texto branco, selecionado em #0072B2 | x760 y10 w504 h40 |
| Segmentação Ano | Campo `d_tempo[ano]`, estilo **Entre** (controle deslizante); intervalo 2000–2026 | x24 y72 w400 h32 |
| Segmentação Tipo | Campo `d_tipo_producao[tipo_producao]`, estilo **Lista** horizontal ou **Mosaico** | x432 y72 w824 h32 |
| Rodapé | Caixa de texto, Segoe UI 9, cinza #5A6B7B | x16 y694 w1248 h22 |

Sincronize as duas segmentações em todas as páginas (**Exibir → Sincronizar segmentações**). Na Capa não há segmentação.
Se a segmentação de Tipo não afetar uma página (por exemplo, Perfil), é normal: nota no rodapé.

## Textos

### Capa
- **Título (painel esquerdo, branco, Segoe UI Semibold 28, x24 y60 w382 h260):**
  Utilização de Business Intelligence e Machine Learning para integração de dados de pesquisas no Brasil
- **Rodapé do painel (branco, Segoe UI 12, x24 y560 w382 h120):**
  Wesley Wernersbach Aranha · Ciência da Computação · UFES · 2026 [acrescente o orientador]
- **Apresentação (x480 y58 w760 h62, Segoe UI 13, #262626):**
  Painel construído a partir de 57.624 currículos da Plataforma Lattes disponibilizados pela STI/UFES, integrados em um Data Warehouse e analisados por modelagem de tópicos. Todos os dados são agregados: não há nomes nem identificadores de pesquisadores, e grupos com menos de 5 pesquisadores são omitidos.
- **Atalhos (um botão transparente por cartão, ação Navegação de página; título Segoe UI Semibold 16 + descrição Segoe UI 11):**
  1. Visão geral: volume e evolução da produção, por tipo e por ano.
  2. Perfil dos pesquisadores: áreas do conhecimento e linhas de pesquisa.
  3. Temas da produção: macrotemas identificados por BERTopic e sua evolução no tempo.
  4. Temas: tópicos e perfil: tópicos de cada macrotema, tipos de produção e grandes áreas.
  5. Internacionalização: países dos eventos, apresentações e outras produções.
  6. Qualidade e obras distintas: cobertura da classificação temática e coautoria.

### Títulos das páginas
Visão geral · Perfil dos pesquisadores · Temas da produção · Temas: tópicos e perfil · Internacionalização · Qualidade e obras distintas

### Rodapés
- **Padrão (todas as páginas):** Fonte: currículos Lattes da UFES (STI/UFES), processados em 2026. Dados agregados; grupos com menos de 5 pesquisadores omitidos.
- **Visão geral (acrescentar):** Itens sem ano informado não aparecem nos gráficos por ano.
- **Perfil (acrescentar):** Um pesquisador pode atuar em mais de uma grande área; as produções por área não somam o total.
- **Temas (acrescentar):** Não inclui itens sem tema. Parte dos itens foi classificada por aproximação (ver página Qualidade).
- **Temas: tópicos e perfil (acrescentar):** Tópicos com menos de 5 pesquisadores são omitidos. Palavras-chave geradas automaticamente (c-TF-IDF); nomes dos macrotemas propostos com apoio de IA.
- **Internacionalização (acrescentar):** Disponível apenas para trabalhos em eventos, apresentações e outras produções.
- **Qualidade (acrescentar):** Considera apenas títulos válidos (3 palavras ou mais).

### Caixas de texto das páginas 5 e 6 (cartão "NOTA")
- **Página 5, "Como ler" (Segoe UI 11):**
  Os países vêm do local do evento (trabalhos em eventos), da apresentação ou da publicação (outras produções). Os demais tipos de produção não informam local e ficam de fora deste painel. "Não informado" indica registros sem país. A proporção fora do Brasil é calculada apenas sobre os registros com país.
- **Página 6, "Notas metodológicas" (Segoe UI 11):**
  Tópico aproximado: o título ficou fora de um tópico do BERTopic e recebeu o tópico mais próximo, desde que a similaridade fosse suficiente. Sem tema: o título não atingiu esse limiar. Obras distintas: títulos únicos por ano e tipo; a razão itens/obras indica quantos currículos, em média, registram a mesma obra (coautoria).

## Cores de apoio
Cabeçalho #0B3C5D · Destaque #0072B2 · Fundo #F2F5F9 · Cartões #FFFFFF · Bordas #D9E0E8 · Texto #262626 · Texto de apoio #5A6B7B

## Nomes curtos das abas (para o navegador de páginas, 6 botões)
Visão geral · Perfil · Temas · Tópicos · Internacional · Qualidade (a Capa fica fora do navegador).
Com 6 botões em 504 px, use fonte 10 e espaçamento de 4 px.
