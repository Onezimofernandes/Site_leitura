"""
NÃO é o plano usado em produção. O projeto agora usa um plano
cronológico fornecido por você, em data/plano_leitura.json.

Este script gera só um plano de referência, em ordem canônica simples
(Gênesis a Apocalipse), como exemplo do formato esperado pelo script
de envio e como alternativa caso você decida não usar um plano
cronológico. Não reproduz nenhum plano de terceiros: é calculado aqui
a partir da contagem pública de capítulos de cada livro.

Uso:
    python scripts/gerar_plano.py
Gera/atualiza: data/plano_leitura.exemplo-canonico.json
"""

import json
import os

# Nome do livro (como aparece no JSON da AA em thiagobodruk/biblia,
# campo "book") e número de capítulos. A contagem de capítulos é
# invariável entre edições: não depende de tradução.
LIVROS = [
    ("Gênesis", 50), ("Êxodo", 40), ("Levítico", 27), ("Números", 36),
    ("Deuteronômio", 34), ("Josué", 24), ("Juízes", 21), ("Rute", 4),
    ("1 Samuel", 31), ("2 Samuel", 24), ("1 Reis", 22), ("2 Reis", 25),
    ("1 Crônicas", 29), ("2 Crônicas", 36), ("Esdras", 10), ("Neemias", 13),
    ("Ester", 10), ("Jó", 42), ("Salmos", 150), ("Provérbios", 31),
    ("Eclesiastes", 12), ("Cânticos", 8), ("Isaías", 66), ("Jeremias", 52),
    ("Lamentações", 5), ("Ezequiel", 48), ("Daniel", 12), ("Oséias", 14),
    ("Joel", 3), ("Amós", 9), ("Obadias", 1), ("Jonas", 4), ("Miquéias", 7),
    ("Naum", 3), ("Habacuque", 3), ("Sofonias", 3), ("Ageu", 2),
    ("Zacarias", 14), ("Malaquias", 4),
    ("Mateus", 28), ("Marcos", 16), ("Lucas", 24), ("João", 21),
    ("Atos", 28), ("Romanos", 16), ("1 Coríntios", 16), ("2 Coríntios", 13),
    ("Gálatas", 6), ("Efésios", 6), ("Filipenses", 4), ("Colossenses", 4),
    ("1 Tessalonicenses", 5), ("2 Tessalonicenses", 3), ("1 Timóteo", 6),
    ("2 Timóteo", 4), ("Tito", 3), ("Filemom", 1), ("Hebreus", 13),
    ("Tiago", 5), ("1 Pedro", 5), ("2 Pedro", 3), ("1 João", 5),
    ("2 João", 1), ("3 João", 1), ("Judas", 1), ("Apocalipse", 22),
]

DIAS_NO_ANO = 365


def gerar_plano():
    total_capitulos = sum(qtd for _, qtd in LIVROS)
    capitulos_por_dia = total_capitulos / DIAS_NO_ANO

    fila = []
    for nome, qtd in LIVROS:
        for cap in range(1, qtd + 1):
            fila.append((nome, cap))

    plano = []
    alvo_acumulado = 0.0
    indice = 0
    for dia in range(1, DIAS_NO_ANO + 1):
        alvo_acumulado += capitulos_por_dia
        limite = round(alvo_acumulado) if dia < DIAS_NO_ANO else len(fila)
        leituras_do_dia = fila[indice:limite]
        indice = limite

        agrupado = {}
        ordem = []
        for nome, cap in leituras_do_dia:
            if nome not in agrupado:
                agrupado[nome] = []
                ordem.append(nome)
            agrupado[nome].append(cap)

        plano.append({
            "dia": dia,
            "leituras": [
                {
                    "livro": nome,
                    "trechos": [{"capitulo": cap} for cap in agrupado[nome]],
                }
                for nome in ordem
            ],
        })

    assert indice == len(fila), "sobraram capítulos fora do plano"
    return plano


if __name__ == "__main__":
    plano = gerar_plano()
    caminho = os.path.join(os.path.dirname(__file__), "..", "data", "plano_leitura.exemplo-canonico.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=2)
    total_capitulos_gerados = sum(
        len(l["trechos"]) for dia in plano for l in dia["leituras"]
    )
    print(f"Plano gerado: {len(plano)} dias, {total_capitulos_gerados} capítulos no total.")
