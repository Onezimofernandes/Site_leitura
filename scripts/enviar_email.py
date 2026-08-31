"""
Executado uma vez por dia (via GitHub Actions).

Passos:
  1. Descobre o dia do plano (1 a 365) a partir da data de hoje.
  2. Baixa o texto da versão da Bíblia escolhida (JSON público) e
     extrai só os capítulos do dia.
  3. Busca a lista de emails inscritos no Supabase.
  4. Envia o email via API da Brevo.

Variáveis de ambiente necessárias (configuradas como Secrets no
GitHub, ver README.md):
  SUPABASE_URL, SUPABASE_SERVICE_KEY
  BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NOME
"""

import os
import sys
import json
import datetime
import urllib.request
import urllib.error

# --- Configuração da fonte bíblica -----------------------------------
# JSON público, um arquivo por versão, mantido em thiagobodruk/biblia.
# "aa" = Almeida Revisada Imprensa Bíblica, a mais antiga das três
# disponíveis nesse repositório e a mais próxima da tradução original
# de Almeida. Ainda assim, LEIA a nota de licença no README antes de
# usar em produção: o próprio repositório declara direitos reservados
# aos detentores de cada tradução, então isso serve para uso não
# comercial como este projeto, mas não é du domínio público
# incontestável. Troque a URL abaixo se optar por outra versão/fonte.
BIBLIA_URL = "https://raw.githubusercontent.com/thiagobodruk/biblia/master/json/aa.json"

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANO_PATH = os.path.join(RAIZ, "data", "plano_leitura.json")

SITE_URL = "https://scripts-woad-seven.vercel.app/"  # ex: https://site-leitura.vercel.app, sem barra no final

MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def formatar_data_pt(data: datetime.date) -> str:
    return f"{data.day} de {MESES_PT[data.month - 1]} de {data.year}"


FUSO_HORARIO = datetime.timezone(datetime.timedelta(hours=-3))  # America/Fortaleza, sem horário de verão


def dia_do_plano(hoje: datetime.date) -> int:
    inicio_do_ano = datetime.date(hoje.year, 1, 1)
    dia = (hoje - inicio_do_ano).days + 1
    return min(dia, 365)  # dia 366 em ano bissexto repete o último dia


def carregar_plano():
    with open(PLANO_PATH, encoding="utf-8") as f:
        return json.load(f)


