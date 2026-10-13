"""001 Initial Schema for LexGround Legal Production Database

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-13 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '001_initial_schema'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('password_hash', sa.String(255), nullable=False),
        sa.Column('role', sa.String(32), server_default='lawyer'),
        sa.Column('totp_secret', sa.String(64), nullable=True),
        sa.Column('totp_enabled', sa.Integer(), server_default='0'),
        sa.Column('failed_login_attempts', sa.Integer(), server_default='0'),
        sa.Column('locked_until', sa.Float(), server_default='0.0'),
        sa.Column('consent_given', sa.Integer(), server_default='0'),
        sa.Column('consent_timestamp', sa.Float(), server_default='0.0'),
        sa.Column('mask_pii_enabled', sa.Integer(), server_default='0'),
        sa.Column('retention_days', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.Float(), nullable=False)
    )
    op.create_index('idx_users_email', 'users', ['email'])

    # 2. matters
    op.create_table(
        'matters',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('client_ref', sa.String(255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False)
    )
    op.create_index('idx_matters_user_id', 'matters', ['user_id'])
    op.create_index('idx_matters_user_matter', 'matters', ['user_id', 'id'])

    # 3. documents
    op.create_table(
        'documents',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(64), nullable=False),
        sa.Column('total_pages', sa.Integer(), nullable=False),
        sa.Column('court', sa.String(255), nullable=True),
        sa.Column('date', sa.String(64), nullable=True),
        sa.Column('case_number', sa.String(128), nullable=True),
        sa.Column('parties', sa.String(255), nullable=True),
        sa.Column('judge', sa.String(255), nullable=True),
        sa.Column('statutes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(32), server_default='ready'),
        sa.Column('doc_type', sa.String(64), server_default='legal_case'),
        sa.Column('case_type', sa.String(64), server_default='general'),
        sa.Column('is_legal', sa.Integer(), server_default='1'),
        sa.Column('classification_confidence', sa.Float(), server_default='1.0'),
        sa.Column('ocr_warning', sa.Text(), nullable=True),
        sa.Column('language_warning', sa.Text(), nullable=True),
        sa.Column('user_override', sa.Integer(), server_default='0'),
        sa.Column('user_id', sa.String(64), nullable=True),
        sa.Column('matter_id', sa.String(64), nullable=True),
        sa.Column('is_encrypted', sa.Integer(), server_default='0'),
        sa.Column('storage_path', sa.String(512), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False)
    )
    op.create_index('idx_documents_user_matter', 'documents', ['user_id', 'matter_id'])
    op.create_index('idx_documents_user_id', 'documents', ['user_id'])
    op.create_index('idx_documents_created_at', 'documents', ['user_id', 'created_at'])

    # 4. chunks
    op.create_table(
        'chunks',
        sa.Column('chunk_id', sa.String(64), primary_key=True),
        sa.Column('doc_id', sa.String(64), nullable=False),
        sa.Column('page', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('ocr', sa.Integer(), server_default='0'),
        sa.Column('user_id', sa.String(64), nullable=True),
        sa.Column('matter_id', sa.String(64), nullable=True)
    )
    op.create_index('idx_chunks_doc_id', 'chunks', ['doc_id'])
    op.create_index('idx_chunks_user_matter', 'chunks', ['user_id', 'matter_id'])

    # 5. citation_registry
    op.create_table(
        'citation_registry',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('citation_text', sa.String(255), nullable=False),
        sa.Column('citation_type', sa.String(64), nullable=False),
        sa.Column('doc_id', sa.String(64), nullable=False),
        sa.Column('chunk_id', sa.String(64), nullable=False),
        sa.Column('user_id', sa.String(64), nullable=True),
        sa.Column('matter_id', sa.String(64), nullable=True)
    )
    op.create_index('idx_citation_reg_doc', 'citation_registry', ['doc_id'])
    op.create_index('idx_citation_reg_user_matter', 'citation_registry', ['user_id', 'matter_id'])

    # 6. chat_history
    op.create_table(
        'chat_history',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('session_id', sa.String(128), nullable=False),
        sa.Column('role', sa.String(32), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('user_id', sa.String(64), nullable=True),
        sa.Column('matter_id', sa.String(64), nullable=True)
    )
    op.create_index('idx_chat_session', 'chat_history', ['session_id'])
    op.create_index('idx_chat_user_matter', 'chat_history', ['user_id', 'matter_id'])

    # 7. drafts
    op.create_table(
        'drafts',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('matter_id', sa.String(64), nullable=False),
        sa.Column('doc_type', sa.String(64), nullable=False),
        sa.Column('draft_text', sa.Text(), nullable=False),
        sa.Column('groundedness_score', sa.Float(), nullable=False),
        sa.Column('created_at', sa.Float(), nullable=False)
    )
    op.create_index('idx_drafts_user_matter', 'drafts', ['user_id', 'matter_id'])

    # 8. password_resets
    op.create_table(
        'password_resets',
        sa.Column('token', sa.String(128), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False),
        sa.Column('used', sa.Integer(), server_default='0')
    )

    # 9. audit_logs
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.String(64), nullable=True),
        sa.Column('matter_id', sa.String(64), nullable=True),
        sa.Column('action', sa.String(128), nullable=False),
        sa.Column('target_type', sa.String(64), nullable=True),
        sa.Column('target_id', sa.String(128), nullable=True),
        sa.Column('ip_address', sa.String(64), nullable=True),
        sa.Column('timestamp', sa.Float(), nullable=False)
    )
    op.create_index('idx_audit_user_ts', 'audit_logs', ['user_id', 'timestamp'])

    # 10. answer_feedback
    op.create_table(
        'answer_feedback',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('matter_id', sa.String(64), nullable=True),
        sa.Column('message_id', sa.String(128), nullable=True),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('prompt_version', sa.String(64), nullable=True),
        sa.Column('model', sa.String(64), nullable=True),
        sa.Column('retrieval_params', sa.Text(), nullable=True),
        sa.Column('verified_status', sa.String(32), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False)
    )
    op.create_index('idx_feedback_user_matter', 'answer_feedback', ['user_id', 'matter_id'])

    # 11. ingestion_jobs (Phase 3 background worker queue state)
    op.create_table(
        'ingestion_jobs',
        sa.Column('job_id', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), nullable=False),
        sa.Column('matter_id', sa.String(64), nullable=True),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('status', sa.String(32), server_default='queued'),
        sa.Column('progress_pct', sa.Integer(), server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('document_id', sa.String(64), nullable=True),
        sa.Column('created_at', sa.Float(), nullable=False),
        sa.Column('updated_at', sa.Float(), nullable=False)
    )
    op.create_index('idx_jobs_user_matter', 'ingestion_jobs', ['user_id', 'matter_id'])

def downgrade():
    op.drop_table('ingestion_jobs')
    op.drop_table('answer_feedback')
    op.drop_table('audit_logs')
    op.drop_table('password_resets')
    op.drop_table('drafts')
    op.drop_table('chat_history')
    op.drop_table('citation_registry')
    op.drop_table('chunks')
    op.drop_table('documents')
    op.drop_table('matters')
    op.drop_table('users')
