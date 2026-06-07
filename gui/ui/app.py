from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtSerialPort import QSerialPortInfo
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.controller import StageController
from core.stage_config import StageConfig
from comm.transport import MockTransport, SerialTransport, TransportError
from ui.settings_dialog import StageSettingsDialog

_AXES   = ("X", "Y", "Z")
_AXIS_NO = {"X": "0", "Y": "1", "Z": "2"}


@dataclass
class _AxisRow:
    """1軸分のウィジェット群"""
    jog_minus:   QPushButton
    jog_plus:    QPushButton
    dist_spin:   QDoubleSpinBox   # 移動量 [μm]
    abs_check:   QCheckBox
    speed_spin:  QDoubleSpinBox   # 移動速度 [μm/s]
    move_button: QPushButton
    home_button: QPushButton
    pos_label:   QLabel           # 現在位置 [μm]（自動更新）
    stop_button: QPushButton

    def all_widgets(self) -> list[QWidget]:
        # pos_label は常時表示のため enable/disable 対象から除外
        return [
            self.jog_minus, self.jog_plus,
            self.dist_spin, self.abs_check, self.speed_spin,
            self.move_button, self.home_button,
            self.stop_button,
        ]


def _make_axis_row() -> _AxisRow:
    minus = QPushButton("−")
    plus_ = QPushButton("＋")
    minus.setAutoRepeat(False)
    plus_.setAutoRepeat(False)

    dist = QDoubleSpinBox()
    dist.setRange(-100_000.0, 100_000.0)
    dist.setSingleStep(100.0)
    dist.setDecimals(2)
    dist.setValue(1_000.0)
    dist.setSuffix(" μm")

    abs_chk = QCheckBox()

    speed = QDoubleSpinBox()
    speed.setRange(1.0, 500_000.0)
    speed.setSingleStep(500.0)
    speed.setDecimals(1)
    speed.setValue(5_000.0)
    speed.setSuffix(" μm/s")

    stop = QPushButton("停止")
    stop.setObjectName("stopButton")

    pos = QLabel("—")
    pos.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pos.setObjectName("posLabel")

    return _AxisRow(
        jog_minus=minus,
        jog_plus=plus_,
        dist_spin=dist,
        abs_check=abs_chk,
        speed_spin=speed,
        move_button=QPushButton("移動"),
        home_button=QPushButton("原点"),
        pos_label=pos,
        stop_button=stop,
    )


