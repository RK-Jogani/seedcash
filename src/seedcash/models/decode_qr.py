import base64
import logging
import re
import zlib

from binascii import a2b_base64, b2a_base64
from enum import IntEnum
from pyzbar import pyzbar
from pyzbar.pyzbar import ZBarSymbol
from base64 import b32decode

from seedcash.helpers.ur2.ur_decoder import URDecoder
from seedcash.models.qr_type import QRType

logger = logging.getLogger(__name__)


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    value = buf[pos]
    if value < 0xFD:
        return value, pos + 1
    if value == 0xFD:
        return int.from_bytes(buf[pos + 1 : pos + 3], "little"), pos + 3
    if value == 0xFE:
        return int.from_bytes(buf[pos + 1 : pos + 5], "little"), pos + 5
    return int.from_bytes(buf[pos + 1 : pos + 9], "little"), pos + 9


def _serialize_varint(value: int) -> bytes:
    if value < 0xFD:
        return bytes([value])
    if value <= 0xFFFF:
        return b"\xfd" + value.to_bytes(2, "little")
    if value <= 0xFFFFFFFF:
        return b"\xfe" + value.to_bytes(4, "little")
    return b"\xff" + value.to_bytes(8, "little")


def _scan_psbt_map_end(buf: bytes, pos: int) -> int:
    while pos < len(buf):
        key_len, pos = _read_varint(buf, pos)
        if key_len == 0:
            return pos
        pos += key_len
        value_len, pos = _read_varint(buf, pos)
        pos += value_len
    raise ValueError("unexpected end while scanning PSBT map")


class DecodeQRStatus(IntEnum):
    """
    Used in DecodeQR to communicate status of adding qr frame/segment
    """

    PART_COMPLETE = 1
    PART_EXISTING = 2
    COMPLETE = 3
    FALSE = 4
    INVALID = 5


