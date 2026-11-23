import hmac
import hashlib


class Slip39:
    @staticmethod
    def slip39_protocol(master_secret: bytearray) -> tuple[bytes, bytes]:
        
        data_bytes = bytearray(master_secret)
        hmac_hash = hmac.new(b"Bitcoin seed", data_bytes, hashlib.sha512).digest()

        private_master_key = hmac_hash[:32]
        private_master_code = hmac_hash[32:]

        return (private_master_key, private_master_code)
