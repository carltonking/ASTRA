"""Alpaca integration exceptions for ASTRA."""


class LiveTradingBlockedError(RuntimeError):
    """Raised when an attempt is made to connect to a live (non-paper) Alpaca endpoint."""

    def __init__(self, url: str = ""):
        msg = (
            f"Live trading is blocked in ASTRA v0.1.0. "
            f"Only paper trading is supported at paper-api.alpaca.markets. "
            f"Refused connection to: {url}"
        ).strip()
        super().__init__(msg)


class ShortSellingBlockedError(RuntimeError):
    """Raised when an attempt is made to submit a sell order without an existing position."""

    def __init__(self, symbol: str = ""):
        msg = f"Short selling is blocked in ASTRA v0.1.0. Cannot sell {symbol if symbol else 'symbol'} without an existing long position."
        super().__init__(msg)


class DeploymentError(RuntimeError):
    """Raised when a strategy deployment fails."""

    ...


class AlpacaConnectionError(RuntimeError):
    """Raised when connection to Alpaca API fails."""
    ...
