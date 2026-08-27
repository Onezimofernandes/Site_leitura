# -*- coding: utf-8 -*-
"""
Converte plano_bruto.txt (uma linha por dia, "Dia N <referências>") no
esquema JSON usado por scripts/enviar_email.py, validando cada
capítulo e cada intervalo de versículo contra a contagem real de
aa.json (baixado antes, na mesma pasta do projeto).

Uso:
    python scripts/converter_plano.py
Lê:   plano_bruto.txt (mesma pasta em que o comando é executado)
      aa.json          (mesma pasta)
Gera: data/plano_leitura.json
"""

import json
import re
import sys

# Nome como aparece no plano -> nome exato usado no campo "name" do
# JSON da fonte bíblica (aa.json). Sem essa tradução, o script de
# envio não encontra o livro.
MAPA_LIVROS = {
    "gênesis": "Gênesis", "êxodo": "Êxodo", "levítico": "Levítico",
    "números": "Números", "deuteronômio": "Deuteronômio", "josué": "Josué",
    "juízes": "Juízes", "rute": "Rute",
    "1samuel": "1 Samuel", "2samuel": "2 Samuel",
    "1reis": "1 Reis", "2reis": "2 Reis",
    "1crônicas": "1 Crônicas", "2crônicas": "2 Crônicas",
    "esdras": "Esdras", "neemias": "Neemias", "ester": "Ester",
    "jó": "Jó", "salmo": "Salmos", "salmos": "Salmos",
    "provérbios": "Provérbios", "eclesiastes": "Eclesiastes",
    "cantares": "Cânticos",
    "isaías": "Isaías", "jeremias": "Jeremias",
    "lamentações": "Lamentações de Jeremias",
    "ezequiel": "Ezequiel", "daniel": "Daniel", "oséias": "Oséias",
    "joel": "Joel", "amós": "Amós", "obadias": "Obadias", "jonas": "Jonas",
    "miquéias": "Miquéias", "naum": "Naum", "habacuque": "Habacuque",
    "sofonias": "Sofonias", "ageu": "Ageu", "zacarias": "Zacarias",
    "malaquias": "Malaquias",
    "mateus": "Mateus", "marcos": "Marcos", "lucas": "Lucas", "joão": "João",
    "atos": "Atos", "romanos": "Romanos",
    "1coríntios": "1 Coríntios", "2coríntios": "2 Coríntios",
    "gálatas": "Gálatas", "efésios": "Efésios", "filipenses": "Filipenses",
    "colossenses": "Colossenses",
    "1tessalonicenses": "1 Tessalonicenses", "2tessalonicenses": "2 Tessalonicenses",
    "1timóteo": "1 Timóteo", "2timóteo": "2 Timóteo",
    "tito": "Tito", "filemon": "Filemom", "hebreus": "Hebreus",
    "tiago": "Tiago", "1pedro": "1 Pedro", "2pedro": "2 Pedro",
    "1joão": "1 João", "2joão": "2 João", "3joão": "3 João",
    "judas": "Judas", "apocalipse": "Apocalipse",
}

# Lista ordenada da mais longa para a mais curta, para o casador de
# nome de livro nunca confundir "1joão" com "joão", por exemplo.
CHAVES_LIVROS = sorted(MAPA_LIVROS.keys(), key=len, reverse=True)


def normalizar(txt):
    return txt.strip().lower().replace(" ", "")


def casar_livro(token_normalizado):
    """Tenta casar o começo do token com um nome de livro conhecido.
    Retorna (nome_canonico, resto_do_token) ou None se não achar."""
    for chave in CHAVES_LIVROS:
        if token_normalizado.startswith(chave):
            resto = token_normalizado[len(chave):]
            if resto == "" or resto[0].isdigit():
                return MAPA_LIVROS[chave], resto
    return None


def parsear_chapterspec(spec):
    """
    Recebe algo como "20-22", "19:1-18", "11-12:16", "95" e devolve uma
    lista de trechos: [{"capitulo": N}] ou
    [{"capitulo": N, "versiculo_inicial": a, "versiculo_final": b}].
    """
    m = re.fullmatch(r"(\d+):(\d+)-(\d+):(\d+)", spec)
    if m:
        ca, va, cb, vb = map(int, m.groups())
        trechos = [{"capitulo": ca, "versiculo_inicial": va}]
        for c in range(ca + 1, cb):
            trechos.append({"capitulo": c})
        trechos.append({"capitulo": cb, "versiculo_inicial": 1, "versiculo_final": vb})
        return trechos

    m = re.fullmatch(r"(\d+)-(\d+):(\d+)", spec)
    if m:
        ca, cb, vb = map(int, m.groups())
        trechos = [{"capitulo": c} for c in range(ca, cb)]
        trechos.append({"capitulo": cb, "versiculo_inicial": 1, "versiculo_final": vb})
        return trechos

    m = re.fullmatch(r"(\d+):(\d+)-(\d+)", spec)
    if m:
        c, va, vb = map(int, m.groups())
        return [{"capitulo": c, "versiculo_inicial": va, "versiculo_final": vb}]

    m = re.fullmatch(r"(\d+):(\d+)", spec)
    if m:
        c, v = map(int, m.groups())
        return [{"capitulo": c, "versiculo_inicial": v, "versiculo_final": v}]

    m = re.fullmatch(r"(\d+)-(\d+)", spec)
    if m:
        a, b = map(int, m.groups())
        return [{"capitulo": c} for c in range(a, b + 1)]

    m = re.fullmatch(r"(\d+)", spec)
    if m:
        return [{"capitulo": int(m.group(1))}]

    raise ValueError(f"não entendi a especificação de capítulo: {spec!r}")


