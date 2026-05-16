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
from seedcash.models.btc_functions import BitcoinFunctions as bf

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
        self.group_threshold = 1
        self.groups: List[Tuple[int, int]] = [None]
        self.bits: bytes = b""

        self.set_bits(bits)

    @property
    def _bits(self) -> str:
        if not self.bits:
            raise InvalidSchemeException("Bits have not been initialized")
        return bin(int.from_bytes(self.bits, byteorder="big"))[2:].zfill(
            len(self.bits) * 8
        )

    @property
    def _group_threshold(self) -> int:
        return self.group_threshold

    @property
    def _groups(self) -> List[Tuple[int, int]]:
        return self.groups

    @property
    def _groups_length(self) -> int:
        return len(self.groups)

    def set_bits(self, bits: str):
        if not bits:
            raise ValueError("Bits cannot be empty.")

        if len(bits) not in [128, 256]:
            raise ValueError("Scheme Parameters must initialize with 128 or 256.")
        # Convert str to bytes
        self.bits = int(bits, 2).to_bytes((len(bits) + 7) // 8, byteorder="big")

    def set_groups_length(self, length: int):
        """
        Set the number of groups in the scheme.
        """
        if length < 1:
            raise ValueError("Number of groups must be at least 1.")
        self.groups = [None] * length

    def set_group_threshold(self, threshold: int):
        """
        Set the group threshold for the scheme.
        """
        if threshold < 1:
            raise ValueError("Group threshold must be at least 1.")
        self.group_threshold = threshold

    def get_group_at(self, index: int) -> tuple:
        if index >= len(self.groups):
            raise IndexError("Index out of range for groups")
        return self.groups[index]

    def update_groups(self, index: int, group: tuple):

        if group is None:
            self.groups[index] = None
            return

        if group[0] > group[1]:
            raise ValueError(
                "Invalid group: threshold cannot be greater than total shares"
            )

        if index > len(self.groups):
            raise IndexError("Index is out of group change")
        self.groups[index] = group

    def discard_groups(self):
        self.groups = [None]
        self.group_threshold = 1

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


class Scheme:
    """
    Manages Shamir Secret Sharing scheme with progressive share entry and analysis.
    """

    def __init__(
        self, mnemonics: List[str] = None, scheme_parameters: SchemeParameters = None
    ):

        if mnemonics is None and scheme_parameters is None:
            raise InvalidSchemeException(
                "Either mnemonics or scheme_parameters must be provided."
            )
        # variables for loading the scheme
        self.scheme_parameters: SchemeParameters = scheme_parameters
        self.groups: Dict[int, ShareGroup] = {}
        self.passphrase: bytes = b""
        self.common_params: List[ShareCommonParameters] = []
        self.wallet: Wallet = None
        self.master_secret: str = None

        if mnemonics:
            self.add_share(mnemonics)

        if scheme_parameters:
            self.master_secret = self.scheme_parameters._bits

    @property
    def _wallet(self):
        if not self.wallet:
            raise ValueError("The wallet not initialized for scheme")

        return self.wallet

    def set_master_secret(self, master_secret: bytes):
        """
        Set the master secret for the scheme.
        """

        if not master_secret:
            raise InvalidSchemeException("Master secret cannot be empty.")

        self.master_secret = bin(int.from_bytes(master_secret, byteorder="big"))[
            2:
        ].zfill(len(master_secret) * 8)

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
        total_groups = self.common_params[0].group_count
        group_threshold = self.common_params[0].group_threshold
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

        # processed, threshold
        return shares_count, member_threshold

    def discard_scheme(self):
        """
        Discards the current scheme and resets the manager.
        """
        self.groups.clear()
        self.common_params.clear()
        self.master_secret = None
        print("Scheme discarded. All data reset.")

    def discard_group(self, group_id: int):
        """
        Discards a specific group by its ID.
        """
        if group_id in self.groups:
            del self.groups[group_id]
            print(f"Group {group_id} discarded.")
        else:
            print(f"Group {group_id} does not exist.")

    def discard_share_of_group(self, share_index: int, group_id: int):
        """
        Discards a specific share in a group.
        """
        if group_id in self.groups:
            group = self.groups[group_id]
            if group.__len__() == 1:
                del self.groups[group_id]

            for share in group.shares:
                if share.index == share_index:
                    group.shares.remove(share)
                    print(f"Share {share_index} in Group {group_id} discarded.")
                    return
            print(f"Share {share_index} not found in Group {group_id}.")
        else:
            print(f"Group {group_id} does not exist.")

    def add_share(self, share_list: List[str]) -> Dict[str, str]:

        share_str = " ".join(share_list)  # Normalize spaces
        share = Share.from_mnemonic(share_str)

        if len(self.groups) == 0:
            # if no groups yet, initialize a group with the share
            self.common_params.append(share.common_parameters())
            group = self.groups.setdefault(share.group_index, ShareGroup())
            group.add(share)

        else:
            if share.common_parameters() not in self.common_params:
                raise InvalidShareException("Share does not match scheme")
            else:
                # Add to existing group
                group = self.groups.setdefault(share.group_index, ShareGroup())
                group.add(share)
                print(f"Share {share.index} added to Group {share.group_index}.")

        return {"status": "added", "message": "Mnemonic added successfully"}

    def recover_secret(self) -> bytes:
        try:
            encrypted_master_secret = recover_ems(self.groups)
            self.set_master_secret(encrypted_master_secret.decrypt(self.passphrase))
        except Exception as e:
            logger.error("Failed to recover master secret:", e)
            return None

    def generate_mnemonics(
        self,
        extendable: bool = True,
        iteration_exponent: int = 1,
    ) -> Dict[int, ShareGroup]:
        """
        Split a master secret into mnemonic shares using Shamir's secret sharing scheme.

        The supplied Master Secret is encrypted by the passphrase (empty passphrase is used
        if none is provided) and split into a set of mnemonic shares.

        This is the user-friendly method to back up a pre-existing secret with the Shamir
        scheme, optionally protected by a passphrase.

        :param group_threshold: The number of groups required to reconstruct the master secret.
        :param groups: A list of (member_threshold, member_count) pairs for each group, where member_count
            is the number of shares to generate for the group and member_threshold is the number of members required to
            reconstruct the group secret.
        :param master_secret: The master secret to split.
        :param passphrase: The passphrase used to encrypt the master secret.
        :param int iteration_exponent: The encryption iteration exponent.
        :return: List of groups mnemonics.
        """
        if not self.scheme_parameters:
            raise InvalidSchemeException("Scheme parameters are not complete.")

        master_secret = self.scheme_parameters.bits
        groups = self.scheme_parameters.groups
        group_threshold = self.scheme_parameters.group_threshold

        if master_secret is None:
            raise InvalidSchemeException("Master secret is not set.")

        if not groups:
            raise InvalidSchemeException("No groups have been set.")

        if not group_threshold:
            raise InvalidSchemeException("Group threshold is not set.")

        logger.info("Passphrase in generate scheme:", self.passphrase)
        if not all(32 <= c <= 126 for c in self.passphrase):
            raise ValueError(
                "The passphrase must contain only printable ASCII characters (code points 32-126)."
            )

        identifier = _random_identifier()
        encrypted_master_secret = EncryptedMasterSecret.from_master_secret(
            master_secret,
            self.passphrase,
            identifier,
            extendable,
            iteration_exponent,
        )
        grouped_shares = split_ems(group_threshold, groups, encrypted_master_secret)
        groups_dict = {}

        for group_index, group_list in enumerate(grouped_shares):
            group = groups_dict.setdefault(group_index, ShareGroup())
            for share in group_list:
                group.add(share)

        self.groups = groups_dict

    def set_passphrase(self, passphrase: str):
        """
        Sets the passphrase for encrypting/decrypting the master secret.
        """
        self.passphrase = passphrase.encode("utf-8")

    def generate_wallet(self) -> Wallet:
        """
        Generates a wallet from the recovered master secret.
        """
        self.recover_secret()

        if not self.master_secret:
            raise InvalidSchemeException("Master secret is not set.")

        private_master_key, private_master_code = bf.slip39_protocol(self.master_secret)

        self.wallet = Wallet(private_master_key, private_master_code)

        return self.wallet

    def is_single_level(self) -> bool:
        """
        Checks if the current scheme is a single-level scheme.
        """
        return (
            self.common_params[0].group_count == 1
            and self.common_params[0].group_threshold == 1
        )

    def is_complete(self) -> bool:
        """
        Checks if the scheme is complete, i.e., threshold number of groups are completed
        """
        complete_groups = [
            group for group in self.groups.values() if group.is_complete()
        ]

        if len(complete_groups) == self.common_params[0].group_threshold:
            return True

        return False
