import logging
import re

from enum import IntEnum
from pyzbar import pyzbar
from pyzbar.pyzbar import ZBarSymbol

from seedcash.helpers.ur2.ur_decoder import URDecoder
from seedcash.helpers.ur2.constants import MAX_UR_FRAME_LENGTH
from seedcash.models.qr_type import QRType

logger = logging.getLogger(__name__)


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

        if data is None:
            return DecodeQRStatus.FALSE

        return self.add_data(data)

    def _invalidate(self):
        self.complete = False
        self.qr_type = QRType.INVALID
        self.decoder = None
        return DecodeQRStatus.INVALID

    def add_data(self, data):
        if self.is_invalid:
            return DecodeQRStatus.INVALID
        if data is None:
            return DecodeQRStatus.FALSE
        if not isinstance(data, (str, bytes)) or len(data) > MAX_UR_FRAME_LENGTH:
            return self._invalidate()
        if self.complete:
            return DecodeQRStatus.COMPLETE
        if isinstance(data, bytes):
            try:
                data = data.decode("utf-8")
            except UnicodeDecodeError:
                return self._invalidate()

        qr_type = DecodeQR.detect_segment_type(data)
        if qr_type == QRType.INVALID:
            return self._invalidate()
        if self.qr_type is None:
            self.qr_type = qr_type
            if qr_type == QRType.PSBT__UR2:
                self.decoder = URDecoder() 
        elif self.qr_type != qr_type:
            return self._invalidate()
        
        try:
            qr_str = data.decode("utf-8") if isinstance(data, bytes) else data
            added = self.decoder.receive_part(qr_str)
            if not self.decoder.last_part_valid or self.decoder.is_failure():
                return self._invalidate()
            if self.decoder.is_success():
                self.complete = True
                return DecodeQRStatus.COMPLETE
            return DecodeQRStatus.PART_COMPLETE if added else DecodeQRStatus.PART_EXISTING
        except (ValueError, TypeError, UnicodeError):
            return self._invalidate()

    def get_psbt(self):
        if self.complete:
            return self.get_data_psbt()
        return None

    def get_data_psbt(self):
        if self.complete:
            if self.qr_type == QRType.PSBT__UR2:
                return self.decoder.result_message().cbor

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
        return self.qr_type == QRType.PSBT__UR2

    @staticmethod
    def extract_qr_data(image, is_binary: bool = False) -> str:
        if image is None:
            return None

        barcodes = pyzbar.decode(image, symbols=[ZBarSymbol.QRCODE], binary=is_binary)

        for barcode in barcodes:
            # Only pull and return the first barcode
            return barcode.data

    @staticmethod
    def detect_segment_type(s):
        if not isinstance(s, (str, bytes)) or len(s) > MAX_UR_FRAME_LENGTH:
            return QRType.INVALID

        if isinstance(s, bytes):
            try:
                s = s.decode("utf-8")
            except UnicodeDecodeError:
                return QRType.INVALID

        # PSBT
        if re.search("^UR:CRYPTO-PSBT/", s, re.IGNORECASE):
            return QRType.PSBT__UR2
            
        return QRType.INVALID

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

