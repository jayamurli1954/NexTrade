"""
Input Sanitization and Validation Utilities

Provides comprehensive input validation for trading bot to prevent:
- SQL injection
- Command injection
- Path traversal
- Invalid data types
- Out-of-range values
"""

import re
import logging
from typing import Optional, Union, List
from decimal import Decimal, InvalidOperation

logger = logging.getLogger("InputSanitizer")


class InputValidationError(Exception):
    """Raised when input validation fails"""
    pass


class InputSanitizer:
    """
    Comprehensive input sanitization for trading bot

    Usage:
        sanitizer = InputSanitizer()
        symbol = sanitizer.sanitize_symbol("RELIANCE")
        price = sanitizer.sanitize_price("2500.50")
        quantity = sanitizer.sanitize_quantity("10")
    """

    # Symbol validation pattern: alphanumeric, hyphens, underscores only
    SYMBOL_PATTERN = re.compile(r'^[A-Z0-9_-]+$')

    # Exchange validation: only allowed exchanges
    VALID_EXCHANGES = {'NSE', 'BSE', 'NFO', 'MCX', 'CDS'}

    # Order action validation
    VALID_ACTIONS = {'BUY', 'SELL', 'HOLD'}

    # Max values for safety
    MAX_PRICE = 1000000.0  # 10 lakh max price
    MAX_QUANTITY = 100000  # Max 1 lakh shares
    MAX_SYMBOL_LENGTH = 20

    def __init__(self):
        logger.info("Input sanitizer initialized")

    @staticmethod
    def sanitize_symbol(symbol: str) -> str:
        """
        Sanitize and validate stock symbol

        Args:
            symbol: Stock symbol to validate

        Returns:
            str: Sanitized symbol in uppercase

        Raises:
            InputValidationError: If symbol is invalid
        """
        if not symbol or not isinstance(symbol, str):
            raise InputValidationError("Symbol must be a non-empty string")

        # Strip whitespace and convert to uppercase
        symbol = symbol.strip().upper()

        # Check length
        if len(symbol) > InputSanitizer.MAX_SYMBOL_LENGTH:
            raise InputValidationError(
                f"Symbol too long (max {InputSanitizer.MAX_SYMBOL_LENGTH} characters)"
            )

        # Check pattern (alphanumeric, hyphen, underscore only)
        if not InputSanitizer.SYMBOL_PATTERN.match(symbol):
            raise InputValidationError(
                f"Invalid symbol '{symbol}'. Only alphanumeric, hyphen, and underscore allowed"
            )

        # Check for common injection patterns
        dangerous_patterns = ['..', '/', '\\', ';', '|', '&', '$', '`', '(', ')']
        if any(pattern in symbol for pattern in dangerous_patterns):
            raise InputValidationError(
                f"Symbol contains dangerous characters"
            )

        return symbol

    @staticmethod
    def sanitize_exchange(exchange: str) -> str:
        """
        Sanitize and validate exchange name

        Args:
            exchange: Exchange name

        Returns:
            str: Validated exchange in uppercase

        Raises:
            InputValidationError: If exchange is invalid
        """
        if not exchange or not isinstance(exchange, str):
            raise InputValidationError("Exchange must be a non-empty string")

        exchange = exchange.strip().upper()

        if exchange not in InputSanitizer.VALID_EXCHANGES:
            raise InputValidationError(
                f"Invalid exchange '{exchange}'. Must be one of: {InputSanitizer.VALID_EXCHANGES}"
            )

        return exchange

    @staticmethod
    def sanitize_action(action: str) -> str:
        """
        Sanitize and validate order action

        Args:
            action: Order action (BUY/SELL/HOLD)

        Returns:
            str: Validated action in uppercase

        Raises:
            InputValidationError: If action is invalid
        """
        if not action or not isinstance(action, str):
            raise InputValidationError("Action must be a non-empty string")

        action = action.strip().upper()

        if action not in InputSanitizer.VALID_ACTIONS:
            raise InputValidationError(
                f"Invalid action '{action}'. Must be one of: {InputSanitizer.VALID_ACTIONS}"
            )

        return action

    @staticmethod
    def sanitize_price(price: Union[str, float, int]) -> float:
        """
        Sanitize and validate price

        Args:
            price: Price value

        Returns:
            float: Validated price

        Raises:
            InputValidationError: If price is invalid
        """
        try:
            # Convert to Decimal for precise validation
            if isinstance(price, str):
                price_decimal = Decimal(price.strip())
            else:
                price_decimal = Decimal(str(price))

            price_float = float(price_decimal)

            # Validate range
            if price_float <= 0:
                raise InputValidationError("Price must be positive")

            if price_float > InputSanitizer.MAX_PRICE:
                raise InputValidationError(
                    f"Price exceeds maximum ({InputSanitizer.MAX_PRICE})"
                )

            # Check for reasonable decimal places (max 2)
            if price_decimal != price_decimal.quantize(Decimal('0.01')):
                # More than 2 decimal places, round it
                price_float = round(price_float, 2)

            return price_float

        except (ValueError, InvalidOperation) as e:
            raise InputValidationError(f"Invalid price format: {e}")

    @staticmethod
    def sanitize_quantity(quantity: Union[str, int]) -> int:
        """
        Sanitize and validate quantity

        Args:
            quantity: Quantity value

        Returns:
            int: Validated quantity

        Raises:
            InputValidationError: If quantity is invalid
        """
        try:
            if isinstance(quantity, str):
                quantity_int = int(quantity.strip())
            else:
                quantity_int = int(quantity)

            if quantity_int <= 0:
                raise InputValidationError("Quantity must be positive")

            if quantity_int > InputSanitizer.MAX_QUANTITY:
                raise InputValidationError(
                    f"Quantity exceeds maximum ({InputSanitizer.MAX_QUANTITY})"
                )

            return quantity_int

        except ValueError as e:
            raise InputValidationError(f"Invalid quantity format: {e}")

    @staticmethod
    def sanitize_percentage(percentage: Union[str, float]) -> float:
        """
        Sanitize and validate percentage value (0-100)

        Args:
            percentage: Percentage value

        Returns:
            float: Validated percentage

        Raises:
            InputValidationError: If percentage is invalid
        """
        try:
            if isinstance(percentage, str):
                pct_float = float(percentage.strip())
            else:
                pct_float = float(percentage)

            if not (0 <= pct_float <= 100):
                raise InputValidationError("Percentage must be between 0 and 100")

            return round(pct_float, 2)

        except ValueError as e:
            raise InputValidationError(f"Invalid percentage format: {e}")

    @staticmethod
    def sanitize_file_path(path: str, allowed_extensions: Optional[List[str]] = None) -> str:
        """
        Sanitize file path to prevent path traversal attacks

        Args:
            path: File path
            allowed_extensions: List of allowed file extensions (e.g., ['.json', '.xlsx'])

        Returns:
            str: Sanitized path

        Raises:
            InputValidationError: If path is invalid or dangerous
        """
        if not path or not isinstance(path, str):
            raise InputValidationError("Path must be a non-empty string")

        # Check for path traversal attempts
        dangerous_patterns = ['..', '~/', '/etc', '/root', '/var', '\\\\']
        if any(pattern in path for pattern in dangerous_patterns):
            raise InputValidationError("Path contains dangerous patterns")

        # Check for absolute paths (should use relative paths)
        if path.startswith('/') or (len(path) > 1 and path[1] == ':'):
            raise InputValidationError("Absolute paths not allowed")

        # Validate extension if specified
        if allowed_extensions:
            if not any(path.endswith(ext) for ext in allowed_extensions):
                raise InputValidationError(
                    f"File extension not allowed. Must be one of: {allowed_extensions}"
                )

        return path

    @staticmethod
    def sanitize_api_key(api_key: str) -> str:
        """
        Sanitize API key (basic validation)

        Args:
            api_key: API key string

        Returns:
            str: Sanitized API key

        Raises:
            InputValidationError: If API key is invalid
        """
        if not api_key or not isinstance(api_key, str):
            raise InputValidationError("API key must be a non-empty string")

        api_key = api_key.strip()

        # Basic validation: alphanumeric only
        if not re.match(r'^[A-Za-z0-9_-]+$', api_key):
            raise InputValidationError("API key contains invalid characters")

        if len(api_key) < 8:
            raise InputValidationError("API key too short (minimum 8 characters)")

        if len(api_key) > 128:
            raise InputValidationError("API key too long (maximum 128 characters)")

        return api_key

    @staticmethod
    def sanitize_client_code(client_code: str) -> str:
        """
        Sanitize client code

        Args:
            client_code: Client code string

        Returns:
            str: Sanitized client code

        Raises:
            InputValidationError: If client code is invalid
        """
        if not client_code or not isinstance(client_code, str):
            raise InputValidationError("Client code must be a non-empty string")

        client_code = client_code.strip().upper()

        # Alphanumeric only
        if not re.match(r'^[A-Z0-9]+$', client_code):
            raise InputValidationError("Client code must be alphanumeric")

        if len(client_code) > 20:
            raise InputValidationError("Client code too long")

        return client_code

    @staticmethod
    def sanitize_totp_secret(totp_secret: str) -> str:
        """
        Sanitize TOTP secret

        Args:
            totp_secret: TOTP secret string

        Returns:
            str: Sanitized TOTP secret (uppercase, no spaces)

        Raises:
            InputValidationError: If TOTP secret is invalid
        """
        if not totp_secret or not isinstance(totp_secret, str):
            raise InputValidationError("TOTP secret must be a non-empty string")

        # Remove spaces and convert to uppercase
        totp_secret = totp_secret.replace(" ", "").upper()

        # Base32 alphabet validation
        if not re.match(r'^[A-Z2-7]+=*$', totp_secret):
            raise InputValidationError("Invalid TOTP secret format (must be Base32)")

        if len(totp_secret) < 16:
            raise InputValidationError("TOTP secret too short")

        return totp_secret


