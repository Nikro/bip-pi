"""
ZeroMQ messaging utilities for the reactive companion system.

This module provides helper functions and constants for managing communication
between the different nodes (awareness, brains, and UI) using ZeroMQ.
"""

import json
import time
import hmac
import hashlib
import os
from typing import Dict, Any, Optional, Union, Tuple
import zmq

# Default ports for the different communication channels
DEFAULT_PORTS = {
    "awareness_pub": 5556,  # Awareness node publishes events
    "brains_rep": 5557,     # Brains node responds to requests
    "ui_pub": 5558,         # UI node publishes state updates
}

# Message types
class MessageType:
    """Constants for different message types used in the system."""
    TRIGGER_EVENT = "trigger_event"
    STATE_UPDATE = "state_update"
    STT_REQUEST = "stt_request"
    TTS_REQUEST = "tts_request"
    RESPONSE = "response"
    ERROR = "error"
    AUTH_REQUEST = "auth_request"
    AUTH_RESPONSE = "auth_response"


# Authentication key (in production, load from environment or secure storage)
_AUTH_KEY = os.environ.get("REACTIVE_COMPANION_AUTH_KEY", "default_dev_key").encode()

# Consider adding a key rotation mechanism for enhanced security
_AUTH_KEY_TIMESTAMP = time.time()
_AUTH_KEY_ROTATION_INTERVAL = 86400  # 24 hours in seconds

def _get_auth_key() -> bytes:
    """
    Get the current authentication key, handling rotation if needed.
    
    Returns:
        Current authentication key as bytes
    """
    global _AUTH_KEY, _AUTH_KEY_TIMESTAMP
    
    # Check if key rotation is needed
    current_time = time.time()
    if current_time - _AUTH_KEY_TIMESTAMP > _AUTH_KEY_ROTATION_INTERVAL:
        # In a production system, this would fetch a new key
        # For now, we'll just update the timestamp
        _AUTH_KEY_TIMESTAMP = current_time
        
    return _AUTH_KEY


def _generate_signature(message_data: Dict[str, Any]) -> str:
    """
    Generate an HMAC signature for message authentication.

    Args:
        message_data: Message data to sign

    Returns:
        Hexadecimal string representation of the signature
    """
    # Create a deterministic JSON string (sorted keys)
    message_str = json.dumps(message_data, sort_keys=True)
    # Generate HMAC signature
    signature = hmac.new(_get_auth_key(), message_str.encode(), hashlib.sha256).hexdigest()
    return signature


def _verify_signature(message_data: Dict[str, Any], signature: str) -> bool:
    """
    Verify the HMAC signature of a message.

    Args:
        message_data: Message data that was signed
        signature: Signature to verify

    Returns:
        True if the signature is valid, False otherwise
    """
    expected_sig = _generate_signature(message_data)
    return hmac.compare_digest(signature, expected_sig)


