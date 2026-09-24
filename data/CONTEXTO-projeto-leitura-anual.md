# Contexto técnico: Leitura Anual da Bíblia

Documento para retomar o projeto em uma nova conversa, sem precisar
reconstruir o histórico. Cole este arquivo inteiro no início de uma
conversa nova para dar o contexto completo.

## O que é o projeto

Site sem fins lucrativos: cadastro de email, envio diário automático da
porção do dia de um plano de leitura cronológica da Bíblia em 365 dias,
confirmação de leitura, e certificado de conclusão para quem completar
os 365 dias até o fim de 2027.

## Arquitetura

| Peça | Serviço | Papel |
|---|---|---|
| Repositório | GitHub — `Onezimofernandes/Site_leitura` (nome pode ter mudado, confirmar) | Todo o código |
| Site | Vercel, domínio `leituraanualdabiblia.vercel.app` — Root Directory = `site` | Formulário e páginas |
| Banco | Supabase (Postgres), URL `https://nsltgofwtuzwjmhpjsbi.supabase.co` | Inscritos e leituras confirmadas |
| Envio diário | GitHub Actions (`.github/workflows/enviar-diario.yml`) rodando `scripts/enviar_email.py` | Uma vez por dia, 06:00 Fortaleza |
| Envio de email | Brevo (API transacional) | — |
| Confirmação imediata de cadastro | Vercel Serverless Function (`site/api/enviar-confirmacao.js`) | Dispara convite na hora do cadastro |
| Texto bíblico | `github.com/thiagobodruk/biblia`, versão AA, baixado a cada envio | Nunca reproduzido de memória |

Chave pública do Supabase (segura de expor, é a "publishable key",
usada nos arquivos do site): `sb_publishable_qWK7C4yC3q6k4tIcNxE83g_UQcAZn5L`

## Estrutura de arquivos no repositório

```
site/index.html              formulário de cadastro (só email)
site/cancelar.html           cancelamento de inscrição (link no email)
site/confirmar.html          confirmação de leitura do dia (botão no email)
site/confirmar-inscricao.html  confirmação de cadastro (double opt-in), pede nome completo
site/api/enviar-confirmacao.js  função serverless da Vercel, dispara convite imediato
scripts/enviar_email.py      script diário: monta e envia os emails
scripts/converter_plano.py   converte plano_bruto.txt -> data/plano_leitura.json
scripts/gerar_plano.py       gera plano alternativo em ordem canônica (referência, não usado)
data/plano_leitura.json      plano cronológico real, em uso (365 dias)
plano_bruto.txt              plano original em texto, fonte editável
supabase/schema.sql          schema completo, para projeto novo
supabase/migracao_*.sql      incrementos separados, para projeto já em produção
.github/workflows/enviar-diario.yml   cron diário
.github/workflows/manter-ativo.yml    evita desativação por inatividade (60 dias)
```

## Schema completo do banco (estado atual, cumulativo)

```sql
create extension if not exists "pgcrypto";

create table inscritos (
    id uuid primary key default gen_random_uuid(),
    email text not null unique,
    nome_completo text,
    confirmado boolean not null default false,
    criado_em timestamptz not null default now(),
    confirmacao_enviada_em timestamptz,
    token uuid not null default gen_random_uuid() unique
);

alter table inscritos
    add constraint email_formato_valido
    check (email ~* '^[^\s@]+@[^\s@]+\.[^\s@]+$');

create unique index inscritos_email_lower_idx on inscritos (lower(email));

alter table inscritos enable row level security;

-- Só permite INSERT com confirmado=false (impede pular a dupla
-- confirmação chamando a API direto).
create policy "qualquer pessoa pode se inscrever, mas nunca já confirmada"
    on inscritos
    for insert
    to anon
    with check (confirmado = false);
-- Sem política de SELECT/UPDATE/DELETE para anon: acesso só via as
-- três funções abaixo.

create table leituras_confirmadas (
    id uuid primary key default gen_random_uuid(),
    email text not null,
    dia integer not null check (dia between 1 and 365),
    confirmado_em timestamptz not null default now(),
    unique (email, dia)
);
alter table leituras_confirmadas enable row level security;
-- Sem política nenhuma: só acessível via confirmar_leitura.

-- Cancela a inscrição (apaga a linha), a partir do token do email.
create or replace function cancelar_inscricao(token_informado uuid)
returns void
language sql
security definer
set search_path = public
as $$
  delete from inscritos where token = token_informado;
$$;
revoke all on function cancelar_inscricao(uuid) from public;
grant execute on function cancelar_inscricao(uuid) to anon;

-- Confirma o cadastro (double opt-in) e grava o nome completo.
create or replace function confirmar_cadastro(token_informado uuid, nome_completo_informado text)
returns void
language sql
security definer
set search_path = public
as $$
  update inscritos
  set confirmado = true,
      nome_completo = coalesce(nullif(trim(nome_completo_informado), ''), nome_completo)
  where token = token_informado;
$$;
revoke all on function confirmar_cadastro(uuid, text) from public;
grant execute on function confirmar_cadastro(uuid, text) to anon;

-- Marca um dia do plano como lido, a partir do token do email.
create or replace function confirmar_leitura(token_informado uuid, dia_informado integer)
returns void
language sql
security definer
set search_path = public
as $$
  insert into leituras_confirmadas (email, dia)
  select lower(email), dia_informado from inscritos where token = token_informado
  on conflict (email, dia) do nothing;
$$;
revoke all on function confirmar_leitura(uuid, integer) from public;
grant execute on function confirmar_leitura(uuid, integer) to anon;
```

