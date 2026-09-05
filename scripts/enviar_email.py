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
BIBLIA_URL = "https://raw.githubusercontent.com/thiagobodruk/biblia/master/json/nvi.json"

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANO_PATH = os.path.join(RAIZ, "data", "plano_leitura.json")

SITE_URL = "https://scripts-woad-seven.vercel.app"  # ex: https://site-leitura.vercel.app, sem barra no final

LIMITE_DIAS_PENDENTES_PARA_SUSPENDER = 6
LIMITE_DIAS_PARA_CONFIRMAR_CADASTRO = 3

MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def formatar_data_pt(data: datetime.date) -> str:
    return f"{data.day} de {MESES_PT[data.month - 1]} de {data.year}"


def formatar_data_barra(data: datetime.date) -> str:
    return data.strftime("%d/%m/%Y")


FUSO_HORARIO = datetime.timezone(datetime.timedelta(hours=-3))  # America/Fortaleza, sem horário de verão


def dia_do_plano_para_data(data: datetime.date) -> int:
    inicio_do_ano = datetime.date(data.year, 1, 1)
    return (data - inicio_do_ano).days + 1


def dia_do_plano(hoje: datetime.date) -> int:
    return min(dia_do_plano_para_data(hoje), 365)  # dia 366 em ano bissexto repete o último dia


def data_do_dia_do_plano(dia_do_plano_num: int, ano: int) -> datetime.date:
    return datetime.date(ano, 1, 1) + datetime.timedelta(days=dia_do_plano_num - 1)


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
                f'font-size:17px;line-height:1.8;color:#2B2620;text-align:justify;">'
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
                f'font-size:15px;font-weight:600;letter-spacing:0.02em;color:#7A1F2B;text-align:center;">{titulo}</h2>'
                f'{paragrafos_versiculos}'
            )
    return "\n".join(blocos)


def montar_html_completo(referencia, corpo_html, link_cancelamento, link_confirmacao, bloco_pendencias):
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
                        letter-spacing:0.14em;text-transform:uppercase;color:#7A1F2B;text-align:center;">
                Porção de hoje
              </p>
              <h1 style="margin:0 0 30px;font-size:23px;line-height:1.3;color:#2B2620;
                         font-family:Georgia,'Times New Roman',serif;text-align:center;">
                {referencia}
              </h1>
              {corpo_html}
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:32px 0 8px;">
                <tr>
                  <td align="center">
                    <a href="{link_confirmacao}"
                       style="display:inline-block;padding:13px 26px;background-color:#7A1F2B;
                              color:#EDE4D0;text-decoration:none;font-family:Arial,Helvetica,sans-serif;
                              font-size:14px;font-weight:bold;border-radius:3px;">
                      Já li, marcar como concluída
                    </a>
                  </td>
                </tr>
              </table>
              {bloco_pendencias}
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


