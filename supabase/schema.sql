-- Execute este arquivo no SQL Editor do Supabase (Project > SQL Editor > New query).

create extension if not exists "pgcrypto";

create table if not exists inscritos (
    id uuid primary key default gen_random_uuid(),
    email text not null unique,
    confirmado boolean not null default true,
    criado_em timestamptz not null default now()
);

-- Ativa Row Level Security: por padrão, ninguém lê ou escreve nada.
alter table inscritos enable row level security;

-- Permite que qualquer pessoa (inclusive o formulário público, usando
-- a chave "anon") INSIRA um novo cadastro.
create policy "qualquer pessoa pode se inscrever"
    on inscritos
    for insert
    to anon
    with check (true);

-- Não existe política de SELECT/UPDATE/DELETE para "anon": o
-- formulário consegue gravar um email, mas não consegue listar,
-- editar ou apagar inscritos existentes. Isso é intencional.
--
-- O script de envio diário usa a "service_role key" (nunca a "anon
-- key"), que ignora RLS por definição do Supabase. Guarde a
-- service_role key só como Secret no GitHub, nunca no site.
