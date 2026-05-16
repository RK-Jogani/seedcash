import hashlib
import hmac
from seedcash.models.btc_functions import BitcoinFunctions as bf

hmac_hash = hmac.new(
    b"Bitcoin seed", bytes.fromhex("734409312cadeefc206303639a72e769"), hashlib.sha512
).digest()
xpriv, xpub, wallet_finderprint = bf.get_wallet_data(hmac_hash[:32], hmac_hash[32:])
print(xpriv)
print(xpub)
print(wallet_finderprint)
