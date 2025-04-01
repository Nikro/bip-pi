"""
Common utilities and modules for the reactive companion system.

This package contains shared functionality used across the different nodes.
"""

from .utils import setup_logger, TimedTask, safe_execute, load_config
from .messaging import (
    MessageType, create_message, serialize_message, deserialize_message,
    PublisherBase, SubscriberBase, RequestorBase, ResponderBase, DEFAULT_PORTS
)

__all__ = [
    'setup_logger', 'TimedTask', 'safe_execute', 'load_config',
    'MessageType', 'create_message', 'serialize_message', 'deserialize_message',
    'PublisherBase', 'SubscriberBase', 'RequestorBase', 'ResponderBase',
    'DEFAULT_PORTS'
]