Consulta para o certificado de fim de ano (quem leu os 365 dias):

```sql
select email, nome_completo, count(distinct dia) as dias_lidos
from leituras_confirmadas l
join inscritos i using (email)
group by email, nome_completo
having count(distinct dia) = 365
order by nome_completo;
```

## scripts/enviar_email.py (conteúdo completo, última versão)

```python
"""
Executado uma vez por dia (via GitHub Actions).

Passos:
  1. Descobre o dia do plano (1 a 365) a partir da data de hoje.
  2. Baixa o texto da versão da Bíblia escolhida (JSON público) e
     extrai só os capítulos do dia.
  3. Busca a lista de emails inscritos e confirmados no Supabase.
  4. Envia convites de confirmação de cadastro a quem ainda não recebeu.
  5. Envia a porção do dia (ou aviso de suspensão) via Brevo.

Variáveis de ambiente necessárias (Secrets no GitHub):
  SUPABASE_URL, SUPABASE_SERVICE_KEY
  BREVO_API_KEY, BREVO_SENDER_EMAIL, BREVO_SENDER_NOME
"""

import os
import sys
import json
import datetime
import urllib.request
import urllib.error
import urllib.parse

BIBLIA_URL = "https://raw.githubusercontent.com/thiagobodruk/biblia/master/json/aa.json"

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANO_PATH = os.path.join(RAIZ, "data", "plano_leitura.json")

SITE_URL = "https://leituraanualdabiblia.vercel.app"  # sem barra no final

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


FUSO_HORARIO = datetime.timezone(datetime.timedelta(hours=-3))  # America/Fortaleza


def dia_do_plano_para_data(data: datetime.date) -> int:
    inicio_do_ano = datetime.date(data.year, 1, 1)
    return (data - inicio_do_ano).days + 1


def dia_do_plano(hoje: datetime.date) -> int:
    return min(dia_do_plano_para_data(hoje), 365)


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
    limite = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=LIMITE_DIAS_PARA_CONFIRMAR_CADASTRO)
    ).isoformat()
    url = (
        os.environ["SUPABASE_URL"].rstrip("/")
        + f"/rest/v1/inscritos?confirmado=eq.false&criado_em=lt.{urllib.parse.quote(limite, safe='')}"
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
        sys.exit(1)


if __name__ == "__main__":
    main()
```

Nota: `SITE_URL` já está com o valor real (`https://leituraanualdabiblia.vercel.app`) nesta versão. Se o domínio mudar de novo, é só trocar essa constante.

## Placeholders que precisam de valor real (conferir se já foram preenchidos)

Em `site/index.html`, `site/cancelar.html`, `site/confirmar.html`,
`site/confirmar-inscricao.html`, dentro do `<script type="module">`:
```js
const SUPABASE_URL = "https://nsltgofwtuzwjmhpjsbi.supabase.co";
const SUPABASE_ANON_KEY = "sb_publishable_qWK7C4yC3q6k4tIcNxE83g_UQcAZn5L";
```

