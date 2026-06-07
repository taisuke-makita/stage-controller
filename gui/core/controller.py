from __future__ import annotations

from dataclasses import dataclass

from .commands import (
    home,
    home_physical,
    jog_start,
    jog_start_physical,
    jog_stop,
    jog_stop_physical,
    move_absolute,
    move_physical_absolute,
    move_physical_relative,
    move_relative,
    physical_speed_query,
    physical_speed_set,
    position_physical_query,
    position_query,
    pulse_speed_query,
    pulse_speed_set,
    register_read,
    register_read_all,
    register_save,
    register_set,
)
from comm.transport import StageTransport


@dataclass
class StageController:
    transport: StageTransport

    def connect(self) -> str:
        self.transport.open()
        return "connected"

    def disconnect(self) -> None:
        self.transport.close()

    def is_connected(self) -> bool:
        return self.transport.is_open()

    # ── Speed ──────────────────────────────────────────────────────────────────

    def set_pulse_speed(self, freq: int) -> str:
        """パルス駆動周波数設定 [pps]"""
        return self.transport.send_command(pulse_speed_set(freq))

    def get_pulse_speed(self) -> str:
        """パルス駆動周波数読み出し"""
        return self.transport.send_command(pulse_speed_query())

    def set_physical_speed(self, speed: float) -> str:
        """物理量駆動速度設定"""
        return self.transport.send_command(physical_speed_set(speed))

    def get_physical_speed(self) -> str:
        """物理量駆動速度読み出し"""
        return self.transport.send_command(physical_speed_query())

    # ── Pulse-based moves ──────────────────────────────────────────────────────

    def move_relative(self, axis: str, pulses: int, speed_pps: int, *, wait: bool = False) -> str:
        """相対Pulse駆動  wait=True で完了まで待機"""
        return self.transport.send_command(move_relative(axis, pulses, speed_pps, wait=wait))

    def move_absolute(self, axis: str, pulses: int, speed_pps: int, *, wait: bool = False) -> str:
        """絶対Pulse駆動  wait=True で完了まで待機"""
        return self.transport.send_command(move_absolute(axis, pulses, speed_pps, wait=wait))

    def get_position(self, axis: str) -> str:
        """Pulse位置読み取り"""
        return self.transport.send_command(position_query(axis))

    def home(self, axis: str, *, wait: bool = False) -> str:
        """ホーミング  wait=True で完了まで待機"""
        return self.transport.send_command(home(axis, wait=wait))

    def jog_start(self, axis: str, positive: bool) -> str:
        """連続駆動開始  positive=True でCW方向"""
        return self.transport.send_command(jog_start(axis, positive))

    def jog_stop(self, axis: str) -> str:
        """連続駆動停止"""
        return self.transport.send_command(jog_stop(axis))

    # ── Physical-unit moves ────────────────────────────────────────────────────

    def move_physical_relative(self, axis: str, distance: float, speed: float, *, wait: bool = False) -> str:
        """相対物理量駆動  wait=True で完了まで待機"""
        return self.transport.send_command(move_physical_relative(axis, distance, speed, wait=wait))

    def move_physical_absolute(self, axis: str, position: float, speed: float, *, wait: bool = False) -> str:
        """絶対物理量駆動  wait=True で完了まで待機"""
        return self.transport.send_command(move_physical_absolute(axis, position, speed, wait=wait))

    def get_physical_position(self, axis: str) -> str:
        """物理位置読み取り"""
        return self.transport.send_command(position_physical_query(axis))

    def home_physical(self, axis: str, *, wait: bool = False) -> str:
        """ホーミング（物理量モード）  wait=True で完了まで待機"""
        return self.transport.send_command(home_physical(axis, wait=wait))

    def jog_start_physical(self, axis: str, positive: bool) -> str:
        """連続駆動開始（物理量モード）  positive=True でCW方向"""
        return self.transport.send_command(jog_start_physical(axis, positive))

    def jog_stop_physical(self, axis: str) -> str:
        """連続駆動停止（物理量モード）"""
        return self.transport.send_command(jog_stop_physical(axis))

    # ── Register ───────────────────────────────────────────────────────────────

    def save_registers(self) -> str:
        """全パラメータ保存（フラッシュ焼き込み）"""
        return self.transport.send_command(register_save())

    def read_all_registers(self) -> str:
        """全パラメータ読み出し"""
        return self.transport.send_command(register_read_all())

    def set_register(self, address: int, value: int | float) -> str:
        """指定アドレスに値設定"""
        return self.transport.send_command(register_set(address, value))

    def get_register(self, address: int) -> str:
        """指定アドレスの値読み出し"""
        return self.transport.send_command(register_read(address))
