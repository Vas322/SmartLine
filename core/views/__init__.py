"""Views package — re-exports all view functions and helpers from submodules."""
from core.services import messaging_service, schedule_mirror_service
from core.views.activities import activities
from core.views.auth import (
    activation_sent_view,
    activate_view,
    profile_view,
    signup_view,
)
from core.views.common import MEMBERS_GROUP, _percent, logger
from core.views.dashboard import dashboard
from core.views.instructions import (
    _unique_instruction_slug,
    instruction_detail,
    instruction_edit,
    instructions,
    schedule_mirror,
)
from core.views.messages import (
    _active_group_topics,
    _read_json_body,
    send_message,
    send_reply,
    telegram_messages,
)
from core.views.players import (
    delete_player,
    player_detail,
    player_edit,
    players,
    toggle_player,
)
from core.views.settings import settings_view

__all__ = [
    # common
    "MEMBERS_GROUP",
    "_percent",
    "logger",
    # dashboard
    "dashboard",
    # players
    "player_detail",
    "players",
    "player_edit",
    "toggle_player",
    "delete_player",
    # activities
    "activities",
    # messages
    "telegram_messages",
    "send_reply",
    "send_message",
    "_active_group_topics",
    "_read_json_body",
    # settings
    "settings_view",
    # instructions
    "instructions",
    "instruction_detail",
    "instruction_edit",
    "_unique_instruction_slug",
    "schedule_mirror",
    # auth
    "signup_view",
    "activate_view",
    "activation_sent_view",
    "profile_view",
]