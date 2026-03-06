"""
TRACE GUI Dialogs Module

Advanced dialogs for plugin configuration and execution.
"""

from tracengine.gui.dialogs.channel_binding import ChannelBindingDialog
from tracengine.gui.dialogs.plugin_runner import PluginRunnerDialog
from tracengine.gui.dialogs.processing import (
    DerivativeDialog,
    FilterDialog,
    AverageChannelsDialog,
    ResampleDialog,
)

__all__ = [
    "ChannelBindingDialog",
    "PluginRunnerDialog",
    "DerivativeDialog",
    "FilterDialog",
    "AverageChannelsDialog",
    "ResampleDialog",
]
