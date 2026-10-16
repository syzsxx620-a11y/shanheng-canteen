"""Frozen initial platform schema; add a new revision for future changes."""
from alembic import op
import sqlalchemy as sa

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('canteens',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.UniqueConstraint('name'),
    )
    op.create_table('legacy_weight_records',
        sa.Column('id', sa.String(length=100), primary_key=True, nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
    )
    op.create_table('system_settings',
        sa.Column('key', sa.String(length=50), primary_key=True, nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
    )
    op.create_table('devices',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('canteen_id', sa.String(length=36), sa.ForeignKey('canteens.id'), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('source_type', sa.String(length=10), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('roi', sa.JSON(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('heartbeat', sa.String(length=40), nullable=True),
        sa.Column('error', sa.Text(), nullable=False),
    )
    op.create_table('users',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('username', sa.String(length=40), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('canteen_id', sa.String(length=36), sa.ForeignKey('canteens.id'), nullable=True),
        sa.Column('created_at', sa.String(length=40), nullable=False),
        sa.UniqueConstraint('username'),
    )
    op.create_table('windows',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('canteen_id', sa.String(length=36), sa.ForeignKey('canteens.id'), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
    )
    op.create_table('audit_logs',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('target', sa.String(length=100), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False),
    )
    op.create_table('auth_sessions',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('refresh_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.String(length=40), nullable=False),
        sa.Column('revoked', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('refresh_hash'),
    )
    op.create_table('detection_jobs',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('canteen_id', sa.String(length=36), sa.ForeignKey('canteens.id'), nullable=False),
        sa.Column('device_id', sa.String(length=36), sa.ForeignKey('devices.id'), nullable=True),
        sa.Column('mode', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('image_path', sa.Text(), nullable=True),
        sa.Column('roi', sa.JSON(), nullable=True),
        sa.Column('result_event_id', sa.String(length=36), nullable=True),
        sa.Column('error', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False),
    )
    op.create_table('dishes',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('window_id', sa.String(length=36), sa.ForeignKey('windows.id'), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('category', sa.String(length=20), nullable=False),
        sa.Column('price', sa.Float(), nullable=False),
        sa.Column('portion_g', sa.Float(), nullable=False),
        sa.Column('kcal', sa.Float(), nullable=False),
        sa.Column('protein', sa.Float(), nullable=False),
        sa.Column('fat', sa.Float(), nullable=False),
        sa.Column('carbs', sa.Float(), nullable=False),
        sa.Column('ingredients', sa.JSON(), nullable=False),
        sa.Column('allergens', sa.JSON(), nullable=True),
        sa.Column('nutrition_source', sa.String(length=200), nullable=False),
        sa.Column('image_url', sa.String(length=300), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('is_demo', sa.Boolean(), nullable=False),
    )
    op.create_table('meal_records',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('date', sa.String(length=10), nullable=False),
        sa.Column('meal', sa.String(length=10), nullable=False),
        sa.Column('items', sa.JSON(), nullable=False),
        sa.Column('nutrients', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False),
    )
    op.create_table('notifications',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(length=100), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('read', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False),
    )
    op.create_table('profiles',
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), primary_key=True, nullable=False),
        sa.Column('data', sa.JSON(), nullable=False),
    )
    op.create_table('recommendations',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('date', sa.String(length=10), nullable=False),
        sa.Column('meal', sa.String(length=10), nullable=False),
        sa.Column('result', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False),
    )
    op.create_table('waste_events',
        sa.Column('id', sa.String(length=100), primary_key=True, nullable=False),
        sa.Column('canteen_id', sa.String(length=36), sa.ForeignKey('canteens.id'), nullable=False),
        sa.Column('device_id', sa.String(length=36), sa.ForeignKey('devices.id'), nullable=True),
        sa.Column('mode', sa.String(length=10), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('model_version', sa.String(length=200), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('area_ratio', sa.Float(), nullable=True),
        sa.Column('grade', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('detections', sa.JSON(), nullable=False),
        sa.Column('reminder', sa.Text(), nullable=False),
        sa.Column('snapshot', sa.Text(), nullable=True),
        sa.Column('review_history', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False),
    )
    op.create_table('favorites',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('dish_id', sa.String(length=36), sa.ForeignKey('dishes.id'), nullable=False),
        sa.UniqueConstraint('user_id', 'dish_id'),
    )
    op.create_table('feedback',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('recommendation_id', sa.String(length=36), sa.ForeignKey('recommendations.id'), nullable=True),
        sa.Column('canteen_id', sa.String(length=36), sa.ForeignKey('canteens.id'), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('reply', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(length=40), nullable=False),
    )
    op.create_table('menu_entries',
        sa.Column('id', sa.String(length=36), primary_key=True, nullable=False),
        sa.Column('date', sa.String(length=10), nullable=False),
        sa.Column('meal', sa.String(length=10), nullable=False),
        sa.Column('dish_id', sa.String(length=36), sa.ForeignKey('dishes.id'), nullable=False),
        sa.Column('available', sa.Boolean(), nullable=False),
        sa.UniqueConstraint('date', 'meal', 'dish_id'),
    )

def downgrade():
    op.drop_table('menu_entries')
    op.drop_table('feedback')
    op.drop_table('favorites')
    op.drop_table('waste_events')
    op.drop_table('recommendations')
    op.drop_table('profiles')
    op.drop_table('notifications')
    op.drop_table('meal_records')
    op.drop_table('dishes')
    op.drop_table('detection_jobs')
    op.drop_table('auth_sessions')
    op.drop_table('audit_logs')
    op.drop_table('windows')
    op.drop_table('users')
    op.drop_table('devices')
    op.drop_table('system_settings')
    op.drop_table('legacy_weight_records')
    op.drop_table('canteens')
