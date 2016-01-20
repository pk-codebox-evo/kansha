"""Add data_members

Revision ID: 2ab01a3573fc
Revises: f058ce7ee0c
Create Date: 2016-01-19 12:40:19.492904

"""

import elixir
from alembic import op
import sqlalchemy as sa
from nagare.database import session

from kansha.card.models import DataCard
from kansha.card_addons.members.models import DataMember


# revision identifiers, used by Alembic.
revision = '2ab01a3573fc'
down_revision = 'f058ce7ee0c'


def upgrade():
    bind = op.get_bind()
    session.bind = bind
    elixir.metadata.bind = bind
    elixir.setup_all()
    elixir.create_all()

    members = {}

    select = sa.text('SELECT board_id, user_username, user_source FROM user_managed_boards__board_managers')
    for board_id, username, source in bind.execute(select):
        key = (username, source)
        members[key] = DataMember(board_id=board_id, user_username=username, user_source=source, role=u'manager', notify=0)

    select = sa.text('SELECT board_id, user_username, user_source, notify FROM user_boards__board_members')
    for board_id, username, source, notify in bind.execute(select):
        key = (username, source)
        if not key in members:
            members[key] = DataMember(board_id=board_id, user_username=username, user_source=source, role=u'', notify=notify)
        else:
            members[key].notify = notify

    select = sa.text('SELECT card_id, user_username, user_source FROM user_cards__card_members')
    for card_id, username, source in bind.execute(select):
        card = DataCard.get(card_id)
        member = members[(username, source)]
        member.cards.append(card)

    op.drop_table('user_cards__card_members')
    op.drop_table('user_boards__board_members')
    op.drop_table('user_managed_boards__board_managers')


def downgrade():
    bind = op.get_bind()
    session.bind = bind
    elixir.metadata.bind = bind
    elixir.setup_all()
    elixir.create_all()
    op.drop_table('members')
