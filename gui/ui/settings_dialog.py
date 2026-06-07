"""
settings_dialog.py
ステージ軸設定ダイアログ。
各軸の μm/pulse 係数・速度上限・ソフトリミット・ホームオフセットを入力し、
MCU への書き込み（RS コマンドでフラッシュ保存）と読み込みを行う。
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.stage_config import (
    AXES,
    MICROSTEP_OPTIONS,
    MOTOR_MODELS,
    AxisConfig,
    StageConfig,
)

if TYPE_CHECKING:
    from core.controller import StageController


class _AxisWidget(QWidget):
    """1軸分の設定フォーム"""

    def __init__(self, cfg: AxisConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build(cfg)

    def _dspin(
        self,
        lo: float,
        hi: float,
        step: float,
        suffix: str,
        value: float,
        decimals: int = 4,
    ) -> QDoubleSpinBox:
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setSingleStep(step)
        w.setDecimals(decimals)
        w.setSuffix(suffix)
        w.setValue(value)
        return w

    def _build(self, cfg: AxisConfig) -> None:
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setContentsMargins(12, 12, 12, 12)
        form.setVerticalSpacing(8)

        # 1フルステップ移動量 [μm/fullstep]
        self.um_per_fullstep = self._dspin(1e-4, 1e6, 0.1, " μm/full", cfg.um_per_fullstep, 4)
        form.addRow("1フルステップ移動量", self.um_per_fullstep)

        # 分解能（microstep）
        self.microstep = QComboBox()
        for ms in MICROSTEP_OPTIONS:
            self.microstep.addItem(f"1/{ms}" if ms != 1 else "フルステップ", ms)
        idx = self.microstep.findData(cfg.microstep)
        self.microstep.setCurrentIndex(idx if idx >= 0 else 0)
        form.addRow("分解能", self.microstep)

        # → um/pulse 算出値（読み取り専用表示）
        self.upp_label = QLabel()
        self.um_per_fullstep.valueChanged.connect(self._update_upp)
        self.microstep.currentIndexChanged.connect(self._update_upp)
        form.addRow("→ μm/pulse", self.upp_label)

        # モーター型番（MOT_SEL）
        self.motor_model = QComboBox()
        for name, val in MOTOR_MODELS.items():
            self.motor_model.addItem(name, val)
        midx = self.motor_model.findData(cfg.motor_model)
        self.motor_model.setCurrentIndex(midx if midx >= 0 else 0)
        form.addRow("モーター型番", self.motor_model)

        # 初速度・加速時間
        self.start_speed = self._dspin(0.0, 500_000.0, 100.0, " μm/s", cfg.start_speed_um_s, 1)
        form.addRow("初速度", self.start_speed)
        self.accel_time = QSpinBox()
        self.accel_time.setRange(1, 60_000)
        self.accel_time.setSingleStep(10)
        self.accel_time.setSuffix(" ms")
        self.accel_time.setValue(cfg.accel_time_ms)
        form.addRow("加速時間", self.accel_time)

        # 速度上限
        self.max_speed = self._dspin(1.0, 500_000.0, 500.0, " μm/s", cfg.max_speed_um_s, 1)
        form.addRow("最大速度", self.max_speed)

        # ソフトリミット
        self.limit_cw  = self._dspin(-1e7, 1e7, 1000.0, " μm", cfg.limit_cw_um,  1)
        self.limit_ccw = self._dspin(-1e7, 1e7, 1000.0, " μm", cfg.limit_ccw_um, 1)
        form.addRow("CW リミット",  self.limit_cw)
        form.addRow("CCW リミット", self.limit_ccw)

        # ホームオフセット
        self.home_offset = self._dspin(-1e7, 1e7, 100.0, " μm", cfg.home_offset_um, 1)
        form.addRow("ホームオフセット", self.home_offset)

        self._update_upp()

    def _update_upp(self) -> None:
        """1フルステップ移動量と microstep から um/pulse を算出表示する"""
        upf = self.um_per_fullstep.value()
        ms  = self.microstep.currentData()
        upp = upf / ms if ms else 0.0
        self.upp_label.setText(f"{upp:.6g} μm/pulse")

    def to_axis_config(self) -> AxisConfig:
        """ウィジェットの現在値から AxisConfig を生成する"""
        return AxisConfig(
            um_per_fullstep  = self.um_per_fullstep.value(),
            microstep        = self.microstep.currentData(),
            start_speed_um_s = self.start_speed.value(),
            accel_time_ms    = self.accel_time.value(),
            motor_model      = self.motor_model.currentData(),
            max_speed_um_s   = self.max_speed.value(),
            limit_cw_um      = self.limit_cw.value(),
            limit_ccw_um     = self.limit_ccw.value(),
            home_offset_um   = self.home_offset.value(),
        )

    def load_from_axis_config(self, cfg: AxisConfig) -> None:
        """AxisConfig の値でウィジェットを更新する"""
        self.um_per_fullstep.setValue(cfg.um_per_fullstep)
        idx = self.microstep.findData(cfg.microstep)
        self.microstep.setCurrentIndex(idx if idx >= 0 else 0)
        midx = self.motor_model.findData(cfg.motor_model)
        self.motor_model.setCurrentIndex(midx if midx >= 0 else 0)
        self.start_speed.setValue(cfg.start_speed_um_s)
        self.accel_time.setValue(cfg.accel_time_ms)
        self.max_speed.setValue(cfg.max_speed_um_s)
        self.limit_cw.setValue(cfg.limit_cw_um)
        self.limit_ccw.setValue(cfg.limit_ccw_um)
        self.home_offset.setValue(cfg.home_offset_um)


class StageSettingsDialog(QDialog):
    """ステージ設定ダイアログ"""

    def __init__(
        self,
        config: StageConfig,
        config_path: Path,
        controller: StageController | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("ステージ設定")
        self.setMinimumWidth(480)
        self._config = config
        self._config_path = config_path
        self._controller = controller
        self._axis_widgets: dict[str, _AxisWidget] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # タブ（軸ごと）
        tabs = QTabWidget()
        for ax in AXES:
            w = _AxisWidget(self._config.axes[ax])
            self._axis_widgets[ax] = w
            tabs.addTab(w, f"軸 {ax}")
        root.addWidget(tabs)

        # MCU 操作ボタン
        mcu_row = QHBoxLayout()
        self._write_btn = QPushButton("MCUに書き込み・保存")
        self._read_btn  = QPushButton("MCUから読み込み")
        self._write_btn.clicked.connect(self._write_to_mcu)
        self._read_btn.clicked.connect(self._read_from_mcu)
        mcu_row.addWidget(self._write_btn)
        mcu_row.addWidget(self._read_btn)
        mcu_row.addStretch()
        root.addLayout(mcu_row)

        if self._controller is None:
            self._write_btn.setEnabled(False)
            self._read_btn.setEnabled(False)

        # OK / キャンセル
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ── 内部処理 ──────────────────────────────────────────────────────────────

    def _collect(self) -> None:
        """ウィジェットの値を _config に反映する"""
        for ax, w in self._axis_widgets.items():
            self._config.axes[ax] = w.to_axis_config()

    def _accept(self) -> None:
        self._collect()
        try:
            self._config.save(self._config_path)
        except Exception as exc:
            QMessageBox.warning(self, "保存エラー", f"設定ファイルの保存に失敗しました:\n{exc}")
        self.accept()

    def _write_to_mcu(self) -> None:
        self._collect()
        try:
            self._config.write_to_mcu(self._controller)
            QMessageBox.information(self, "完了", "MCU へ書き込み、フラッシュへ保存しました。")
        except Exception as exc:
            QMessageBox.critical(self, "エラー", f"MCU への書き込みに失敗しました:\n{exc}")

    def _read_from_mcu(self) -> None:
        try:
            self._config.read_from_mcu(self._controller)
        except Exception as exc:
            QMessageBox.critical(self, "エラー", f"MCU からの読み込みに失敗しました:\n{exc}")
            return
        for ax, w in self._axis_widgets.items():
            w.load_from_axis_config(self._config.axes[ax])
        QMessageBox.information(self, "完了", "MCU から読み込みました。")
