# Porção Diária

Site sem fins lucrativos para cadastro de email e envio diário automático
da porção do dia de um plano de leitura da Bíblia em 365 dias.

## O plano de leitura

O plano em uso é o cronológico que você forneceu (`plano_bruto.txt`,
convertido para `data/plano_leitura.json` por
`scripts/converter_plano.py`). Dois pontos que precisam do seu aval,
já resolvidos com a decisão mais conservadora possível, mas reversível
se você discordar:

1. **Dia duplicado no PDF original:** o documento tinha duas entradas
   "Dia 343", uma para Filipenses 1-4 e outra para Colossenses 1-4
   (a segunda claramente deveria ser "Dia 344"). Tratei isso como um
   dia a mais e renumerei tudo a partir dali em +1, para o plano
   fechar em 365 dias (o PDF original ia só até o dia 364). Se a
   intenção original era outra (por exemplo, ler os dois livros no
   mesmo dia 343 e manter só 364 dias de plano), me avise que eu
   ajusto o conversor.
2. **Bug que corrigi durante a integração:** o JSON da fonte bíblica
   (`aa.json`) usa a chave `"name"` para o nome do livro, não
   `"book"` como eu tinha escrito antes em `enviar_email.py`. Sem essa
   correção, todo dia teria dado erro de "livro não encontrado". Já
   corrigido.

O plano gerado foi validado automaticamente: todo capítulo e todo
intervalo de versículo foi conferido contra a contagem real de
capítulos/versículos do `aa.json` (zero problemas encontrados) e
depois eu conferi manualmente, contra uma retranscrição independente
do PDF, que a passagem do texto do documento para `plano_bruto.txt`
não introduziu nenhum erro de digitação.

Esquema de `data/plano_leitura.json`, um item por dia:

```json
{
  "dia": 2,
  "leituras": [
    { "livro": "Gênesis", "trechos": [
        { "capitulo": 2, "versiculo_inicial": 4, "versiculo_final": 25 }
    ]},
    { "livro": "Jó", "trechos": [
        { "capitulo": 1 },
        { "capitulo": 2, "versiculo_inicial": 1, "versiculo_final": 10 }
    ]}
  ]
}
```

Regras:

- `"capitulo"` é sempre obrigatório dentro de cada trecho.
- `"versiculo_inicial"` e `"versiculo_final"` são opcionais; quando
  ausentes, o script lê o capítulo inteiro.
- O nome em `"livro"` precisa bater exatamente com o campo `"name"` do
  JSON da fonte bíblica. O mapeamento entre a abreviação do plano
  ("1Samuel", "2Reis" etc.) e o nome exato já está em
  `scripts/converter_plano.py`, na constante `MAPA_LIVROS`.

Se no futuro você quiser ajustar algum dia do plano, edite
`plano_bruto.txt` (mesmo formato do PDF: "Dia N referência") e rode
de novo:

```bash
python scripts/converter_plano.py
```

Isso regenera `data/plano_leitura.json` já validado contra a fonte
bíblica; qualquer capítulo ou versículo inexistente interrompe a
geração com a lista exata dos problemas, em vez de gerar um arquivo
quebrado silenciosamente.

Um exemplo mínimo, ilustrando o formato para um dia com capítulo
inteiro e um dia misto, está em `data/plano_leitura.exemplo-formato.json`.
Um plano alternativo em ordem canônica simples (não cronológica),
gerado por `scripts/gerar_plano.py`, está em
`data/plano_leitura.exemplo-canonico.json`: existe só como referência
de formato e não é o plano usado em produção.

## O que já vem pronto

- `site/index.html`: página de cadastro, sem framework, pronta para
  hospedar em qualquer serviço de site estático.
- `supabase/schema.sql`: tabela `inscritos` com as políticas de
  segurança já configuradas.
- `scripts/enviar_email.py`: script que roda uma vez por dia, busca a
  porção do dia, os inscritos e dispara os emails.
- `.github/workflows/`: os dois agendamentos (envio diário e
  manutenção do repositório).

## Nota sobre a fonte do texto bíblico (leia antes de publicar)

O script busca o texto em `https://raw.githubusercontent.com/thiagobodruk/biblia`,
que disponibiliza três versões em português (NVI, ACF, AA) em JSON. O
próprio repositório declara que as traduções têm direitos reservados
aos detentores de cada uma (Sociedade Bíblica Internacional, Sociedade
Bíblica Trinitariana e Imprensa Bíblica Brasileira), e distribui o
repositório sob licença Creative Commons BY-NC, ou seja, uso não
comercial com atribuição. Isso é compatível com um projeto sem fins
lucrativos como o seu, mas não é o mesmo que domínio público
incontestável. Antes de divulgar o site publicamente, duas
recomendações:

