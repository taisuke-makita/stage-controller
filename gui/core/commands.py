from __future__ import annotations

_AXIS_TO_NO = {
    "X": "0",
    "Y": "1",
    "Z": "2",
    "0": "0",
    "1": "1",
    "2": "2",
}


def axis_no(axis: str) -> str:
    try:
        return _AXIS_TO_NO[axis.strip().upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown axis: {axis}") from exc


# ── Speed ──────────────────────────────────────────────────────────────────────

def pulse_speed_set(freq: int) -> str:
    """MS<freq>  パルス駆動周波数設定"""
    return f"MS{freq}"


def pulse_speed_query() -> str:
    """MSR  パルス駆動周波数読み出し"""
    return "MSR"


def physical_speed_set(speed: float) -> str:
    """mS<speed>  物理量駆動速度設定"""
    return f"mS{speed}"


def physical_speed_query() -> str:
    """mSR  物理量駆動速度読み出し"""
    return "mSR"


# ── Pulse-based commands (M prefix) ───────────────────────────────────────────

def move_relative(axis: str, pulses: int, speed_pps: int, *, wait: bool = False) -> str:
    """MS<speed>;M<n>R<pulses>  相対Pulse駆動
    wait=True で完了待ち (小文字r), False で即時応答 (大文字R)
    """
    cmd = "r" if wait else "R"
    return f"MS{speed_pps};M{axis_no(axis)}{cmd}{pulses}"


def move_absolute(axis: str, pulses: int, speed_pps: int, *, wait: bool = False) -> str:
    """MS<speed>;M<n>A<pulses>  絶対Pulse駆動
    wait=True で完了待ち (小文字a), False で即時応答 (大文字A)
    """
    cmd = "a" if wait else "A"
    return f"MS{speed_pps};M{axis_no(axis)}{cmd}{pulses}"


def position_query(axis: str) -> str:
    """M<n>P  Pulse位置読み取り"""
    return f"M{axis_no(axis)}P"


def home(axis: str, *, wait: bool = False) -> str:
    """M<n>I / M<n>i  ホーミング
    wait=True で完了待ち (小文字i), False で即時応答 (大文字I)
    """
    cmd = "i" if wait else "I"
    return f"M{axis_no(axis)}{cmd}"


def jog_start(axis: str, positive: bool) -> str:
    """M<n>NP / M<n>NM  連続駆動開始"""
    direction = "P" if positive else "M"
    return f"M{axis_no(axis)}N{direction}"


def jog_stop(axis: str) -> str:
    """M<n>F  連続駆動停止"""
    return f"M{axis_no(axis)}F"


# ── Physical-unit commands (m prefix) ─────────────────────────────────────────

def move_physical_relative(axis: str, distance: float, speed: float, *, wait: bool = False) -> str:
    """mS<speed>;m<n>R<dist>  相対物理量駆動
    wait=True で完了待ち (小文字r), False で即時応答 (大文字R)
    """
    cmd = "r" if wait else "R"
    return f"mS{speed};m{axis_no(axis)}{cmd}{distance}"


def move_physical_absolute(axis: str, position: float, speed: float, *, wait: bool = False) -> str:
    """mS<speed>;m<n>A<pos>  絶対物理量駆動
    wait=True で完了待ち (小文字a), False で即時応答 (大文字A)
    """
    cmd = "a" if wait else "A"
    return f"mS{speed};m{axis_no(axis)}{cmd}{position}"


def position_physical_query(axis: str) -> str:
    """m<n>P  物理位置読み取り"""
    return f"m{axis_no(axis)}P"


def home_physical(axis: str, *, wait: bool = False) -> str:
    """m<n>I / m<n>i  ホーミング（物理量モード）"""
    cmd = "i" if wait else "I"
    return f"m{axis_no(axis)}{cmd}"


def jog_start_physical(axis: str, positive: bool) -> str:
    """m<n>NP / m<n>NM  連続駆動開始（物理量モード）"""
    direction = "P" if positive else "M"
    return f"m{axis_no(axis)}N{direction}"


def jog_stop_physical(axis: str) -> str:
    """m<n>F  連続駆動停止（物理量モード）"""
    return f"m{axis_no(axis)}F"


# ── Register commands (R prefix) ──────────────────────────────────────────────

def register_save() -> str:
    """RS  全パラメータ保存（フラッシュ焼き込み）"""
    return "RS"


def register_read_all() -> str:
    """RA  全パラメータ読み出し"""
    return "RA"


def register_set(address: int, value: int | float) -> str:
    """R<adr>S<val>  指定アドレスに値設定（焼き込みなし）"""
    return f"R{address}S{value}"


def register_read(address: int) -> str:
    """R<adr>R  指定アドレスの値読み出し"""
    return f"R{address}R"