class MainWindow(QMainWindow):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.setWindowTitle("自動ステージコントローラ")
        self.resize(1080, 580)
        self.controller:   StageController | None = None
        self._config_path: Path = config_path
        self._config:      StageConfig = StageConfig.load_or_default(config_path)

        # ── 位置ポーリング用タイマー（接続中のみ稼働） ──────────────────────────
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(300)   # 300 ms
        self._poll_timer.timeout.connect(self._poll_positions)

        # ── 通信 ──────────────────────────────────────────────────────────────
        self.port_combo        = QComboBox()
        self.mock_check        = QCheckBox("シミュレーション")
        self.mock_check.setChecked(True)
        self.connect_button    = QPushButton("接続")
        self.disconnect_button = QPushButton("切断")
        self.refresh_button    = QPushButton("更新")
        self.settings_button   = QPushButton("設定…")
        self.disconnect_button.setEnabled(False)

        # ── 各軸ウィジェット ────────────────────────────────────────────────────
        self._rows: dict[str, _AxisRow] = {ax: _make_axis_row() for ax in _AXES}

        # ── ジョグ速度（全軸共通）[μm/s] ──────────────────────────────────────
        self.jog_speed_spin = QDoubleSpinBox()
        self.jog_speed_spin.setRange(1.0, 500_000.0)
        self.jog_speed_spin.setSingleStep(500.0)
        self.jog_speed_spin.setDecimals(1)
        self.jog_speed_spin.setValue(1_000.0)
        self.jog_speed_spin.setSuffix(" μm/s")

        # ── 直接コマンド ───────────────────────────────────────────────────────
        self.command_edit = QPlainTextEdit()
        self.command_edit.setPlaceholderText("例: mS5000;m0R1000")
        self.command_edit.setMaximumHeight(68)
        self.send_button = QPushButton("送信")

        # ── ログ ──────────────────────────────────────────────────────────────
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)

        self._build_ui()
        self._connect_signals()
        self.refresh_ports()
        self._set_controls_enabled(False)

    # ── UI 構築 ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(10)
        root.addWidget(self._build_connection_box())
        root.addWidget(self._build_stage_box())
        root.addWidget(self._build_command_box())
        root.addWidget(self._build_log_box(), stretch=1)
        self.setCentralWidget(central)
        self._apply_style()

    def _build_connection_box(self) -> QGroupBox:
        box = QGroupBox("通信")
        lay = QGridLayout(box)
        lay.addWidget(QLabel("ポート"),       0, 0)
        lay.addWidget(self.port_combo,        0, 1)
        lay.addWidget(self.mock_check,        0, 2)
        lay.addWidget(self.refresh_button,    0, 3)
        lay.addWidget(self.connect_button,    0, 4)
        lay.addWidget(self.disconnect_button, 0, 5)
        lay.addWidget(self.settings_button,   0, 6)
        return box

    def _build_stage_box(self) -> QGroupBox:
        box = QGroupBox("ステージ操作")
        outer = QVBoxLayout(box)
        outer.setSpacing(8)

        jog_row = QHBoxLayout()
        jog_row.addWidget(QLabel("ジョグ速度（全軸共通）"))
        jog_row.addWidget(self.jog_speed_spin)
        jog_row.addStretch()
        outer.addLayout(jog_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        HEADERS = [
            ("軸",            0),
            ("ジョグ −",      1),
            ("ジョグ ＋",     2),
            ("移動量 [μm]",   3),
            ("絶対",          4),
            ("速度 [μm/s]",   5),
            ("移動",          6),
            ("原点",          7),
            ("位置 [μm]",     8),
            ("停止",          9),
        ]
        for text, col in HEADERS:
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, 0, col)

        for row_idx, axis in enumerate(_AXES, start=1):
            r = self._rows[axis]
            ax_lbl = QLabel(axis)
            ax_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(ax_lbl,        row_idx, 0)
            grid.addWidget(r.jog_minus,   row_idx, 1)
            grid.addWidget(r.jog_plus,    row_idx, 2)
            grid.addWidget(r.dist_spin,   row_idx, 3)
            grid.addWidget(r.abs_check,   row_idx, 4, Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(r.speed_spin,  row_idx, 5)
            grid.addWidget(r.move_button, row_idx, 6)
            grid.addWidget(r.home_button, row_idx, 7)
            grid.addWidget(r.pos_label,   row_idx, 8)
            grid.addWidget(r.stop_button, row_idx, 9)

        grid.setColumnStretch(3, 2)
        grid.setColumnStretch(5, 2)
        outer.addLayout(grid)
        return box

    def _build_command_box(self) -> QGroupBox:
        box = QGroupBox("直接コマンド")
        lay = QVBoxLayout(box)
        lay.addWidget(self.command_edit)
        lay.addWidget(self.send_button, alignment=Qt.AlignmentFlag.AlignRight)
        return box

    def _build_log_box(self) -> QGroupBox:
        box = QGroupBox("ログ")
        lay = QVBoxLayout(box)
        lay.addWidget(self.log)
        return box

    def _apply_style(self) -> None:
        self.setStyleSheet("""
            QMainWindow { background: #f5f7fb; }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d9dee8;
                border-radius: 6px;
                margin-top: 12px;
                padding: 10px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QPushButton {
                min-height: 28px;
                min-width: 56px;
                padding: 2px 6px;
            }
            QPushButton#stopButton {
                background: #b42318;
                color: white;
                font-weight: 700;
            }
            QLabel#posLabel {
                font-family: Consolas, monospace;
                font-weight: 600;
                background: #eef2f9;
                border: 1px solid #d9dee8;
                border-radius: 4px;
                padding: 4px 6px;
            }
            QPlainTextEdit {
                font-family: Consolas, monospace;
                font-size: 10pt;
            }
            QLabel {
                font-size: 9pt;
            }
        """)

    # ── シグナル接続 ──────────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self.connect_stage)
        self.disconnect_button.clicked.connect(self.disconnect_stage)
        self.settings_button.clicked.connect(self.open_settings)
        self.send_button.clicked.connect(self.send_manual_command)

        for axis, r in self._rows.items():
            r.abs_check.toggled.connect(
                lambda checked, btn=r.move_button: btn.setText("絶対移動" if checked else "移動")
            )
            r.move_button.clicked.connect(lambda _, ax=axis: self._execute_move(ax))
            r.home_button.clicked.connect(lambda _, ax=axis: self._send(lambda c: c.home(ax)))
            r.stop_button.clicked.connect(lambda _, ax=axis: self._send(lambda c: c.jog_stop(ax)))
            r.jog_minus.pressed.connect(lambda ax=axis: self._jog_start(ax, positive=False))
            r.jog_minus.released.connect(lambda ax=axis: self._jog_stop(ax))
            r.jog_plus.pressed.connect(lambda ax=axis: self._jog_start(ax, positive=True))
            r.jog_plus.released.connect(lambda ax=axis: self._jog_stop(ax))

    # ── 接続 ──────────────────────────────────────────────────────────────────

    def refresh_ports(self) -> None:
        current = self.port_combo.currentText()
        self.port_combo.clear()
        ports = [port.portName() for port in QSerialPortInfo.availablePorts()]
        self.port_combo.addItems(ports)
        if current in ports:
            self.port_combo.setCurrentText(current)
        self._log(f"検出ポート: {', '.join(ports) if ports else 'なし'}")

    def connect_stage(self) -> None:
        try:
            if self.mock_check.isChecked():
                transport = MockTransport()
            else:
                port = self.port_combo.currentText().strip()
                if not port:
                    QMessageBox.warning(self, "接続できません", "シリアルポートを選択してください。")
                    return
                transport = SerialTransport(port=port)
            self.controller = StageController(transport)
            self.controller.connect()
        except TransportError as exc:
            QMessageBox.critical(self, "通信エラー", str(exc))
            self._log(f"ERROR {exc}")
            return
        self._set_connected(True)
        self._log("接続しました")

    def disconnect_stage(self) -> None:
        if self.controller is not None:
            self.controller.disconnect()
        self.controller = None
        self._set_connected(False)
        self._log("切断しました")

    # ── 設定ダイアログ ────────────────────────────────────────────────────────

    def open_settings(self) -> None:
        dlg = StageSettingsDialog(
            config      = self._config,
            config_path = self._config_path,
            controller  = self.controller,
            parent      = self,
        )
        dlg.exec()

    # ── 移動（μm → pulse に PC 側で換算して M-prefix コマンドを送信） ──────────

    def _execute_move(self, axis: str) -> None:
        r      = self._rows[axis]
        cfg    = self._config.axes[axis]
        if cfg.um_per_pulse == 0.0:
            QMessageBox.warning(self, "設定エラー", f"軸 {axis} の μm/pulse が 0 です。設定を確認してください。")
            return
        pulses = round(r.dist_spin.value()  / cfg.um_per_pulse)
        pps    = max(1, round(r.speed_spin.value() / cfg.um_per_pulse))
        if r.abs_check.isChecked():
            self._send(lambda c, ax=axis, p=pulses, s=pps: c.move_absolute(ax, p, s))
        else:
            self._send(lambda c, ax=axis, p=pulses, s=pps: c.move_relative(ax, p, s))

    # ── ジョグ（μm/s → pps に換算して M-prefix コマンドを送信） ─────────────

    def _jog_start(self, axis: str, positive: bool) -> None:
        if self.controller is None or not self.controller.is_connected():
            return
        cfg       = self._config.axes[axis]
        pps       = max(1, round(self.jog_speed_spin.value() / cfg.um_per_pulse)) \
                    if cfg.um_per_pulse != 0.0 else 1
        axis_no   = _AXIS_NO[axis]
        direction = "P" if positive else "M"
        cmd       = f"MS{pps};M{axis_no}N{direction}"
        try:
            response = self.controller.transport.send_command(cmd)
            self._log(f"< {response}")
        except TransportError as exc:
            self._log(f"ERROR {exc}")

    def _jog_stop(self, axis: str) -> None:
        self._send(lambda c, ax=axis: c.jog_stop(ax))

    # ── 位置のリアルタイム表示（QTimer で 300ms ごとにポーリング） ────────────

    def _poll_positions(self) -> None:
        if self.controller is None or not self.controller.is_connected():
            return
        for axis in _AXES:
            try:
                resp = self.controller.get_position(axis)   # M<n>P → "1234"
                um   = float(resp) * self._config.axes[axis].um_per_pulse
                self._rows[axis].pos_label.setText(f"{um:.2f}")
            except (TransportError, ValueError):
                # mock 応答や解析不可時はログを汚さず "—" 表示
                self._rows[axis].pos_label.setText("—")

    # ── コマンド直接送信 ───────────────────────────────────────────────────────

    def send_manual_command(self) -> None:
        command = self.command_edit.toPlainText().strip()
        if not command:
            return
        self._send(lambda c: c.transport.send_command(command))

    def _send(self, action) -> None:
        if self.controller is None or not self.controller.is_connected():
            QMessageBox.warning(self, "未接続", "先にコントローラへ接続してください。")
            return
        try:
            response = action(self.controller)
        except TransportError as exc:
            QMessageBox.critical(self, "通信エラー", str(exc))
            self._log(f"ERROR {exc}")
            return
        self._log(f"< {response}")

    # ── UI 状態管理 ───────────────────────────────────────────────────────────

    def _set_connected(self, connected: bool) -> None:
        self.connect_button.setEnabled(not connected)
        self.disconnect_button.setEnabled(connected)
        self.refresh_button.setEnabled(not connected)
        self.port_combo.setEnabled(not connected)
        self.mock_check.setEnabled(not connected)
        self._set_controls_enabled(connected)

        # 位置ポーリングの開始/停止
        if connected:
            self._poll_timer.start()
        else:
            self._poll_timer.stop()
            for r in self._rows.values():
                r.pos_label.setText("—")

    def _set_controls_enabled(self, enabled: bool) -> None:
        widgets: list[QWidget] = [self.jog_speed_spin, self.command_edit, self.send_button]
        for r in self._rows.values():
            widgets.extend(r.all_widgets())
        for w in widgets:
            w.setEnabled(enabled)

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{timestamp}] {message}")


def main(config_path: Path | None = None) -> None:
    if config_path is None:
        config_path = Path(__file__).parent.parent / "stage_config.json"
    app    = QApplication(sys.argv)
    window = MainWindow(config_path=config_path)
    window.show()
    sys.exit(app.exec())