def create_message(msg_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a properly formatted message.

    Args:
        msg_type: Type of the message (see MessageType class)
        payload: Data to include in the message

    Returns:
        Dict containing the formatted message with type, payload, and timestamp
    """
    message = {
        "type": msg_type,
        "payload": payload,
        "timestamp": time.time()
    }
    
    # Add authentication signature
    message["signature"] = _generate_signature({
        "type": msg_type,
        "payload": payload,
        "timestamp": message["timestamp"]
    })
    
    return message


def serialize_message(message: Dict[str, Any]) -> bytes:
    """
    Serialize a message to bytes using JSON.

    Args:
        message: Message dictionary to serialize

    Returns:
        JSON-encoded bytes representation of the message
    """
    return json.dumps(message).encode("utf-8")


def deserialize_message(message_bytes: bytes) -> Tuple[Dict[str, Any], bool]:
    """
    Deserialize a message from bytes to dictionary and verify its signature.

    Args:
        message_bytes: Serialized message

    Returns:
        Tuple containing (deserialized message as a dictionary, is_authentic)
    """
    try:
        message = json.loads(message_bytes.decode("utf-8"))
        
        # Extract and verify signature
        signature = message.pop("signature", "")
        is_authentic = _verify_signature({
            "type": message.get("type"),
            "payload": message.get("payload", {}),
            "timestamp": message.get("timestamp")
        }, signature)
        
        return message, is_authentic
    except json.JSONDecodeError:
        # Return an error message if JSON parsing fails
        return {
            "type": MessageType.ERROR,
            "payload": {"message": "Invalid message format"},
            "timestamp": time.time()
        }, False


class PublisherBase:
    """Base class for ZeroMQ publishers."""

    def __init__(self, port: int):
        """
        Initialize a ZeroMQ publisher.

        Args:
            port: Port number to bind to
        """
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind(f"tcp://*:{port}")
    
    def publish(self, msg_type: str, payload: Dict[str, Any]) -> None:
        """
        Create and publish a message.

        Args:
            msg_type: Type of the message
            payload: Data to include in the message
        """
        message = create_message(msg_type, payload)
        self.socket.send(serialize_message(message))


class SubscriberBase:
    """Base class for ZeroMQ subscribers."""

    def __init__(self, host: str, port: int, topics: Optional[list] = None, 
                 verify_signatures: bool = True):
        """
        Initialize a ZeroMQ subscriber.

        Args:
            host: Host to connect to
            port: Port to connect to
            topics: List of topics to subscribe to (None = all)
            verify_signatures: Whether to verify message signatures
        """
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(f"tcp://{host}:{port}")
        self.verify_signatures = verify_signatures
        
        if topics:
            for topic in topics:
                self.socket.setsockopt_string(zmq.SUBSCRIBE, topic)
        else:
            # Subscribe to all messages
            self.socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    def receive(self, timeout: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Receive a message, with optional timeout.

        Args:
            timeout: Timeout in milliseconds, None for blocking

        Returns:
            Deserialized message or None if timed out or authentication failed
        """
        if timeout is not None:
            poller = zmq.Poller()
            poller.register(self.socket, zmq.POLLIN)
            if poller.poll(timeout):
                message_bytes = self.socket.recv()
                message, is_authentic = deserialize_message(message_bytes)
                
                if self.verify_signatures and not is_authentic:
                    # Silently drop messages that fail signature verification
                    return None
                return message
            return None
        else:
            message_bytes = self.socket.recv()
            message, is_authentic = deserialize_message(message_bytes)
            
            if self.verify_signatures and not is_authentic:
                # Silently drop messages that fail signature verification
                return None
            return message


class RequestorBase:
    """Base class for ZeroMQ requesters."""

    def __init__(self, host: str, port: int):
        """
        Initialize a ZeroMQ requester.

        Args:
            host: Host to connect to
            port: Port to connect to
        """
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(f"tcp://{host}:{port}")
    
    def request(self, msg_type: str, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Send a request and wait for response.

        Args:
            msg_type: Type of the message
            payload: Data to include in the message
            timeout: Timeout in milliseconds, None for blocking

        Returns:
            Deserialized response message or None if timed out or authentication failed
        """
        message = create_message(msg_type, payload)
        self.socket.send(serialize_message(message))
        
        if timeout is not None:
            poller = zmq.Poller()
            poller.register(self.socket, zmq.POLLIN)
            if poller.poll(timeout):
                response_bytes = self.socket.recv()
                response, is_authentic = deserialize_message(response_bytes)
                if not is_authentic:
                    # Return error message for failed authentication
                    return {
                        "type": MessageType.ERROR,
                        "payload": {"message": "Authentication failed"},
                        "timestamp": time.time()
                    }
                return response
            return None
        else:
            response_bytes = self.socket.recv()
            response, is_authentic = deserialize_message(response_bytes)
            if not is_authentic:
                # Return error message for failed authentication
                return {
                    "type": MessageType.ERROR,
                    "payload": {"message": "Authentication failed"},
                    "timestamp": time.time()
                }
            return response


class ResponderBase:
    """Base class for ZeroMQ responders."""

    def __init__(self, port: int, verify_signatures: bool = True):
        """
        Initialize a ZeroMQ responder.

        Args:
            port: Port to bind to
            verify_signatures: Whether to verify message signatures
        """
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REP)
        self.socket.bind(f"tcp://*:{port}")
        self.verify_signatures = verify_signatures
    
    def receive_request(self, timeout: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Receive a request message.

        Args:
            timeout: Timeout in milliseconds, None for blocking

        Returns:
            Deserialized request message or None if timed out or authentication failed
        """
        if timeout is not None:
            poller = zmq.Poller()
            poller.register(self.socket, zmq.POLLIN)
            if poller.poll(timeout):
                message_bytes = self.socket.recv()
                message, is_authentic = deserialize_message(message_bytes)
                
                if self.verify_signatures and not is_authentic:
                    # Return authentication error instead of dropping to allow response
                    return {
                        "type": MessageType.AUTH_REQUEST,
                        "payload": {"authenticated": False},
                        "timestamp": time.time()
                    }
                return message
            return None
        else:
            message_bytes = self.socket.recv()
            message, is_authentic = deserialize_message(message_bytes)
            
            if self.verify_signatures and not is_authentic:
                # Return authentication error instead of dropping to allow response
                return {
                    "type": MessageType.AUTH_REQUEST,
                    "payload": {"authenticated": False},
                    "timestamp": time.time()
                }
            return message
    
    def send_response(self, msg_type: str, payload: Dict[str, Any]) -> None:
        """
        Send a response to a previously received request.

        Args:
            msg_type: Type of the response message
            payload: Data to include in the message
        """
        response = create_message(msg_type, payload)
        self.socket.send(serialize_message(response))