class DecodeQR:
    """
    Used to process images or string data from animated qr codes.
    """

    def __init__(self):
        self.complete = False
        self.qr_type = None
        self.decoder = None

    def add_image(self, image):
        data = DecodeQR.extract_qr_data(image, is_binary=True)
        if data == None:
            return DecodeQRStatus.FALSE

        return self.add_data(data)

    def add_data(self, data):
        if data == None:
            return DecodeQRStatus.FALSE

        qr_type = DecodeQR.detect_segment_type(data)

        if self.qr_type == None:
            self.qr_type = qr_type

            if self.qr_type == QRType.PSBT__UR2:
                self.decoder = URDecoder()  # BCUR Decoder
            elif self.qr_type == QRType.PSBT__SPECTER:
                self.decoder = SpecterPsbtQrDecoder()
            elif self.qr_type == QRType.PSBT__BASE64:
                self.decoder = Base64PsbtQrDecoder()
            elif self.qr_type == QRType.PSBT__BASE43:
                self.decoder = Base43PsbtQrDecoder()
            elif self.qr_type == QRType.PSBT__BBQR:
                self.decoder = BBQRPsbtQrDecoder()

        elif self.qr_type != qr_type:
            raise Exception("QR Fragment Unexpected Type Change")

        if not self.decoder:
            # Did not find any recognizable format
            return DecodeQRStatus.INVALID

        # Convert to string data
        if type(data) == bytes:
            # Should always be bytes, but the test suite has some manual datasets that
            # are strings.
            # TODO: Convert the test suite rather than handle here?
            qr_str = data.decode("utf-8")
        else:
            # it's already str data
            qr_str = data

        if self.qr_type == QRType.PSBT__UR2:
            added_part = self.decoder.receive_part(qr_str)
            if self.decoder.is_complete():
                self.complete = True
                return DecodeQRStatus.COMPLETE
            if added_part:
                return DecodeQRStatus.PART_COMPLETE
            else:
                return DecodeQRStatus.PART_EXISTING

        else:
            # All other formats use the same method signature
            rt = self.decoder.add(qr_str, self.qr_type)
            if rt == DecodeQRStatus.COMPLETE:
                self.complete = True
            return rt

    def get_psbt(self):
        if self.complete:
            return self.get_data_psbt()
        return None

    def get_data_psbt(self):
        if self.complete:
            if self.qr_type == QRType.PSBT__UR2:
                return self.decoder.result_message().cbor

        return None

    def get_base64_psbt(self):
        if self.complete:
            data = self.get_data_psbt()
            b64_psbt = b2a_base64(data)

            if b64_psbt[-1:] == b"\n":
                b64_psbt = b64_psbt[:-1]

            return b64_psbt.decode("utf-8")
        return None

    def get_qr_data(self) -> dict:
        """
        This provides a single access point for external code to retrieve the QR data,
        regardless of which decoder is actually instantiated.
        """
        # TODO: Implement this approach across all decoders
        return self.decoder.get_qr_data()

    def get_percent_complete(self, weight_mixed_frames: bool = False) -> int:
        if not self.decoder:
            return 0

        if self.qr_type == QRType.PSBT__UR2:
            return int(
                self.decoder.estimated_percent_complete(
                    weight_mixed_frames=weight_mixed_frames
                )
                * 100
            )

        elif self.qr_type in [QRType.PSBT__SPECTER, QRType.PSBT__BBQR]:
            if self.decoder.total_segments == None:
                return 0
            return int(
                (self.decoder.collected_segments / self.decoder.total_segments) * 100
            )

        elif self.decoder.total_segments == 1:
            # The single frame QR formats are all or nothing
            if self.decoder.complete:
                return 100
            else:
                return 0

        else:
            return 0

    @property
    def is_complete(self) -> bool:
        return self.complete

    @property
    def is_invalid(self) -> bool:
        return self.qr_type == QRType.INVALID

    @property
    def is_psbt(self) -> bool:
        return self.qr_type in [
            QRType.PSBT__UR2,
            QRType.PSBT__SPECTER,
            QRType.PSBT__BASE64,
            QRType.PSBT__BASE43,
            QRType.PSBT__BBQR,
        ]

    @staticmethod
    def extract_qr_data(image, is_binary: bool = False) -> str | None:
        if image is None:
            return None

        barcodes = pyzbar.decode(image, symbols=[ZBarSymbol.QRCODE], binary=is_binary)

        # if barcodes:
        # print("--------------- extract_qr_data ---------------")
        # print(barcodes)

        for barcode in barcodes:
            # Only pull and return the first barcode
            return barcode.data

    @staticmethod
    def detect_segment_type(s):

        try:
            # Convert to str data
            if type(s) == bytes:
                # Should always be bytes, but the test suite has some manual datasets that
                # are strings.
                # TODO: Convert the test suite rather than handle here?
                s = s.decode("utf-8")

            logger.debug(f"segment string: {s}")
            logger.debug(f"segment string length: {len(s)}")

            # PSBT
            if re.search("^UR:CRYPTO-PSBT/", s, re.IGNORECASE):
                return QRType.PSBT__UR2

            elif re.search("^UR:CRYPTO-OUTPUT/", s, re.IGNORECASE):
                return QRType.OUTPUT__UR

            elif re.search(
                r"^p(\d+)of(\d+) ([A-Za-z0-9+\/=]+$)", s, re.IGNORECASE
            ):  # must be base64 characters only in segment
                return QRType.PSBT__SPECTER

            elif re.search("^UR:BYTES/", s, re.IGNORECASE):
                return QRType.BYTES__UR

            elif DecodeQR.is_base64_psbt(s):
                return QRType.PSBT__BASE64

            elif re.search(
                r"^B\$[2HZ]P[0-9A-Z]{4}", s
            ):  # https://github.com/coinkite/BBQr/blob/master/BBQr.md#spliting-the-data
                return QRType.PSBT__BBQR

            elif DecodeQR.is_base43_psbt(s):
                return QRType.PSBT__BASE43

        except UnicodeDecodeError:
            # Probably this isn't meant to be string data; check if it's valid byte data
            # below.
            pass

        # Is it byte data?
        if not isinstance(s, bytes):
            try:
                # TODO: remove this check & conversion once above cast to str is removed
                s = s.encode()
            except UnicodeError:
                # Couldn't convert back to bytes; shouldn't happen
                raise Exception("Conversion to bytes failed")

        return QRType.INVALID

    @staticmethod
    def is_base64(s):
        try:
            return base64.b64encode(base64.b64decode(s)) == s.encode("ascii")
        except Exception:
            return False

    @staticmethod
    def is_base64_psbt(s):
        from seedcash.models.psbt_parser import parse_psbt

        try:
            if DecodeQR.is_base64(s):
                parse_psbt(a2b_base64(s))
                return True
        except Exception:
            return False
        return False

    @staticmethod
    def is_base43_psbt(s):
        from seedcash.models.psbt_parser import parse_psbt

        try:
            parse_psbt(DecodeQR.base43_decode(s))
            return True
        except Exception:
            return False

    @staticmethod
    def base43_decode(s):
        chars = b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ$*+-./:"  # base43 chars

        if isinstance(s, bytes):
            v = s
        if isinstance(s, str):
            v = s.encode("ascii")
        elif isinstance(s, bytearray):
            v = bytes(s)

        long_value = 0
        power_of_base = 1
        for c in v[::-1]:
            digit = chars.find(bytes([c]))
            if digit == -1:
                raise Exception("Forbidden character {} for base {}".format(c, 43))
            # naive but slow variant:   long_value += digit * (base**i)
            long_value += digit * power_of_base
            power_of_base *= 43
        result = bytearray()
        while long_value >= 256:
            div, mod = divmod(long_value, 256)
            result.append(mod)
            long_value = div
        result.append(long_value)
        nPad = 0
        for c in v:
            if c == chars[0]:
                nPad += 1
            else:
                break
        result.extend(b"\x00" * nPad)
        result.reverse()
        return bytes(result)


