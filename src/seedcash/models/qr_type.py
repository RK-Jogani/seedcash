class QRType:
    """
    Used with DecodeQR and EncodeQR to communicate qr encoding type
    """
    # PSBT types
    PSBT__BASE64 = "psbt__base64"
    PSBT__SPECTER = "psbt__specter"
    PSBT__BASE43 = "psbt__base43"
    PSBT__UR2 = "psbt__ur2"
    PSBT__BBQR = "psbt__bbqr"

    # Seed types
    SEED__SEEDQR = "seed__seedqr"
    SEED__COMPACTSEEDQR = "seed__compactseedqr"
    SEED__UR2 = "seed__ur2"
    SEED__MNEMONIC = "seed__mnemonic"
    SEED__FOUR_LETTER_MNEMONIC = "seed__four_letter_mnemonic"

    BYTES__UR = "bytes__ur"
    OUTPUT__UR = "output__ur"

    INVALID = "invalid"