1. Mantenha uma nota de atribuição visível (ex.: no rodapé do site e
   no rodapé do email) citando a versão usada e a fonte.
2. Se quiser eliminar qualquer ambiguidade, escreva para a sociedade
   bíblica responsável pela versão escolhida pedindo autorização
   explícita para este uso; é comum esse tipo de pedido ser aprovado
   sem custo para fins devocionais não comerciais.

## Passo a passo

### 1. Repositório no GitHub

Crie um repositório novo (pode ser público, isso não custa nada e
mantém o GitHub Actions grátis sem limite de minutos) e suba todos os
arquivos desta pasta.

### 2. Banco de dados no Supabase

1. Crie uma conta em supabase.com e um novo projeto (plano grátis).
2. Vá em **SQL Editor > New query**, cole o conteúdo de
   `supabase/schema.sql` e rode.
3. Pegue os três valores que você vai precisar, em dois lugares
   diferentes do painel:
   - **Project Settings > Data API** (ou botão **Connect** no topo):
     a **Project URL**, no formato `https://SEUPROJETO.supabase.co`.
   - **Project Settings > API Keys**, aba **Publishable and secret API
     keys**: a **Publishable key** (chave pública, equivalente à antiga
     "anon key") e, mais abaixo na mesma aba, a **Secret key**
     (equivalente à antiga "service_role key"). Se o seu projeto ainda
     só mostra a aba "Legacy anon, service_role API keys", use a
     `anon key` e a `service_role key` de lá; funcionam do mesmo jeito.

### 3. Configurar o site

Abra `site/index.html` e troque as duas linhas:

```js
const SUPABASE_URL = "COLOQUE_A_URL_DO_SEU_PROJETO_SUPABASE";
const SUPABASE_ANON_KEY = "COLOQUE_A_ANON_KEY_DO_SEU_PROJETO_SUPABASE";
```

pelos valores do passo anterior: a **Project URL** e a **Publishable
key** (ou a `anon key`, se seu projeto ainda usa só as chaves legadas).
Nunca coloque a Secret key / service_role key aqui, é a única que
precisa ficar restrita ao servidor.

### 4. Publicar o site

Na Vercel ou na Netlify (ambas grátis para esse uso), crie um novo
projeto apontando para o seu repositório do GitHub, com a pasta `site`
como raiz de publicação. Não precisa de comando de build: é HTML puro.
Em minutos você tem uma URL pública com o formulário funcionando.

### 5. Conta de envio na Brevo

1. Crie uma conta em brevo.com (plano grátis, 300 emails/dia).
2. Verifique um remetente (**Senders, Domains & Dedicated IPs >
   Senders**): um email seu que a Brevo confirma que você controla.
3. Gere uma API key em **SMTP & API > API Keys**.

### 6. Configurar os Secrets no GitHub

No repositório, vá em **Settings > Secrets and variables > Actions >
New repository secret** e cadastre quatro secrets:

| Nome | Valor |
|---|---|
| `SUPABASE_URL` | a Project URL do Supabase (Project Settings > Data API) |
| `SUPABASE_SERVICE_KEY` | a Secret key (ou service_role key, se legada) |
| `BREVO_API_KEY` | a API key gerada na Brevo |
| `BREVO_SENDER_EMAIL` | o email verificado como remetente na Brevo |

### 7. Testar antes de confiar no cron

Vá na aba **Actions** do repositório, abra o workflow "Enviar porção
diária" e clique em **Run workflow** para disparar manualmente. Isso
roda o script exatamente como o cron faria, sem esperar até amanhã de
manhã. Confira se o email chegou e se o texto e a referência batem com
o dia do plano.

Se der erro, o log da execução (na própria aba Actions) mostra a
mensagem: geralmente é secret com nome errado, service key trocada
pela anon key, ou remetente ainda não verificado na Brevo.

### 8. Deixar rodando

Depois do teste manual funcionar, não precisa fazer mais nada: o
workflow `enviar-diario.yml` roda sozinho todo dia às 06:00
(horário de Fortaleza), e o `manter-ativo.yml` garante que o
agendamento não seja desativado por inatividade do repositório.

## Limites a observar

- **300 emails/dia** é o teto grátis da Brevo. Com ~50 inscritos você
  usa menos de 20% disso; se a lista crescer bastante, monitore.
- O script assume ano de 365 dias; em ano bissexto, o dia 29 de
  fevereiro repete a leitura do dia 365 do seu plano, a menos que você
  inclua um dia 366 explícito no JSON.
- Para trocar a versão da Bíblia usada, troque só a constante
  `BIBLIA_URL` em `scripts/enviar_email.py` por outro arquivo JSON no
  mesmo formato (`aa.json`, `acf.json` ou `nvi.json`, todos no mesmo
  repositório).
