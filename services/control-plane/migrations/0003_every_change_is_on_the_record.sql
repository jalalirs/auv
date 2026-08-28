-- Audit. Every mutation writes exactly one row naming the actor, the subject,
-- the request that carried it, and the outcome. The table is append-only.

CREATE SCHEMA audit;

CREATE TYPE audit.outcome AS ENUM ('succeeded', 'failed');

CREATE TABLE audit.event (
    id            text PRIMARY KEY,
    occurred_at   timestamptz NOT NULL DEFAULT now(),
    actor_id      text REFERENCES identity.principal (id),
    action        text NOT NULL,
    subject_kind  text NOT NULL,
    subject_id    text,
    outcome       audit.outcome NOT NULL,
    request_id    text NOT NULL,
    detail        jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX audit_event_by_actor ON audit.event (actor_id, occurred_at DESC);
CREATE INDEX audit_event_by_subject ON audit.event (subject_kind, subject_id, occurred_at DESC);
CREATE INDEX audit_event_by_request ON audit.event (request_id);

CREATE FUNCTION audit.reject_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'the audit record is append-only: % on audit.event is refused', TG_OP;
END;
$$;

CREATE TRIGGER the_audit_record_is_append_only
    BEFORE UPDATE OR DELETE ON audit.event
    FOR EACH ROW EXECUTE FUNCTION audit.reject_rewrite();