class BaseQrDecoder:
    def __init__(self):
        self.total_segments = None
        self.collected_segments = 0
        self.complete = False

    @property
    def is_complete(self) -> bool:
        return self.complete

    def add(self, segment, qr_type):
        raise Exception("Not implemented in child class")

    def get_qr_data(self) -> dict:
        # TODO: standardize this approach across all decoders (example: SignMessageQrDecoder)
        raise Exception("get_qr_data must be implemented in decoder child class")


class BaseSingleFrameQrDecoder(BaseQrDecoder):
    def __init__(self):
        super().__init__()
        self.total_segments = 1


class BaseAnimatedQrDecoder(BaseQrDecoder):
    def __init__(self):
        super().__init__()
        self.segments = []

    def current_segment_num(self, segment) -> int:
        raise Exception("Not implemented in child class")

    def total_segment_nums(self, segment) -> int:
        raise Exception("Not implemented in child class")

    def parse_segment(self, segment) -> str:
        raise Exception("Not implemented in child class")

    @property
    def is_valid(self) -> bool:
        return True

    def add(self, segment, qr_type=None):
        if self.total_segments == None:
            self.total_segments = self.total_segment_nums(segment)
            self.segments = [None] * self.total_segments
        elif self.total_segments != self.total_segment_nums(segment):
            raise Exception("Segment total changed unexpectedly")

        current_segment_num = self.current_segment_num(segment)
        if self.segments[current_segment_num - 1] == None:
            self.segments[current_segment_num - 1] = self.parse_segment(segment)
            self.collected_segments += 1
            if self.total_segments == self.collected_segments:
                if self.is_valid:
                    self.complete = True
                    return DecodeQRStatus.COMPLETE
                else:
                    return DecodeQRStatus.INVALID
            return DecodeQRStatus.PART_COMPLETE  # new segment added

        return (
            DecodeQRStatus.PART_EXISTING
        )  # segment not added because it's already been added


