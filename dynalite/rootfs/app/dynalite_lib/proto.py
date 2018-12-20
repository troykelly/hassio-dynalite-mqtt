"""Async IO."""

import asyncio
from functools import reduce
import logging

LOG = logging.getLogger(__name__)

class Connection(asyncio.Protocol):
    """asyncio Protocol with line parsing and queuing writes"""

    # pylint: disable=too-many-instance-attributes
    def __init__(self, loop, connected, disconnected, got_data):
        self.loop = loop
        self._connected_callback = connected
        self._disconnected_callback = disconnected
        self._got_data_callback = got_data

        self._transport = None
        self._waiting_for_response = None
        self._timeout_task = None
        self._queued_writes = []
        self._buffer = bytearray()
        self._paused = False

    def connection_made(self, transport):
        LOG.debug("connected callback")
        self._transport = transport
        self._connected_callback(transport, self)

    def connection_lost(self, exc):
        LOG.debug("disconnected callback")
        self._transport = None
        self._cleanup()
        self._disconnected_callback()

    def _cleanup(self):
        self._cancel_timer()
        self._waiting_for_response = None
        self._queued_writes = []
        self._buffer = bytearray()

    def pause(self):
        """Pause the connection from sending/receiving."""
        self._cleanup()
        self._paused = True

    def resume(self):
        """Restart the connection from sending/receiving."""
        self._paused = False

    def _cancel_timer(self):
        if self._timeout_task:
            self._timeout_task.cancel()
            self._timeout_task = None

    def data_received(self, data):
        self._buffer += data
        while len(self._buffer) > 7:
            line = self._buffer[:8]
            if len(self._buffer[8:]) > 7:
                self._buffer = self._buffer[8:]
            else:
                self._buffer = bytearray()
            self._got_data_callback(line)
        self._process_write_queue()

    def _process_write_queue(self):
        while self._queued_writes and not self._waiting_for_response:
            to_write = self._queued_writes.pop(0)
            self.write_data(to_write[0], to_write[1], timeout=to_write[2])

    def write_data(self, data, timeout=5.0):
        """Write data on the asyncio Protocol"""
        if self._transport is None:
            return

        if self._paused:
            return

        LOG.debug("write_data '%s'", data)
        self._transport.write(data)
