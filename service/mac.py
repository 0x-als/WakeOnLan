import re


class Mac:
    HEX = re.compile(r"^[0-9A-F]{12}$")

    @classmethod
    def normalize(cls, value):
        cleaned = re.sub(r"[^0-9A-Fa-f]", "", str(value or "")).upper()
        if not cls.HEX.match(cleaned):
            raise ValueError("MAC-адрес должен содержать 12 шестнадцатеричных символов")
        return ":".join(cleaned[i:i + 2] for i in range(0, 12, 2))

    @classmethod
    def to_bytes(cls, value):
        return bytes.fromhex(cls.normalize(value).replace(":", ""))

    @classmethod
    def is_valid(cls, value):
        try:
            cls.normalize(value)
            return True
        except ValueError:
            return False

    @classmethod
    def is_usable(cls, value):
        try:
            mac = cls.normalize(value)
        except ValueError:
            return False
        if mac in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
            return False
        return not mac.startswith(("01:00:5E", "33:33"))