def baixar_biblia():
    with urllib.request.urlopen(BIBLIA_URL, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8-sig"))


def indexar_por_livro(biblia_json):
    return {livro["name"]: livro["chapters"] for livro in biblia_json}


def montar_texto_do_dia(entrada_do_dia, indice_livros):
    """
    Cada item de "leituras" tem um "livro" e uma lista de "trechos".
    Cada trecho é {"capitulo": N} para o capítulo inteiro, ou
    {"capitulo": N, "versiculo_inicial": a, "versiculo_final": b}
    para só uma parte do capítulo (limites inclusivos, versículo 1
    é o primeiro).
    """
    blocos = []
    for leitura in entrada_do_dia["leituras"]:
        nome_livro = leitura["livro"]
        capitulos_biblia = indice_livros.get(nome_livro)
        if capitulos_biblia is None:
            blocos.append(
                f'<p style="margin:0 0 16px;font-style:italic;color:#8a4a4a;">'
                f"Não encontrei '{nome_livro}' na fonte bíblica configurada.</p>"
            )
            continue
        for trecho in leitura["trechos"]:
            num_cap = trecho["capitulo"]
            versiculos_do_capitulo = capitulos_biblia[num_cap - 1]

            inicio = trecho.get("versiculo_inicial", 1)
            fim = trecho.get("versiculo_final", len(versiculos_do_capitulo))

            fatia = versiculos_do_capitulo[inicio - 1: fim]
            paragrafos_versiculos = "\n".join(
                f'<p style="margin:0 0 14px;font-family:Georgia,\'Times New Roman\',serif;'
                f'font-size:17px;line-height:1.8;color:#2B2620;">'
                f'<sup style="font-size:11px;line-height:0;color:#9c8f7a;'
                f'margin-right:5px;">{inicio + i}</sup>{v}</p>'
                for i, v in enumerate(fatia)
            )

            if inicio == 1 and fim == len(versiculos_do_capitulo):
                titulo = f"{nome_livro} {num_cap}"
            else:
                titulo = f"{nome_livro} {num_cap}:{inicio}-{fim}"

            blocos.append(
                f'<h2 style="margin:28px 0 10px;font-family:Georgia,\'Times New Roman\',serif;'
                f'font-size:15px;font-weight:600;letter-spacing:0.02em;color:#7A1F2B;">{titulo}</h2>'
                f'{paragrafos_versiculos}'
            )
    return "\n".join(blocos)


def montar_html_completo(referencia, corpo_html, link_cancelamento):
    return f"""\
<html>
<body style="margin:0;padding:0;background-color:#EDE4D0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#EDE4D0;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;background-color:#FFFDF7;border-radius:6px;">
          <tr>
            <td style="padding:40px 36px 32px;font-family:Georgia,'Times New Roman',serif;">
              <p style="margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;font-size:12px;
                        letter-spacing:0.14em;text-transform:uppercase;color:#7A1F2B;">
                Porção de hoje
              </p>
              <h1 style="margin:0 0 30px;font-size:23px;line-height:1.3;color:#2B2620;
                         font-family:Georgia,'Times New Roman',serif;">
                {referencia}
              </h1>
              {corpo_html}
              <p style="margin:40px 0 0;padding-top:20px;border-top:1px solid rgba(43,38,32,0.15);
                        font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.6;color:#5B5347;">
                Você recebe este email porque se inscreveu para receber a leitura diária.
                <a href="{link_cancelamento}" style="color:#5B5347;">Clique aqui para cancelar a inscrição.</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def referencia_curta(entrada_do_dia):
    partes = []
    for leitura in entrada_do_dia["leituras"]:
        refs_do_livro = []
        for trecho in leitura["trechos"]:
            num_cap = trecho["capitulo"]
            if "versiculo_inicial" in trecho or "versiculo_final" in trecho:
                inicio = trecho.get("versiculo_inicial", 1)
                fim = trecho.get("versiculo_final", "fim")
                refs_do_livro.append(f"{num_cap}:{inicio}-{fim}")
            else:
                refs_do_livro.append(str(num_cap))
        partes.append(f"{leitura['livro']} {', '.join(refs_do_livro)}")
    return "; ".join(partes)


def buscar_inscritos():
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/inscritos?select=email,token&confirmado=eq.true"
    req = urllib.request.Request(url, headers={
        "apikey": os.environ["SUPABASE_SERVICE_KEY"],
        "Authorization": "Bearer " + os.environ["SUPABASE_SERVICE_KEY"],
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        linhas = json.loads(resp.read().decode("utf-8"))
    return [{"email": linha["email"], "token": linha["token"]} for linha in linhas]


def enviar_via_brevo(destinatario, assunto, referencia, corpo_html, link_cancelamento):
    payload = {
        "sender": {
            "name": os.environ.get("BREVO_SENDER_NOME", "Porção Diária"),
            "email": os.environ["BREVO_SENDER_EMAIL"],
        },
        "to": [{"email": destinatario}],
        "subject": assunto,
        "htmlContent": montar_html_completo(referencia, corpo_html, link_cancelamento),
    }
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "api-key": os.environ["BREVO_API_KEY"],
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        corpo = e.read().decode("utf-8", errors="replace")
        print(f"Falha ao enviar para {destinatario}: {e.code} {corpo}", file=sys.stderr)
        return None


def main():
    hoje = datetime.datetime.now(FUSO_HORARIO).date()
    plano = carregar_plano()
    entrada_do_dia = plano[dia_do_plano(hoje) - 1]

    biblia_json = baixar_biblia()
    indice_livros = indexar_por_livro(biblia_json)

    texto_html = montar_texto_do_dia(entrada_do_dia, indice_livros)
    referencia = referencia_curta(entrada_do_dia)
    assunto = f"Leitura Bíblica, {formatar_data_pt(hoje)}"

    inscritos = buscar_inscritos()
    print(f"Dia {entrada_do_dia['dia']} ({referencia}): enviando para {len(inscritos)} inscritos.")

    falhas = 0
    for inscrito in inscritos:
        link_cancelamento = f"{SITE_URL}/cancelar.html?token={inscrito['token']}"
        status = enviar_via_brevo(inscrito["email"], assunto, referencia, texto_html, link_cancelamento)
        if status is None:
            falhas += 1

    print(f"Concluído. Falhas: {falhas}/{len(inscritos)}.")
    if inscritos and falhas == len(inscritos):
        sys.exit(1)  # todos falharam: marca o job como erro para gerar alerta


if __name__ == "__main__":
    main()
