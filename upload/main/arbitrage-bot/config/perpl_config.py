"""
perpl_config.py — теперь настраивается из .env (только API) + perpl_strategy_config.yml (параметры)
Best-practices: ключи и профили — отдельно, чтобы можно было менять стратегию руками без перезапуска.
"""
import os
from dataclasses import dataclass
from typing import Optional, Any
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

import yaml

@dataclass(frozen=True)
class PerplExchangeCredentials:
    api_key: str
    api_secret: str

@dataclass(frozen=True)
class PerplStrategyParams:
    target_amount_usdc: float  # Сумма USDC для 1 круга
    min_profit_percent: float  # Минимальный профит в %% от круга
    use_websocket: bool        # Использовать WebSocket для стаканов
    rest_polling_interval: float  # Интервал резервного REST (сек)

@dataclass(frozen=True)
class PerplSettings:
    mexc: PerplExchangeCredentials
    bingx: PerplExchangeCredentials
    trading_mode: str
    strategy: PerplStrategyParams


def load_perpl_settings(env_path: Optional[str] = None,
                       yml_path: str = "upload/main/arbitrage-bot/config/perpl_strategy_config.yml") -> PerplSettings:
    """
    Загружает ключи из .env и настройки из YAML-конфига.
    """
    if load_dotenv and (env_path or os.path.exists('config/.env') or os.path.exists('.env')):
        load_dotenv(env_path or 'config/.env' if os.path.exists('config/.env') else '.env')
    def getenv(name, default=None, required=False, cast=str):
        value = os.getenv(name, default)
        if required and value is None:
            raise RuntimeError(f"Env variable '{name}' required")
        return cast(value) if value is not None else None
    mexc = PerplExchangeCredentials(
        api_key=getenv('MEXC_API_KEY', '', True),
        api_secret=getenv('MEXC_SECRET', '', True)
    )
    bingx = PerplExchangeCredentials(
        api_key=getenv('BINGX_API_KEY', '', True),
        api_secret=getenv('BINGX_SECRET', '', True)
    )
    # YML
    with open(yml_path, encoding='utf-8') as f:
        yml = yaml.safe_load(f)
    mode = yml.get("trading_mode", "paper")
    params: dict[str, Any] = yml["strategies"]["cross_exchange_btc_usdc"]
    strat = PerplStrategyParams(
        target_amount_usdc=float(params["target_amount_usdc"]),
        min_profit_percent=float(params["min_profit_percent"]),
        use_websocket=bool(params["use_websocket"]),
        rest_polling_interval=float(params["rest_polling_interval"]),
    )
    return PerplSettings(
        mexc=mexc,
        bingx=bingx,
        trading_mode=mode,
        strategy=strat
    )
