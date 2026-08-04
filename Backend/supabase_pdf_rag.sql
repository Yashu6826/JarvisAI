-- Run this once in the Supabase SQL editor before using PDF Q&A.
create extension if not exists vector;
create extension if not exists pgcrypto;

create table if not exists public.pdf_documents (
  id uuid primary key default gen_random_uuid(),
  user_id text,
  session_id text not null,
  filename text not null,
  file_sha256 text not null,
  page_count integer not null check (page_count between 1 and 30),
  embedding_model text not null default 'nvidia/nemotron-3-embed-1b:free',
  created_at timestamptz not null default now()
);

create table if not exists public.pdf_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.pdf_documents(id) on delete cascade,
  user_id text,
  session_id text not null,
  chunk_index integer not null,
  page_start integer not null,
  page_end integer not null,
  chunk_text text not null,
  embedding vector(2048) not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- Safe migration for an existing Nexa project. Previous one-shot uploads had
-- no user ownership and are intentionally not exposed to Doc: searches.
alter table public.pdf_documents add column if not exists user_id text;
alter table public.pdf_chunks add column if not exists user_id text;
alter table public.pdf_documents drop constraint if exists pdf_documents_page_count_check;
alter table public.pdf_documents
  add constraint pdf_documents_page_count_check check (page_count between 1 and 30);

create index if not exists pdf_chunks_document_idx
  on public.pdf_chunks(document_id, session_id);

create index if not exists pdf_documents_user_idx
  on public.pdf_documents(user_id, created_at desc);

create index if not exists pdf_chunks_user_idx
  on public.pdf_chunks(user_id, created_at desc);

-- Nemotron embeddings are 2048-dimensional. pgvector can store vector(2048),
-- but ivfflat indexes currently cap indexed vector columns at 2000 dimensions.
-- With Nexa's bounded document limits, exact filtered search is fast enough, so no
-- vector index is needed here.

create or replace function public.match_pdf_chunks(
  p_document_id uuid,
  p_session_id text,
  p_query_embedding vector(2048),
  p_match_count integer default 8
)
returns table (
  id uuid,
  document_id uuid,
  chunk_index integer,
  page_start integer,
  page_end integer,
  chunk_text text,
  metadata jsonb,
  similarity double precision
)
language sql
stable
as $$
  select
    c.id,
    c.document_id,
    c.chunk_index,
    c.page_start,
    c.page_end,
    c.chunk_text,
    c.metadata,
    1 - (c.embedding <=> p_query_embedding) as similarity
  from public.pdf_chunks c
  where c.document_id = p_document_id
    and c.session_id = p_session_id
  order by c.embedding <=> p_query_embedding
  limit least(greatest(p_match_count, 1), 20);
$$;

-- Searches only documents explicitly saved with Remember: by the signed-in user.
create or replace function public.match_saved_pdf_chunks(
  p_user_id text,
  p_query_embedding vector(2048),
  p_match_count integer default 8
)
returns table (
  id uuid,
  document_id uuid,
  filename text,
  chunk_index integer,
  page_start integer,
  page_end integer,
  chunk_text text,
  metadata jsonb,
  similarity double precision
)
language sql
stable
as $$
  select
    c.id,
    c.document_id,
    d.filename,
    c.chunk_index,
    c.page_start,
    c.page_end,
    c.chunk_text,
    c.metadata,
    1 - (c.embedding <=> p_query_embedding) as similarity
  from public.pdf_chunks c
  join public.pdf_documents d on d.id = c.document_id
  where c.user_id = p_user_id
    and d.user_id = p_user_id
  order by c.embedding <=> p_query_embedding
  limit least(greatest(p_match_count, 1), 20);
$$;

-- Make the new user_id columns and RPC visible to Supabase's REST schema cache
-- immediately after this migration runs.
notify pgrst, 'reload schema';