def parsear_dia(texto_do_dia, capitulos_por_livro):
    """texto_do_dia: string sem o prefixo 'Dia N', ex: '1Samuel 19:19-24; 20,21; Salmo 56, 142'"""
    tokens = re.split(r"[;,]", texto_do_dia)
    leituras = []
    livro_atual = None

    for token_bruto in tokens:
        token = token_bruto.strip()
        if not token:
            continue
        token_norm = normalizar(token)
        casado = casar_livro(token_norm)

        if casado:
            livro_atual, resto = casado
            spec = resto
        else:
            if livro_atual is None:
                raise ValueError(f"token sem livro conhecido e sem livro anterior: {token_bruto!r}")
            spec = token_norm

        if spec == "":
            # Livro citado sem número: só é válido se o livro tem um
            # único capítulo (Obadias, Filemom, 2 João, 3 João, Judas),
            # caso em que "capítulo 1" é a única leitura possível.
            if capitulos_por_livro.get(livro_atual) == 1:
                spec = "1"
            else:
                raise ValueError(f"token de livro sem capítulo: {token_bruto!r}")

        trechos_novos = parsear_chapterspec(spec)

        if leituras and leituras[-1]["livro"] == livro_atual:
            leituras[-1]["trechos"].extend(trechos_novos)
        else:
            leituras.append({"livro": livro_atual, "trechos": trechos_novos})

    return leituras


def validar(plano, biblia_json):
    capitulos_por_livro = {l["name"]: len(l["chapters"]) for l in biblia_json}
    versiculos_por_livro_cap = {
        l["name"]: [len(cap) for cap in l["chapters"]] for l in biblia_json
    }
    problemas = []
    for entrada in plano:
        for leitura in entrada["leituras"]:
            nome = leitura["livro"]
            if nome not in capitulos_por_livro:
                problemas.append(f"dia {entrada['dia']}: livro desconhecido {nome!r}")
                continue
            for trecho in leitura["trechos"]:
                cap = trecho["capitulo"]
                if cap < 1 or cap > capitulos_por_livro[nome]:
                    problemas.append(
                        f"dia {entrada['dia']}: {nome} {cap} não existe "
                        f"(livro tem {capitulos_por_livro[nome]} capítulos)"
                    )
                    continue
                total_versiculos = versiculos_por_livro_cap[nome][cap - 1]
                vi = trecho.get("versiculo_inicial")
                vf = trecho.get("versiculo_final")
                if vi is not None and (vi < 1 or vi > total_versiculos):
                    problemas.append(
                        f"dia {entrada['dia']}: {nome} {cap}:{vi} não existe "
                        f"(capítulo tem {total_versiculos} versículos)"
                    )
                if vf is not None and (vf < 1 or vf > total_versiculos):
                    problemas.append(
                        f"dia {entrada['dia']}: {nome} {cap}:{vf} não existe "
                        f"(capítulo tem {total_versiculos} versículos)"
                    )
    return problemas


def main():
    with open("plano_bruto.txt", encoding="utf-8") as f:
        linhas = [l.rstrip("\n") for l in f if l.strip()]

    with open("aa.json", encoding="utf-8-sig") as f:
        biblia_json = json.load(f)
    capitulos_por_livro = {l["name"]: len(l["chapters"]) for l in biblia_json}

    padrao_dia = re.compile(r"^Dia\s+(\d+)([a-z]?)\s+(.*)$")
    entradas_brutas = []
    for linha in linhas:
        m = padrao_dia.match(linha)
        if not m:
            print(f"AVISO: linha não reconhecida, ignorada: {linha!r}", file=sys.stderr)
            continue
        numero, sufixo, resto = m.groups()
        entradas_brutas.append((int(numero), sufixo, resto))

    # Corrige o dia duplicado do PDF original: "Dia 343 Filipenses 1-4"
    # seguido de "Dia 343b Colossenses 1-4" (essa segunda linha vinha
    # como "Dia 343" de novo no PDF, claramente um erro de digitação,
    # já que Filipenses e Colossenses são livros distintos e o plano
    # não repete referência em outro lugar). Aqui eu trato a segunda
    # ocorrência como um dia a mais, e renumero tudo dali em diante
    # em +1, para o plano fechar em 365 dias corridos em vez de 364.
    plano = []
    deslocamento = 0
    for numero_original, sufixo, resto in entradas_brutas:
        dia_final = numero_original + deslocamento
        if sufixo:
            deslocamento += 1
            dia_final = numero_original + deslocamento
        leituras = parsear_dia(resto, capitulos_por_livro)
        plano.append({"dia": dia_final, "leituras": leituras})

    problemas = validar(plano, biblia_json)
    if problemas:
        print(f"{len(problemas)} problema(s) encontrados na validação:", file=sys.stderr)
        for p in problemas:
            print(" - " + p, file=sys.stderr)
        sys.exit(1)

    dias_presentes = [e["dia"] for e in plano]
    faltando = sorted(set(range(1, 366)) - set(dias_presentes))
    if faltando:
        print(f"AVISO: dias sem leitura no plano final: {faltando}", file=sys.stderr)

    with open("data/plano_leitura.json", "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False, indent=2)

    print(f"OK: {len(plano)} dias gerados, 0 problemas de validação, "
          f"últimoo dia = {plano[-1]['dia']}.")


if __name__ == "__main__":
    main()