# Convenience function for bulk validation
def validate_order_params(symbol: str, exchange: str, action: str,
                          quantity: Union[str, int], price: Union[str, float]) -> dict:
    """
    Validate all order parameters at once

    Args:
        symbol: Stock symbol
        exchange: Exchange name
        action: Order action
        quantity: Order quantity
        price: Order price

    Returns:
        dict: Validated parameters

    Raises:
        InputValidationError: If any parameter is invalid
    """
    sanitizer = InputSanitizer()

    return {
        'symbol': sanitizer.sanitize_symbol(symbol),
        'exchange': sanitizer.sanitize_exchange(exchange),
        'action': sanitizer.sanitize_action(action),
        'quantity': sanitizer.sanitize_quantity(quantity),
        'price': sanitizer.sanitize_price(price)
    }


if __name__ == "__main__":
    # Test cases
    sanitizer = InputSanitizer()

    print("Testing Input Sanitizer:\n")

    # Test symbol validation
    try:
        print(f"✓ Valid symbol: {sanitizer.sanitize_symbol('RELIANCE')}")
        print(f"✓ Valid symbol: {sanitizer.sanitize_symbol('TCS-EQ')}")
    except InputValidationError as e:
        print(f"✗ {e}")

    try:
        sanitizer.sanitize_symbol("REL; DROP TABLE;")
    except InputValidationError as e:
        print(f"✓ Blocked injection: {e}")

    # Test price validation
    try:
        print(f"✓ Valid price: {sanitizer.sanitize_price('2500.50')}")
        print(f"✓ Valid price: {sanitizer.sanitize_price(1234.56)}")
    except InputValidationError as e:
        print(f"✗ {e}")

    try:
        sanitizer.sanitize_price("-100")
    except InputValidationError as e:
        print(f"✓ Blocked negative price: {e}")

    # Test quantity validation
    try:
        print(f"✓ Valid quantity: {sanitizer.sanitize_quantity('10')}")
    except InputValidationError as e:
        print(f"✗ {e}")

    try:
        sanitizer.sanitize_quantity("0")
    except InputValidationError as e:
        print(f"✓ Blocked zero quantity: {e}")

    print("\nAll tests completed!")
