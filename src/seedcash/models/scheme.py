from typing import Dict, List, Tuple

from seedcash.helpers.shamir_mnemonic.share import Share, ShareCommonParameters
from seedcash.helpers.shamir_mnemonic.shamir import (
    EncryptedMasterSecret,
    ShareGroup,
    _random_identifier,
    recover_ems,
    split_ems,
)
from seedcash.models.wallet import Wallet
from seedcash.models.slip39 import Slip39 as sp

import logging

logger = logging.getLogger(__name__)


class InvalidSchemeException(Exception):
    pass


class InvalidGroupException(Exception):
    pass


class InvalidShareException(Exception):
    pass


class SchemeParameters:
    """
    Represents the parameters of a Shamir Secret Sharing scheme.
    """

    def __init__(self, bits: str = None):
        if bits is None:
            raise InvalidSchemeException(
                "Either bits or groups must be provided to initialize the scheme."
            )
        self._group_threshold = 1
        self._groups: List[Tuple[int, int]] = [None]
        self._bits: bytes = b""

        self.set_bits(bits)

    @property
    def bits_str(self) -> str:
        if not self._bits:
            raise InvalidSchemeException("Bits have not been initialized")
        return bin(int.from_bytes(self._bits, byteorder="big"))[2:].zfill(
            len(self._bits) * 8
        )

    @property
    def bits(self) -> bytes:
        if not self._bits:
            raise InvalidSchemeException("Bits have not been initialized")
        return self._bits


    @property
    def group_threshold(self) -> int:
        if not self._group_threshold:
            raise InvalidSchemeException("Group threshold has not been initialized")
        return self._group_threshold

    @property
    def groups(self) -> List[Tuple[int, int]]:
        if not self._groups:
            raise InvalidSchemeException("Groups have not been initialized")
        return self._groups

    @property
    def groups_length(self) -> int:
        return len(self.groups)

    def set_bits(self, bits: str):
        if not bits:
            raise ValueError("Bits cannot be empty.")

        if len(bits) not in [128, 256]:
            raise ValueError("Scheme Parameters must initialize with 128 or 256.")
        # Convert str to bytes
        self._bits = int(bits, 2).to_bytes((len(bits) + 7) // 8, byteorder="big")

    def set_groups_length(self, length: int):
        """
        Set the number of groups in the scheme.
        """
        if length < 1:
            raise ValueError("Number of groups must be at least 1.")
        self._groups = [None] * length

    def set_group_threshold(self, threshold: int):
        if threshold < 1:
            raise ValueError("Group threshold must be at least 1.")
        self._group_threshold = threshold

    def get_group_at(self, index: int) -> tuple:
        if index >= len(self.groups):
            raise IndexError("Index out of range for groups")
        return self.groups[index]

    def update_groups(self, index: int, group: tuple):

        if group is None:
            self._groups[index] = None
            return

        if group[0] > group[1]:
            raise ValueError(
                "Invalid group: threshold cannot be greater than total shares"
            )

        if index > len(self.groups):
            raise IndexError("Index is out of group change")
        self._groups[index] = group

    def discard_groups(self):
        self._groups = [None]
        self._group_threshold = 1

    def scheme_is_complete(self) -> bool:
        """
        Checks if the scheme is complete, i.e., all groups are set.
        """
        return all(group is not None for group in self.groups)

    def return_params(self) -> Tuple[bytes, int, List[Tuple[int, int]]]:
        """
        Returns the group threshold and the list of groups.
        """
        # returns the bits, group threshold, and groups
        return self.bits, self.group_threshold, self.groups

    def discard_parameters(self):
        """
        Discards the current scheme parameters and resets them.
        """
        self._bits = b""
        self._group_threshold = 1
        self._groups = [None]
        import gc
        gc.collect()


class Scheme:
    
    def __init__(
        self, scheme_parameters: SchemeParameters = None
    ):

        self._groups: Dict[int, ShareGroup] = {}
        self._passphrase: bytes = b""
        self._common_params: ShareCommonParameters = None
        self._master_secret: bytearray = None

        self._wallet: Wallet = None
        self._scheme_parameters: SchemeParameters = scheme_parameters

    @property
    def master_secret(self) -> bytearray:
        if not self._master_secret:
            raise InvalidSchemeException("Master secret has not been initialized")
        return self._master_secret
    
    @property
    def wallet(self):
        if not self._wallet:
            raise ValueError("The wallet not initialized for scheme")
        return self._wallet

    def set_wallet(self, wallet: Wallet):
        if not isinstance(wallet, Wallet):
            raise ValueError("Provided wallet is not a valid Wallet instance")
        if self._wallet is not None:
            self._wallet.discard_wallet()
        self._wallet = wallet

    @property
    def passphrase(self) -> bytes:
        if not self._passphrase:
            return b""
        return self._passphrase

    def set_passphrase(self, passphrase: str):
        passphrase = passphrase.encode("utf-8")
        if not all(32 <= c <= 126 for c in passphrase):
            raise ValueError("The passphrase must contain only printable ASCII characters (code points 32-126).")
        self._passphrase = passphrase

    @property
    def scheme_parameters(self):
        if not self._scheme_parameters:
            raise InvalidSchemeException("Scheme parameters have not been initialized")
        return self._scheme_parameters

    @property
    def common_params(self) -> ShareCommonParameters:
        if not self._common_params:
            raise InvalidSchemeException("Common parameters have not been initialized")
        return self._common_params
    
    def set_common_params(self, common_params: ShareCommonParameters):
        if not isinstance(common_params, ShareCommonParameters):
            raise ValueError("common_params must be a ShareCommonParameters instance.")
        self._common_params = common_params
    
    @property
    def groups(self) -> Dict[int, ShareGroup]:
        if not self._groups:
            raise InvalidSchemeException("Groups have not been initialized")
        return self._groups

    def add_share_to_group(self, share: Share):
        """
        Adds a share to the appropriate group based on its group index.
        If the group does not exist, it creates a new group.
        """
        if not isinstance(share, Share):
            raise ValueError("share must be a Share instance.")

        if self._common_params is None:
            self.set_common_params(share.common_parameters())
            
        if share.common_parameters() != self.common_params:
            raise InvalidShareException("Share does not match scheme")

        group = self._groups.setdefault(share.group_index, ShareGroup())
        group.add(share)

    def set_master_secret(self, master_secret: bytearray):
        if not isinstance(master_secret, (bytearray)):
            raise ValueError("master_secret must be bytes or bytearray.")
        self._master_secret = master_secret

    def get_group_indices(self) -> List[int]:
        """
        Returns the indices of all groups in the scheme.
        """
        return list(self.groups.keys())

    def get_shares_indices_of_group(self, group_index: int) -> List[int]:
        """
        Returns the indices of shares in a specific group.
        """
        if group_index not in self.groups:
            return None

        return sorted([share.index for share in self.groups[group_index].shares])

    def get_mnemonics_share_of_group(
        self, share_index: int, group_index: int
    ) -> List[str]:
        """
        Returns the mnemonic of a specific share in a group.
        """
        if group_index not in self.groups:
            return None

        group = self.groups[group_index]
        for share in group.shares:
            if share.index == share_index:
                return share.mnemonic().split()

        return None

    def get_scheme_info(self):
        """
        Returns the common parameters of the Shamir scheme.
        If no shares are entered, returns None.
        """
        total_groups = self.common_params.group_count
        group_threshold = self.common_params.group_threshold
        processed_groups = self.groups.__len__()

        # completed_groups
        self.completed_groups = len(
            [group for group in self.groups.values() if group.is_complete()]
        )

        # processed, threshold, total
        return processed_groups, group_threshold, total_groups, self.completed_groups

    def get_group_info(self, group_index: int):
        """
        Returns information about a specific group.
        If the group does not exist, returns None.
        """
        if group_index not in self.groups:
            return None

        group = self.groups[group_index]
        shares_count = group.__len__()
        member_threshold = group.member_threshold()

        return shares_count, member_threshold

    def discard_scheme(self):
        """
        Discards the current scheme and resets the manager.
        """
        
        if self._scheme_parameters is not None:
            self._scheme_parameters.discard_parameters()
            self._scheme_parameters = None
            
        if self._wallet is not None:
            self._wallet.discard_wallet()
            self._wallet = None

        self.clean_secret()

    def clean_secret(self):
        if self._master_secret is not None:
            self._master_secret[:] = b"\x00" * len(self._master_secret)
        self._master_secret = None
        self._groups.clear()
        self._common_params = None
        self._passphrase: bytes = b""
        self._passphrase = None

        import gc
        gc.collect()
        

    def discard_group(self, group_id: int):
        """
        Discards a specific group by its ID.
        """
        if group_id in self.groups:
            del self._groups[group_id]

    def discard_share_of_group(self, share_index: int, group_id: int):
        """
        Discards a specific share in a group.
        """
        if group_id in self.groups:
            group = self.groups[group_id]
            if group.__len__() == 1:
                del self._groups[group_id]

            for share in group.shares:
                if share.index == share_index:
                    group.shares.remove(share)
                    return

    def add_share(self, share_list: List[str]) -> None:

        share_str = " ".join(share_list)
        self.add_share_to_group(Share.from_mnemonic(share_str))

    def recover_secret(self) -> bytearray:
        try:
            encrypted_master_secret = recover_ems(self.groups)
            self.set_master_secret(bytearray(encrypted_master_secret.decrypt(self.passphrase)))
        except Exception as e:
            logger.error("Failed to recover master secret")
            return None

    def generate_mnemonics(
        self,
        extendable: bool = True,
        iteration_exponent: int = 1,
    ) -> Dict[int, ShareGroup]:

        if self.scheme_parameters.bits is None:
            raise InvalidSchemeException("Scheme parameters must be set before generating mnemonics.")
        
        identifier = _random_identifier()
        encrypted_master_secret = EncryptedMasterSecret.from_master_secret(
            self.scheme_parameters.bits,
            self.passphrase,
            identifier,
            extendable,
            iteration_exponent,
        )
        grouped_shares = split_ems(
            self.scheme_parameters.group_threshold, 
            self.scheme_parameters.groups,
            encrypted_master_secret)
        
        groups_dict = {}

        for group_index, group_list in enumerate(grouped_shares):
            group = groups_dict.setdefault(group_index, ShareGroup())
            for share in group_list:
                group.add(share)

        self._groups = groups_dict

    
    def generate_wallet(self) -> Wallet:
        if self._scheme_parameters:
            self.generate_mnemonics()
        
        self.recover_secret()
        
        private_master_key, private_master_code = sp.slip39_protocol(self.master_secret)

        self.set_wallet(Wallet(private_master_key, private_master_code))

        return self.wallet

    def is_single_level(self) -> bool:
        """
        Checks if the current scheme is a single-level scheme.
        """
        return (
            self.common_params.group_count == 1
            and self.common_params.group_threshold == 1
        )

    def is_complete(self) -> bool:
        """
        Checks if the scheme is complete, i.e., threshold number of groups are completed
        """
        complete_groups = [
            group for group in self.groups.values() if group.is_complete()
        ]

        if len(complete_groups) == self.common_params.group_threshold:
            return True

        return False