Secrets do GitHub (Settings > Secrets and variables > Actions):
`SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `BREVO_API_KEY`, `BREVO_SENDER_EMAIL`.

Variáveis de ambiente da Vercel (Settings > Environment Variables), usadas
por `site/api/enviar-confirmacao.js`: as mesmas quatro acima, com os
mesmos valores.

## Pendência mais importante no momento do encerramento

**Domínio do remetente de email ainda não autenticado.** O
`BREVO_SENDER_EMAIL` configurado era (até onde sei) um email pessoal,
o que causa rejeição (DMARC fail) em Hotmail, Yahoo e Proton — confirmado
por log de bounce real da Brevo. A correção é: registrar um domínio
próprio, autenticá-lo na Brevo (Domains > Add a domain, adicionar os
registros DKIM/DMARC no DNS, sem precisar de SPF próprio), cadastrar um
remetente nesse domínio, e atualizar `BREVO_SENDER_EMAIL` tanto no
Secret do GitHub quanto na variável de ambiente da Vercel. Confirmar se
isso já foi feito; se não, é a prioridade número um antes de qualquer
divulgação maior.

## Outras pendências menores

- Conferir se `SITE_URL` no script e as variáveis da Vercel já refletem
  o domínio definitivo (`leituraanualdabiblia.vercel.app`, com dois "a").
- Nomes de quem já estava cadastrado antes da coluna `nome_completo`
  existir: preencher manualmente via `UPDATE inscritos SET nome_completo
  = '...' WHERE email = '...';` para quem ainda estiver com o campo nulo
  (consulta para achar quem falta: `select email from inscritos where
  nome_completo is null;`).
- Testar envio para Gmail, Outlook e Yahoo ao mesmo tempo depois de
  trocar o domínio do remetente, para confirmar que os três recebem.

## Decisões de design que valem lembrar (evita retrabalho)

- Plano de leitura é cronológico, fornecido pelo usuário via PDF, não
  em ordem canônica. Convertido e validado por `converter_plano.py`.
- `leituras_confirmadas` é chaveada por email, não por id de cadastro,
  de propósito: sobrevive a cancelamento e reinscrição.
- Suspensão de envio após 6 dias pendentes acumulados foi implementada
  na versão simples (sem coluna extra para "congelar" a contagem durante
  a suspensão); limitação aceita, correção manual se alguém travar.
- Dupla confirmação de cadastro (double opt-in) existe para impedir
  cadastro do email de terceiros sem consentimento; cadastro nunca
  confirmado é apagado depois de 3 dias.
- Nome completo é pedido na tela de CONFIRMAÇÃO de cadastro
  (`confirmar-inscricao.html`), não na tela de cadastro inicial
  (`index.html`, que só pede email).
- Fonte bíblica (thiagobodruk/biblia, versão AA) tem licenciamento
  ambíguo (CC BY-NC do repositório, mas direitos de tradução reservados
  às sociedades bíblicas); compatível com uso não comercial, mas
  recomenda-se confirmar autorização direto com a sociedade bíblica se o
  projeto crescer.
- Identidade visual usada em site, emails e panfleto: fundo pergaminho
  `#EDE4D0`, tom mais escuro `#E2D6BC`, tinta `#2B2620`, vinho `#7A1F2B`
  (acento principal), tipografia Fraunces (títulos) + Source Serif 4
  (texto), elemento decorativo de fita/marcador de página.

## Bugs já corrigidos (não repetir)

- BOM no JSON da Bíblia: ler com `utf-8-sig`, não `utf-8`.
- Chave do nome do livro no JSON da Bíblia é `"name"`, não `"book"`.
- `+` cru em URL de filtro do Supabase quebra (interpretado como
  espaço); sempre usar `urllib.parse.quote(valor, safe='')`.
- Arquivos do GitHub Actions e da API da Vercel precisam ser criados a
  partir da RAIZ do repositório; o campo de nome de arquivo do GitHub é
  relativo à pasta atual, então criar de dentro de uma subpasta gera
  caminho errado (ex: `workflows/.github/workflows/...`).
- Vercel precisa de Root Directory = `site`; sem isso, tenta rodar como
  projeto Python por causa dos arquivos `.py` do resto do repo.
- Ao editar funções deste arquivo por partes (str_replace), sempre
  reler o arquivo inteiro depois e testar rodando de verdade (não só
  compilando), porque uma substituição mal encaixada pode deixar código
  sintaticamente válido mas semanticamente quebrado (já aconteceu de uma
  função inteira ficar "engolida" como código morto dentro de outra).

## Escala e custos (se o projeto crescer além de ~50 inscritos)

Brevo (envio de email) é o primeiro teto: 300 emails grátis/dia, o que
cobre até ~250-280 inscritos com folga. Acima disso, planos pagos a
partir de US$ 9/mês. Supabase, Vercel e GitHub Actions aguentam uma
escala bem maior antes de custar algo (na casa de milhares de
inscritos). Vercel Hobby (grátis) é oficialmente só para uso pessoal;
projetos que crescem para atender outros grupos publicamente podem
precisar do plano Pro (US$ 20/mês) por questão de termos de uso, não de
limite técnico.
