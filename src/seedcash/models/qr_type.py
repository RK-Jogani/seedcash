class QRType:
    """
    Used with DecodeQR and EncodeQR to communicate qr encoding type
    """

    PSBT__BASE64 = "psbt__base64"
    PSBT__SPECTER = "psbt__specter"
    PSBT__BASE43 = "psbt__base43"
    PSBT__UR2 = "psbt__ur2"
    PSBT__BBQR = "psbt__bbqr"

    BYTES__UR = "bytes__ur"
    OUTPUT__UR = "output__ur"

    INVALID = "invalid"
