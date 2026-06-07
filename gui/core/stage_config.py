"""
stage_config.py
ステージ軸設定と MCU パラメータレジスタの読み書き。

設定の真の入力値 = 1フルステップ移動量[μm/fullstep] + 分解能(microstep)。
um/pulse はここから自動計算する（分解能との物理的整合を保証）:
    um/pulse = um_per_fullstep / microstep
    （1フルステップ = microstep パルスに分割されるため）

MCU パラメータアドレスマップ:
  addr 104-106 : COEF_NUM  [μm/pulse] ← um_per_pulse を格納
  addr 120-122 : COEF_DEN  [pulse]    ← 常に 1.0
  addr  72-74  : limit_cw   [μm]
  addr  88-90  : limit_ccw  [μm]
  addr  56-58  : home_offset[μm]
  addr 136-138 : start_pps  [pps]     ← 初速度 (μm/s ÷ um/pulse)
  addr 152-154 : accel_ms   [ms]      ← 加速時間
  addr 168-170 : resolution [reg]     ← microstep × 10
  addr 200-202 : mot_sel    [16bit]   ← モーター型番
  addr 183     : init_access_mask
  addr 184     : motor_en_mask
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.controller import StageController

# ── 軸定義 ────────────────────────────────────────────────────────────────────

AXES = ("X", "Y", "Z")
AXIS_IDX = {"X": 0, "Y": 1, "Z": 2}

# 分解能(microstep) → CVD RESOLUTION レジスタ値
MICROSTEP_TO_REG = {1: 10, 2: 20, 4: 40, 5: 50, 10: 100, 20: 200, 50: 500, 100: 1000}
MICROSTEP_OPTIONS = tuple(MICROSTEP_TO_REG.keys())

# モーター型番 → CVD MOT_SEL 値
MOTOR_MODELS = {
    "0.35 A": 0xFF00,
    "0.75 A": 0xFE01,
    "1.20 A": 0xFD02,
    "1.40 A": 0xFC03,
    "1.80 A": 0xFB04,
    "2.40 A": 0xFA05,
}

# ── MCU パラメータアドレス ─────────────────────────────────────────────────────

ADDR_COEFF_NUM    = (104, 105, 106)
ADDR_COEFF_DEN    = (120, 121, 122)
ADDR_LIMIT_CW     = ( 72,  73,  74)
ADDR_LIMIT_CCW    = ( 88,  89,  90)
ADDR_HOME_OFFSET  = ( 56,  57,  58)
ADDR_START        = (136, 137, 138)
ADDR_ACCEL        = (152, 153, 154)
ADDR_RESOL        = (168, 169, 170)
ADDR_MOTSEL       = (200, 201, 202)
ADDR_INIT_ACCESS  = 183
ADDR_MOTOR_EN     = 184


# ── データクラス ───────────────────────────────────────────────────────────────

@dataclass
class AxisConfig:
    """1軸分のステージ設定（真の入力値は um_per_fullstep + microstep）"""
    um_per_fullstep: float = 1.0       # 1フルステップ移動量 [μm/fullstep]
    microstep: int         = 100       # 分解能 (1/2/4/5/10/20/50/100)
    start_speed_um_s: float = 100.0    # 初速度 [μm/s]
    accel_time_ms: int     = 100       # 加速時間 [ms]
    motor_model: int       = 0xFE01    # モーター型番 (MOT_SEL値)
    max_speed_um_s: float  = 5000.0    # 最大速度 [μm/s]
    limit_cw_um: float     = 25000.0   # CW ソフトリミット [μm]
    limit_ccw_um: float    = 0.0       # CCW ソフトリミット [μm]
    home_offset_um: float  = 0.0       # ホームオフセット [μm]
    motor_en: bool         = True      # モーター有効
    init_access: bool      = False     # 起動時ホーミング実施

    @property
    def um_per_pulse(self) -> float:
        """[μm/pulse] = um_per_fullstep / microstep"""
        return self.um_per_fullstep / self.microstep if self.microstep != 0 else 1.0

    @property
    def resolution_reg(self) -> int:
        """CVD RESOLUTION レジスタ値 = microstep × 10"""
        return MICROSTEP_TO_REG.get(self.microstep, self.microstep * 10)


@dataclass
class StageConfig:
    """3軸ステージ設定の集合体"""
    axes: dict[str, AxisConfig] = field(
        default_factory=lambda: {ax: AxisConfig() for ax in AXES}
    )

    # ── ファイル保存 / 読み込み ─────────────────────────────────────────────────

    def save(self, path: Path) -> None:
        data = {ax: asdict(cfg) for ax, cfg in self.axes.items()}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> StageConfig:
        data = json.loads(path.read_text(encoding="utf-8"))
        axes = {ax: AxisConfig(**cfg) for ax, cfg in data.items()}
        return cls(axes=axes)

    @classmethod
    def load_or_default(cls, path: Path) -> StageConfig:
        try:
            return cls.load(path)
        except Exception:
            return cls()

    # ── MCU への書き込み ────────────────────────────────────────────────────────

    def write_to_mcu(self, controller: StageController) -> None:
        """全軸パラメータを MCU レジスタに書き込み、フラッシュへ保存する。"""
        motor_en_mask    = 0
        init_access_mask = 0

        for ax in AXES:
            i   = AXIS_IDX[ax]
            cfg = self.axes[ax]
            upp = cfg.um_per_pulse
            start_pps = max(1, round(cfg.start_speed_um_s / upp)) if upp != 0.0 else 1

            # um/pulse は COEF_NUM/DEN として MCU の m-prefix 換算用に保持
            controller.set_register(ADDR_COEFF_NUM[i],   upp)
            controller.set_register(ADDR_COEFF_DEN[i],   1.0)
            controller.set_register(ADDR_LIMIT_CW[i],    cfg.limit_cw_um)
            controller.set_register(ADDR_LIMIT_CCW[i],   cfg.limit_ccw_um)
            controller.set_register(ADDR_HOME_OFFSET[i], cfg.home_offset_um)
            controller.set_register(ADDR_START[i],       start_pps)
            controller.set_register(ADDR_ACCEL[i],       cfg.accel_time_ms)
            controller.set_register(ADDR_RESOL[i],       cfg.resolution_reg)
            controller.set_register(ADDR_MOTSEL[i],      cfg.motor_model)
            if cfg.motor_en:
                motor_en_mask    |= (1 << i)
            if cfg.init_access:
                init_access_mask |= (1 << i)

        controller.set_register(ADDR_MOTOR_EN,    motor_en_mask)
        controller.set_register(ADDR_INIT_ACCESS, init_access_mask)
        controller.save_registers()   # RS コマンド → フラッシュ保存

    # ── MCU からの読み込み ──────────────────────────────────────────────────────

    def read_from_mcu(self, controller: StageController) -> None:
        """MCU レジスタから全軸パラメータを読み込む。
        um_per_fullstep は COEF_NUM(=um/pulse) × microstep で逆算する。
        """
        try:
            motor_en_mask    = int(float(controller.get_register(ADDR_MOTOR_EN)))
            init_access_mask = int(float(controller.get_register(ADDR_INIT_ACCESS)))
        except (ValueError, TypeError):
            motor_en_mask    = 0
            init_access_mask = 0

        reg_to_microstep = {v: k for k, v in MICROSTEP_TO_REG.items()}

        for ax in AXES:
            i   = AXIS_IDX[ax]
            cfg = self.axes[ax]
            try:
                resol = int(float(controller.get_register(ADDR_RESOL[i])))
                cfg.microstep      = reg_to_microstep.get(resol, max(1, resol // 10))
                cfg.motor_model    = int(float(controller.get_register(ADDR_MOTSEL[i])))
                cfg.accel_time_ms  = int(float(controller.get_register(ADDR_ACCEL[i])))
                # um/pulse(=COEF_NUM) × microstep で 1フルステップ移動量を逆算
                upp = float(controller.get_register(ADDR_COEFF_NUM[i]))
                cfg.um_per_fullstep = upp * cfg.microstep
                start_pps          = float(controller.get_register(ADDR_START[i]))
                cfg.start_speed_um_s = start_pps * cfg.um_per_pulse
                cfg.limit_cw_um    = float(controller.get_register(ADDR_LIMIT_CW[i]))
                cfg.limit_ccw_um   = float(controller.get_register(ADDR_LIMIT_CCW[i]))
                cfg.home_offset_um = float(controller.get_register(ADDR_HOME_OFFSET[i]))
            except (ValueError, TypeError):
                pass
            cfg.motor_en    = bool(motor_en_mask    & (1 << i))
            cfg.init_access = bool(init_access_mask & (1 << i))
