"""
perpl_config.py — автозагрузка переменных окружения для стратегий/бирж;
интеграция с .env, dataclass настройки и пояснения к каждому полю, best-practice.
"""
import os
from dataclasses import dataclass
from typing import Optional
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

@dataclass(frozen=True)
class PerplExchangeCredentials:
    api_key: str  # API-ключ для биржи
    api_secret: str  # Секретный ключ для биржи

@dataclass(frozen=True)
class PerplSettings:
    mexc: PerplExchangeCredentials  # Объект с ключами для MEXC
    bingx: PerplExchangeCredentials  # Объект с ключами для BingX
    trading_mode: str  # paper = тест, live = боевой режим
    target_size_btc: float  # Размер позиции для арбитража (BTC)
    min_profit_usd: float  # Минимальная прибыль (USDC)
    min_spread_bps: float  # Минимальный требуемый спред (bps = 0.01%)

def load_perpl_settings(env_path: Optional[str] = None) -> PerplSettings:
    """
    Загружает параметры из .env или окружения.
    env_path: путь до .env (по умолчанию config/.env или .env)
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
    mode = getenv('TRADING_MODE', 'paper').lower()
    size_btc = float(getenv('TARGET_SIZE_BTC', 0.01))
    min_profit = float(getenv('MIN_PROFIT_USD', 1.0))
    min_spread = float(getenv('MIN_SPREAD_BPS', 5.0))
    return PerplSettings(
        mexc=mexc,
        bingx=bingx,
        trading_mode=mode,
        target_size_btc=size_btc,
        min_profit_usd=min_profit,
        min_spread_bps=min_spread
    )
