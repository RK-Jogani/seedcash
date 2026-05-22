import hmac
import hashlib
import os


class Slip39:
    @staticmethod
    def slip39_protocol(master_secret: str):
        # getting private master key and chain code using the master secret
        # convert master_secret to bytes to hash
        data_bytes = int(master_secret, 2).to_bytes(
            len(master_secret) // 8, byteorder="big"
        )

        hmac_hash = hmac.new(b"Bitcoin seed", data_bytes, hashlib.sha512).digest()

        private_master_key = hmac_hash[:32]
        private_master_code = hmac_hash[32:]

        return private_master_key, private_master_code

    @staticmethod
    def get_random_bits_for_slip(num_words: int) -> str:
        """
        Generate random bits for Slip39 based on the number of words.
        "10101" of length 128 or 256 random bits.
        """
        if num_words == 20:
            bits_length = 128
        elif num_words == 33:
            bits_length = 256

        # random function to generate bits
        random_bits = os.urandom(bits_length // 8)

        # Convert bytes to binary string
        random_bits_binary = "".join(format(byte, "08b") for byte in random_bits)

        # Ensure the length matches the required bits length
        if len(random_bits_binary) < bits_length:
            random_bits_binary = random_bits_binary.ljust(bits_length, "0")
        elif len(random_bits_binary) > bits_length:
            random_bits_binary = random_bits_binary[:bits_length]

        return random_bits_binary
