// Vercel Serverless Function (Node.js).
// Chamada pelo site logo depois do cadastro, para disparar o email de
// confirmação na hora, em vez de esperar o envio diário do GitHub Actions.
//
// Variáveis de ambiente necessárias (Vercel > Project Settings >
// Environment Variables), com os MESMOS valores já usados nos Secrets
// do GitHub:
//   BREVO_API_KEY, BREVO_SENDER_EMAIL, SUPABASE_URL, SUPABASE_SERVICE_KEY

const LIMITE_DIAS_PARA_CONFIRMAR_CADASTRO = 3;

function montarHtmlConfirmacaoCadastro(linkConfirmacao) {
  return `\
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
                removido automaticamente em ${LIMITE_DIAS_PARA_CONFIRMAR_CADASTRO}
                dias sem confirmação, e você não vai receber mais nada.
              </p>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="center">
                    <a href="${linkConfirmacao}"
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
</html>`;
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'method not allowed' });
    return;
  }

  const { email, token } = req.body || {};
  if (!email || !token) {
    res.status(400).json({ error: 'email e token são obrigatórios' });
    return;
  }

  const siteUrl = `https://${req.headers.host}`;
  const linkConfirmacao = `${siteUrl}/confirmar-inscricao.html?token=${encodeURIComponent(token)}`;

  try {
    const respostaBrevo = await fetch('https://api.brevo.com/v3/smtp/email', {
      method: 'POST',
      headers: {
        'api-key': process.env.BREVO_API_KEY,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        sender: { name: 'Porção Diária', email: process.env.BREVO_SENDER_EMAIL },
        to: [{ email }],
        subject: 'Confirme sua inscrição na Porção Diária',
        htmlContent: montarHtmlConfirmacaoCadastro(linkConfirmacao),
      }),
    });

    if (!respostaBrevo.ok) {
      const corpo = await respostaBrevo.text();
      console.error('Falha ao enviar confirmação imediata:', respostaBrevo.status, corpo);
      // Não retorna erro 5xx aqui de propósito: o envio diário ainda
      // cobre esse cadastro como reserva, então o cadastro em si não
      // deve parecer ter falhado para quem preencheu o formulário.
      res.status(200).json({ ok: false, aviso: 'envio imediato falhou, reserva diária cobre' });
      return;
    }

    // Marca como enviado, para o job diário não mandar de novo.
    await fetch(
      `${process.env.SUPABASE_URL.replace(/\/$/, '')}/rest/v1/inscritos?token=eq.${encodeURIComponent(token)}`,
      {
        method: 'PATCH',
        headers: {
          apikey: process.env.SUPABASE_SERVICE_KEY,
          Authorization: `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
          'Content-Type': 'application/json',
          Prefer: 'return=minimal',
        },
        body: JSON.stringify({ confirmacao_enviada_em: new Date().toISOString() }),
      }
    );

    res.status(200).json({ ok: true });
  } catch (erro) {
    console.error('Erro inesperado ao enviar confirmação imediata:', erro);
    // Mesmo raciocínio: não propaga erro pro cadastro, a reserva diária cobre.
    res.status(200).json({ ok: false, aviso: 'erro inesperado, reserva diária cobre' });
  }
}
