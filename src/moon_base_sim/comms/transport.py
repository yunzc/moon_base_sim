"""zmq transport. The only place sockets live; payloads are pickled objects.

Sim side binds PUB (telemetry out) + PULL (commands in); autonomy side connects
SUB + PUSH. Topic filtering is done in Python (SUB subscribes to everything), so
a message is a pickled ``(topic, payload)`` tuple on the telemetry channel.
"""
from __future__ import annotations

import zmq

from .messages import Command


class SimEndpoint:
    def __init__(self, telemetry_addr: str, command_addr: str):
        self._ctx = zmq.Context.instance()
        self._pub = self._ctx.socket(zmq.PUB)
        self._pub.bind(telemetry_addr)
        self._pull = self._ctx.socket(zmq.PULL)
        self._pull.bind(command_addr)

    def publish(self, topic: str, msg) -> None:
        self._pub.send_pyobj((topic, msg))

    def poll_commands(self) -> list[Command]:
        out: list[Command] = []
        while True:
            try:
                out.append(self._pull.recv_pyobj(flags=zmq.NOBLOCK))
            except zmq.Again:
                return out

    def close(self) -> None:
        self._pub.close(0)
        self._pull.close(0)


class AutonomyEndpoint:
    def __init__(self, telemetry_addr: str, command_addr: str):
        self._ctx = zmq.Context.instance()
        self._sub = self._ctx.socket(zmq.SUB)
        self._sub.connect(telemetry_addr)
        self._sub.setsockopt(zmq.SUBSCRIBE, b"")
        self._push = self._ctx.socket(zmq.PUSH)
        self._push.connect(command_addr)

    def poll(self, timeout_ms: int = 0) -> list[tuple[str, object]]:
        """Block up to ``timeout_ms`` for traffic, then drain everything queued."""
        out: list[tuple[str, object]] = []
        if self._sub.poll(timeout_ms):
            while True:
                try:
                    out.append(self._sub.recv_pyobj(flags=zmq.NOBLOCK))
                except zmq.Again:
                    break
        return out

    def send(self, cmd: Command) -> None:
        self._push.send_pyobj(cmd)

    def close(self) -> None:
        self._sub.close(0)
        self._push.close(0)
