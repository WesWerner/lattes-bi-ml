"""Recorta cada grafico do PDF exportado do Power BI e salva um PNG por grafico.

Uso (com o ambiente ativo; instale uma vez: python -m pip install pymupdf):
    python scripts\\recortar_graficos.py caminho\\painel.pdf [pasta_saida] [--dpi 300]
    python scripts\\recortar_graficos.py caminho\\exportacao.pdf figuras --por-pagina   (uma pagina por grafico)

No Power BI Desktop: Arquivo > Exportar > Exportar para PDF (todas as paginas, 16:9, 1280x720).
Ordem esperada das paginas: 1 Capa, 2 Visao geral, 3 Perfil, 4 Temas, 5 Topicos,
6 Internacionalizacao, 7 Qualidade. As coordenadas sao as de powerbi/INTERFACE.md.
"""
import argparse
import sys
from pathlib import Path

import pymupdf  # PyMuPDF

W, H = 1280, 720  # tamanho logico da pagina no Power BI

# (nome_do_arquivo, x, y, largura, altura) por pagina (indice a partir de 0 = Capa)
RECORTES = {
    1: [("p01_kpis", 16, 118, 1248, 68),
        ("p01_i1_i2_evolucao_por_tipo", 16, 196, 820, 244),
        ("p01_i2_producoes_por_tipo", 844, 196, 420, 244),
        ("p01_i4_faixas_de_producao", 16, 448, 620, 238),
        ("p01_i3_pesquisadores_por_ano", 644, 448, 620, 238)],
    2: [("p02_i5_pesquisadores_por_area", 16, 118, 620, 282),
        ("p02_i6_producoes_por_grande_area", 644, 118, 620, 282),
        ("p02_i7_linhas_de_pesquisa", 16, 408, 1248, 278)],
    3: [("p03_i8_producoes_por_macrotema", 16, 118, 520, 568),
        ("p03_i9_evolucao_macrotemas", 544, 118, 720, 568)],
    4: [("p04_i11_matriz_macrotema_tipo", 16, 118, 620, 568),
        ("p04_i12_arvore_area_macrotema", 644, 118, 620, 250),
        ("p04_i10_tabela_topicos", 644, 376, 620, 310)],
    5: [("p05_i14_mapa_paises", 16, 118, 784, 302),
        ("p05_i14_pct_fora_do_brasil", 808, 118, 456, 302),
        ("p05_i14_top15_paises", 16, 428, 620, 258)],
    6: [("p06_i13_qualidade_classificacao", 16, 118, 620, 282),
        ("p06_i15_razao_itens_obras", 644, 118, 620, 282),
        ("p06_i15_itens_e_obras", 16, 408, 620, 278)],
}


ORDEM = [n for i in sorted(RECORTES) for (n, *_r) in RECORTES[i]]


def por_pagina(a) -> int:
    """Modo 'uma pagina por grafico': converte cada pagina em PNG e apara as bordas em branco."""
    from PIL import Image, ImageChops
    pdf = pymupdf.open(a.pdf)
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    sem_kpis = [n for n in ORDEM if n != "p01_kpis"]
    nomes = ORDEM if len(pdf) == len(ORDEM) else (sem_kpis if len(pdf) == len(sem_kpis) else None)
    if nomes is None:
        print(f"Aviso: o PDF tem {len(pdf)} paginas e a ordem padrao tem {len(ORDEM)}; usando fig_NN.", file=sys.stderr)
    for i, pagina in enumerate(pdf):
        pix = pagina.get_pixmap(dpi=a.dpi)
        im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        caixa = ImageChops.difference(im, Image.new("RGB", im.size, (255, 255, 255))).getbbox()
        if caixa:
            m = 6
            im = im.crop((max(caixa[0] - m, 0), max(caixa[1] - m, 0), min(caixa[2] + m, im.width), min(caixa[3] + m, im.height)))
        nome = nomes[i] if nomes else f"fig_{i + 1:02d}"
        im.save(saida / f"{nome}.png")
    print(f"{len(pdf)} graficos salvos em {saida.resolve()}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("saida", nargs="?", default="figuras_bi")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--por-pagina", action="store_true",
                    help="cada pagina do PDF e um grafico inteiro (pagina de exportacao): salva um PNG por pagina, sem as bordas brancas")
    a = ap.parse_args()
    if a.por_pagina:
        return por_pagina(a)

    pdf = pymupdf.open(a.pdf)
    saida = Path(a.saida)
    saida.mkdir(parents=True, exist_ok=True)
    if len(pdf) < 7:
        print(f"Aviso: o PDF tem {len(pdf)} paginas; o esperado sao 7 (com a Capa).", file=sys.stderr)
    n = 0
    for i, pagina in enumerate(pdf):
        r = pagina.rect
        if abs(r.width / r.height - W / H) > 0.01:
            print(f"Aviso: pagina {i + 1} nao esta em 16:9 ({r.width:.0f}x{r.height:.0f}).", file=sys.stderr)
        pagina.get_pixmap(dpi=a.dpi).save(saida / f"pagina_{i + 1:02d}_completa.png")
        sx, sy = r.width / W, r.height / H
        for nome, x, y, w, h in RECORTES.get(i, []):
            clip = pymupdf.Rect(r.x0 + x * sx, r.y0 + y * sy, r.x0 + (x + w) * sx, r.y0 + (y + h) * sy)
            pagina.get_pixmap(dpi=a.dpi, clip=clip).save(saida / f"{nome}.png")
            n += 1
    print(f"{n} graficos e {len(pdf)} paginas salvos em {saida.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