def montar_html_completo_suspenso(bloco_pendencias):
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
                        letter-spacing:0.14em;text-transform:uppercase;color:#7A1F2B;text-align:center;">
                Envio suspenso
              </p>
              <h1 style="margin:0 0 20px;font-size:22px;line-height:1.3;color:#2B2620;
                         font-family:Georgia,'Times New Roman',serif;text-align:center;">
                A leitura diária está pausada
              </h1>
              <p style="margin:0 0 8px;font-size:16px;line-height:1.7;color:#2B2620;">
                Você acumulou {LIMITE_DIAS_PENDENTES_PARA_SUSPENDER} dias de leitura sem
                confirmar, então os envios diários foram pausados. Confirme os dias pendentes
                abaixo (usando os links dos emails que já recebeu, se precisar de mais deles)
                para o envio voltar a partir de amanhã.
              </p>
              {bloco_pendencias}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def montar_html_confirmacao_cadastro(link_confirmacao):
    return f"""\
<html>
<body style="margin:0;padding:0;background-color:#EDE4D0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#EDE4D0;">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"
               style="max-width:600px;width:100%;background-color:#FFFDF7;border-radius:6px;">
          <tr>
            <td style="padding:40px 36px 32px;font-family:Georgia,'Times New Roman',serif;text-align:center;">
              <p style="margin:0 0 6px;font-family:Arial,Helvetica,sans-serif;font-size:12px;
                        letter-spacing:0.14em;text-transform:uppercase;color:#7A1F2B;">
                Confirmação de cadastro
              </p>
              <h1 style="margin:0 0 20px;font-size:22px;line-height:1.3;color:#2B2620;
                         font-family:Georgia,'Times New Roman',serif;">
                Confirme sua inscrição
              </h1>
              <p style="margin:0 0 28px;font-size:16px;line-height:1.7;color:#2B2620;text-align:left;">
                Alguém (esperamos que você mesmo) cadastrou este email para
                receber a leitura bíblica diária. Se foi você, confirme
                abaixo. Se não foi, ignore este email: o cadastro é
                removido automaticamente em {LIMITE_DIAS_PARA_CONFIRMAR_CADASTRO}
                dias sem confirmação, e você não vai receber mais nada.
              </p>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center">
                    <a href="{link_confirmacao}"
                       style="display:inline-block;padding:13px 26px;background-color:#7A1F2B;
                              color:#EDE4D0;text-decoration:none;font-family:Arial,Helvetica,sans-serif;
                              font-size:14px;font-weight:bold;border-radius:3px;">
                      Confirmar inscrição
                    </a>
                  </td>
                </tr>
              </table>
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


def buscar_pendentes_confirmacao_cadastro():
    """Quem se cadastrou mas ainda não confirmou, e ainda não recebeu
    o convite de confirmação (para não mandar de novo todo dia)."""
    url = (
        os.environ["SUPABASE_URL"].rstrip("/")
        + "/rest/v1/inscritos?select=email,token"
        + "&confirmado=eq.false&confirmacao_enviada_em=is.null"
    )
    req = urllib.request.Request(url, headers={
        "apikey": os.environ["SUPABASE_SERVICE_KEY"],
        "Authorization": "Bearer " + os.environ["SUPABASE_SERVICE_KEY"],
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def marcar_convite_enviado(token):
    url = os.environ["SUPABASE_URL"].rstrip("/") + f"/rest/v1/inscritos?token=eq.{token}"
    req = urllib.request.Request(
        url,
        data=json.dumps({"confirmacao_enviada_em": datetime.datetime.now(datetime.timezone.utc).isoformat()}).encode("utf-8"),
        headers={
            "apikey": os.environ["SUPABASE_SERVICE_KEY"],
            "Authorization": "Bearer " + os.environ["SUPABASE_SERVICE_KEY"],
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        method="PATCH",
    )
    with urllib.request.urlopen(req, timeout=30):
        pass


def limpar_cadastros_nao_confirmados():
    """Apaga quem nunca confirmou o cadastro depois do prazo. Evita
    tanto lixo acumulado quanto ficar reenviando convite pra sempre
    para um email que não pediu."""
    limite = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=LIMITE_DIAS_PARA_CONFIRMAR_CADASTRO)
    ).isoformat()
    url = (
        os.environ["SUPABASE_URL"].rstrip("/")
        + f"/rest/v1/inscritos?confirmado=eq.false&criado_em=lt.{limite}"
    )
    req = urllib.request.Request(
        url,
        headers={
            "apikey": os.environ["SUPABASE_SERVICE_KEY"],
            "Authorization": "Bearer " + os.environ["SUPABASE_SERVICE_KEY"],
            "Prefer": "return=minimal",
        },
        method="DELETE",
    )
    with urllib.request.urlopen(req, timeout=30):
        pass


def buscar_inscritos():
    url = (
        os.environ["SUPABASE_URL"].rstrip("/")
        + "/rest/v1/inscritos?select=email,token,criado_em&confirmado=eq.true"
    )
    req = urllib.request.Request(url, headers={
        "apikey": os.environ["SUPABASE_SERVICE_KEY"],
        "Authorization": "Bearer " + os.environ["SUPABASE_SERVICE_KEY"],
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        linhas = json.loads(resp.read().decode("utf-8"))
    return [
        {"email": linha["email"], "token": linha["token"], "criado_em": linha["criado_em"]}
        for linha in linhas
    ]


def buscar_confirmacoes():
    """Retorna {email: {dias confirmados}} para todo mundo, numa única
    consulta (mais barato que uma consulta por inscrito)."""
    url = os.environ["SUPABASE_URL"].rstrip("/") + "/rest/v1/leituras_confirmadas?select=email,dia"
    req = urllib.request.Request(url, headers={
        "apikey": os.environ["SUPABASE_SERVICE_KEY"],
        "Authorization": "Bearer " + os.environ["SUPABASE_SERVICE_KEY"],
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        linhas = json.loads(resp.read().decode("utf-8"))
    confirmacoes = {}
    for linha in linhas:
        confirmacoes.setdefault(linha["email"], set()).add(linha["dia"])
    return confirmacoes


def calcular_dias_pendentes(email, criado_em_iso, dia_atual, confirmacoes, fuso):
    data_cadastro = (
        datetime.datetime.fromisoformat(criado_em_iso.replace("Z", "+00:00"))
        .astimezone(fuso)
        .date()
    )
    dia_inicio = max(1, dia_do_plano_para_data(data_cadastro))
    dias_confirmados = confirmacoes.get(email, set())
    return [d for d in range(dia_inicio, dia_atual) if d not in dias_confirmados]


def montar_bloco_pendencias(dias_pendentes, token, ano, site_url):
    if not dias_pendentes:
        return ""

    MAX_LINKS = 5
    recentes = sorted(dias_pendentes, reverse=True)[:MAX_LINKS]
    itens_html = []
    for dia_num in recentes:
        data_str = formatar_data_barra(data_do_dia_do_plano(dia_num, ano))
        link = f"{site_url}/confirmar.html?token={token}&dia={dia_num}&data={data_str}"
        itens_html.append(
            f'<a href="{link}" style="color:#7A1F2B;text-decoration:underline;">{data_str}</a>'
        )
    lista_html = ", ".join(itens_html)

    restante = len(dias_pendentes) - len(recentes)
    nota_restante = f" e mais {restante} dia(s) anterior(es)" if restante > 0 else ""

    return f"""
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                     style="margin:24px 0 0;background-color:#F3ECDD;border-radius:4px;">
                <tr>
                  <td style="padding:16px 18px;font-family:Arial,Helvetica,sans-serif;
                             font-size:13px;line-height:1.6;color:#5B5347;">
                    Você ainda não confirmou a leitura de: {lista_html}{nota_restante}.
                    Após {LIMITE_DIAS_PENDENTES_PARA_SUSPENDER} dias pendentes acumulados,
                    o envio diário fica suspenso até você confirmar os dias em atraso.
                  </td>
                </tr>
              </table>"""


def enviar_via_brevo(destinatario, assunto, html_final):
    payload = {
        "sender": {
            "name": os.environ.get("BREVO_SENDER_NOME", "Porção Diária"),
            "email": os.environ["BREVO_SENDER_EMAIL"],
        },
        "to": [{"email": destinatario}],
        "subject": assunto,
        "htmlContent": html_final,
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
    confirmacoes = buscar_confirmacoes()
    print(f"Dia {entrada_do_dia['dia']} ({referencia}): enviando para {len(inscritos)} inscritos.")

    limpar_cadastros_nao_confirmados()

    pendentes_confirmacao = buscar_pendentes_confirmacao_cadastro()
    print(f"Convites de confirmação de cadastro a enviar: {len(pendentes_confirmacao)}.")
    for pendente in pendentes_confirmacao:
        link_confirmacao_cadastro = f"{SITE_URL}/confirmar-inscricao.html?token={pendente['token']}"
        status_convite = enviar_via_brevo(
            pendente["email"],
            "Confirme sua inscrição na Porção Diária",
            montar_html_confirmacao_cadastro(link_confirmacao_cadastro),
        )
        if status_convite is not None:
            marcar_convite_enviado(pendente["token"])

    falhas = 0
    for inscrito in inscritos:
        dias_pendentes = calcular_dias_pendentes(
            inscrito["email"], inscrito["criado_em"], entrada_do_dia["dia"], confirmacoes, FUSO_HORARIO
        )
        bloco_pendencias = montar_bloco_pendencias(dias_pendentes, inscrito["token"], hoje.year, SITE_URL)

        if len(dias_pendentes) >= LIMITE_DIAS_PENDENTES_PARA_SUSPENDER:
            assunto_final = "Leitura Bíblica: envio suspenso até confirmar dias pendentes"
            html_final = montar_html_completo_suspenso(bloco_pendencias)
        else:
            link_cancelamento = f"{SITE_URL}/cancelar.html?token={inscrito['token']}"
            link_confirmacao = (
                f"{SITE_URL}/confirmar.html?token={inscrito['token']}"
                f"&dia={entrada_do_dia['dia']}&data={formatar_data_barra(hoje)}"
            )
            assunto_final = assunto
            html_final = montar_html_completo(referencia, texto_html, link_cancelamento, link_confirmacao, bloco_pendencias)

        status = enviar_via_brevo(inscrito["email"], assunto_final, html_final)
        if status is None:
            falhas += 1

    print(f"Concluído. Falhas: {falhas}/{len(inscritos)}.")
    if inscritos and falhas == len(inscritos):
        sys.exit(1)  # todos falharam: marca o job como erro para gerar alerta


if __name__ == "__main__":
    main()