class SpecterPsbtQrDecoder(BaseAnimatedQrDecoder):
    """
    Used to decode Specter Desktop Animated QR PSBT encoding.
    """

    def get_base64_data(self) -> str:
        base64 = "".join(self.segments)
        if self.complete and DecodeQR.is_base64(base64):
            return base64

        return None

    def get_data(self):
        base64 = self.get_base64_data()
        if base64 != None:
            return a2b_base64(base64)

        return None

    def current_segment_num(self, segment) -> int:
        if re.search(r"^p(\d+)of(\d+) ", segment, re.IGNORECASE) != None:
            return int(re.search(r"^p(\d+)of(\d+) ", segment, re.IGNORECASE).group(1))

    def total_segment_nums(self, segment) -> int:
        if re.search(r"^p(\d+)of(\d+) ", segment, re.IGNORECASE) != None:
            return int(re.search(r"^p(\d+)of(\d+) ", segment, re.IGNORECASE).group(2))

    def parse_segment(self, segment) -> str:
        return segment.split(" ")[-1].strip()


class BBQRPsbtQrDecoder(BaseAnimatedQrDecoder):
    """
    Used to decode BBQR Animated PSBT encoding.
    """

    def __init__(self):
        super().__init__()
        self.encoding = None

    def get_data(self) -> str:
        logger.debug("BBQRPsbtQrDecoder get_data")
        data = "".join(self.segments)
        if self.complete and self.encoding:
            if self.encoding == "H":
                return b"".join(bytes.fromhex(s) for s in self.segments)

            # base32 decode, but insert padding for API
            rv = b""
            for p in self.segments:
                padding = (8 - (len(p) % 8)) % 8
                rv += b32decode(p + (padding * "="))

            if self.encoding == "Z":
                # decompress
                z = zlib.decompressobj(wbits=-10)
                rv = z.decompress(rv)
                rv += z.flush()

            return rv

        return None

    def current_segment_num(self, segment) -> int:
        current_segment = int(segment[6:8], 36) + 1
        logger.debug(f"BBQRPsbtQrDecoder current_segment_num {current_segment}")
        return current_segment

    def total_segment_nums(self, segment) -> int:
        total_segments = int(segment[4:6], 36)
        logger.debug(f"BBQRPsbtQrDecoder total_segment_nums {total_segments}")
        return total_segments

    def parse_segment(self, segment) -> str:
        self.encoding = segment[2]
        file_type = segment[3]
        data = segment[8:]

        return data.strip()


class Base64PsbtQrDecoder(BaseSingleFrameQrDecoder):
    """
    Decodes single frame base64 encoded qr image.
    Does not support animated qr because no indicator of segments or their order
    """

    def add(self, segment, qr_type=QRType.PSBT__BASE64):
        if DecodeQR.is_base64(segment):
            self.complete = True
            self.data = segment
            self.collected_segments = 1
            return DecodeQRStatus.COMPLETE

        return DecodeQRStatus.INVALID

    def get_base64_data(self) -> str:
        return self.data

    def get_data(self):
        base64 = self.get_base64_data()
        if base64 != None:
            return a2b_base64(base64)

        return None


class Base43PsbtQrDecoder(BaseSingleFrameQrDecoder):
    """
    Decodes single frame base43 encoded qr image.
    Does not support animated qr because no indicator of segments or their order
    """

    def add(self, segment, qr_type=QRType.PSBT__BASE43):
        if DecodeQR.is_base43_psbt(segment):
            self.complete = True
            self.data = DecodeQR.base43_decode(segment)
            self.collected_segments = 1
            return DecodeQRStatus.COMPLETE

        return DecodeQRStatus.INVALID

    def get_data(self):
        return self.data
