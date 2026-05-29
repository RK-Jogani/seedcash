import os
from dataclasses import dataclass
from typing import Any, List


import logging

logger = logging.getLogger(__name__)


class SettingsConstants:
    # Basic settings options
    OPTION__ENABLED = "enabled"
    OPTION__DISABLED = "disabled"
    OPTION__PROMPT = "prompt"
    OPTIONS__ENABLED_DISABLED = [OPTION__ENABLED, OPTION__DISABLED]

    # Bitcoin Denomination
    BTC_DENOMINATION__BTC = "btc"
    BTC_DENOMINATION__SATS = "sats"
    BTC_DENOMINATION__THRESHOLD = "threshold"
    BTC_DENOMINATION__BTCSATSHYBRID = "btcsatshybrid"

    # User-facing selection options
    COORDINATOR__BLUE_WALLET = "bw"
    COORDINATOR__NUNCHUK = "nun"
    COORDINATOR__SPARROW = "spa"
    COORDINATOR__SPECTER_DESKTOP = "spd"
    COORDINATOR__KEEPER = "kpr"
    ALL_COORDINATORS = [
        (COORDINATOR__BLUE_WALLET, "BlueWallet"),
        (COORDINATOR__NUNCHUK, "Nunchuk"),
        (COORDINATOR__SPARROW, "Sparrow"),
        (COORDINATOR__SPECTER_DESKTOP, "Specter Desktop"),
        (COORDINATOR__KEEPER, "Keeper"),
    ]

    LOCALE__ENGLISH = "en"
    LOCALE__CHINESE = "zh_Hans_CN"
    LOCALE__SPANISH = "es"

    ALL_LOCALES = {
        LOCALE__ENGLISH: "English",
        LOCALE__CHINESE: "简体中文 (Chinese Simplified)",
        LOCALE__SPANISH: "Español (Spanish)",
        LOCALE__SPANISH: "Español (Spanish)",
    }

    # Do not wrap for translation. Present each language in its native form (i.e. either
    # using its native chars or how they write it in Latin chars; e.g. Spanish is listed
    # and sorted as "Español").
    # Sort fully-vetted languages first, then beta languages, then the "placeholders /
    # coming soon" languages.
    # Sort by native form when written in Latin chars, otherwise sort by English name.
    # Include English name in parens for languages that don't use Latin chars.
    # Include region/country in parens for specific dialects (e.g. "Português (Brasil)").
    # Note that dicts preserve insertion order as of Python 3.7.

    @classmethod
    def get_detected_languages(cls) -> list[tuple[str, str]]:
        """
        Return a list of tuples of language codes and their native names.

        Scans the filesystem to autodiscover which language codes are onboard.
        """
        # Will normally be the launch dir (where main.py is located)...
        cwd = os.getcwd()

        # ...except when running the tests which happens one dir higher
        if "src" not in cwd:
            cwd = os.path.join(cwd, "src")

        # Pre-load English since there's no "en" entry in the translations folder; also
        # it should always appear first in the list anyway.
        detected_languages = [
            (cls.LOCALE__ENGLISH, cls.ALL_LOCALES[cls.LOCALE__ENGLISH])
        ]

        locales_present = set()
        for root, dirs, files in os.walk(
            os.path.join(cwd, "seedcash", "resources", "seedcash-translations", "l10n")
        ):
            for file in [f for f in files if f.endswith(".mo")]:
                locales_present.add(root.split(f"l10n{ os.sep }")[1].split(os.sep)[0])

        for locale in cls.ALL_LOCALES.keys():
            if locale in locales_present:
                detected_languages.append((locale, cls.ALL_LOCALES[locale]))

        return detected_languages

    @classmethod
    def get_all_seed_protocols(cls) -> list[str]:
        """
        Returns a list of all available seed protocols.
        """
        protocols = [protocol[1] for protocol in cls.ALL_SEED_PROTOCOLS]
        logger.info(f"Available seed protocols: {protocols}")
        return protocols

    @classmethod
    def get_choose_words_options(cls, protocol: str) -> list[tuple[int, str]]:
        """
        Returns the available options for choosing the number of words based on the
        selected seed protocol.
        """
        if protocol == cls.SEED_PROTOCOL__BIP39:
            return [protocol[0] for protocol in cls.CHOOSE_BIP39_WORDS]
        elif protocol == cls.SEED_PROTOCOL__SLIP39:
            return [protocol[0] for protocol in cls.CHOOSE_SLIP39_WORDS]
        else:
            raise ValueError(f"Invalid seed protocol: {protocol}")

    CAMERA_ROTATION__0 = 0
    CAMERA_ROTATION__90 = 90
    CAMERA_ROTATION__180 = 180
    CAMERA_ROTATION__270 = 270
    ALL_CAMERA_ROTATIONS = [
        (CAMERA_ROTATION__0, ("Rotation 0°")),
        (CAMERA_ROTATION__90, ("Rotation 90°")),
        (CAMERA_ROTATION__180, ("Rotation 180°")),
        (CAMERA_ROTATION__270, ("Rotation 270°")),
    ]

    # Seed protocols
    SEED_PROTOCOL__BIP39 = "BIP39"
    SEED_PROTOCOL__SLIP39 = "SLIP39"

    ALL_SEED_PROTOCOLS = [
        (SEED_PROTOCOL__BIP39, "BIP39"),
        (SEED_PROTOCOL__SLIP39, "SLIP39"),
    ]

    # BIPP39 Choose Words
    CHOOSE_BIP39_WORDS = [
        (12, "12 Words"),
        (15, "15 Words"),
        (18, "18 Words"),
        (21, "21 Words"),
        (24, "24 Words"),
    ]

    CHOOSE_SLIP39_WORDS = [
        (20, "20 Words"),
        (33, "33 Words"),
    ]

    PERSISTENT_SETTINGS__SD_INSERTED__HELP_TEXT = "Store Settings on SD card"
    PERSISTENT_SETTINGS__SD_REMOVED__HELP_TEXT = "Insert SD card to enable"

    WORDLIST_LANGUAGE__ENGLISH = "en"
    WORDLIST_LANGUAGE__CHINESE = "zh_Hant_TW"
    WORDLIST_LANGUAGE__SPANISH = "es"

    ALL_WORDLIST_LANGUAGES = [
        (WORDLIST_LANGUAGE__ENGLISH, "English"),
    ]

    # Individual SettingsEntry attr_names
    # Note: attr_names are internal constants; do not wrap for translation
    SETTING__LOCALE = "locale"
    SETTING__WORDLIST_LANGUAGE = "wordlist_language"
    SETTING__PERSISTENT_SETTINGS = "persistent_settings"
    SETTING__COORDINATORS = "coordinators"

    SETTING__DISPLAY_CONFIGURATION = "display_config"
    SETTING__DISPLAY_COLOR_INVERTED = "color_inverted"

    SETTING__CAMERA_ROTATION = "camera_rotation"
    SETTING__SEED_PROTOCOL = "seed_protocol"
    SETTING__CHOOSE_WORDS = "choose_words"

    SETTING__DEBUG = "debug"

    # Hardware config settings
    DISPLAY_CONFIGURATION__ST7789__240x240 = (
        "st7789_240x240"  # default; original Waveshare 1.3" display hat
    )
    DISPLAY_CONFIGURATION__ST7789__320x240 = (
        "st7789_320x240"  # natively portrait dimensions; we apply a 90° rotation
    )
    DISPLAY_CONFIGURATION__ILI9341__320x240 = (
        "ili9341_320x240"  # natively portrait dimensions; we apply a 90° rotation
    )
    DISPLAY_CONFIGURATION__ILI9486__480x320 = (
        "ili9486_480x320"  # natively portrait dimensions; we apply a 90° rotation
    )
    ALL_DISPLAY_CONFIGURATIONS = [
        (DISPLAY_CONFIGURATION__ST7789__240x240, "st7789 240x240"),
        (DISPLAY_CONFIGURATION__ST7789__320x240, "st7789 320x240"),
        (DISPLAY_CONFIGURATION__ILI9341__320x240, "ili9341 320x240 (beta)"),
        # (DISPLAY_CONFIGURATION__ILI9486__320x480, "ili9486 480x320"),  # TODO: Enable when ili9486 driver performance is improved
    ]

    # Hidden settings
    SETTING__QR_BRIGHTNESS = "qr_background_color"

    # Structural constants
    # TODO: Not using these for display purposes yet (ever?)
    CATEGORY__SYSTEM = "system"
    CATEGORY__DISPLAY = "display"
    CATEGORY__WALLET = "wallet"
    CATEGORY__FEATURES = "features"

    VISIBILITY__GENERAL = "general"
    VISIBILITY__ADVANCED = "advanced"
    VISIBILITY__HARDWARE = "hardware"
    VISIBILITY__DEVELOPER = "developer"
    VISIBILITY__HIDDEN = (
        "hidden"  # For data-only (e.g. custom_derivation), not configurable by the user
    )

    # TODO: Is there really a difference between ENABLED and PROMPT?
    TYPE__ENABLED_DISABLED = "enabled_disabled"
    TYPE__ENABLED_DISABLED_PROMPT = "enabled_disabled_prompt"
    TYPE__ENABLED_DISABLED_PROMPT_REQUIRED = "enabled_disabled_prompt_required"
    TYPE__SELECT_1 = "select_1"
    TYPE__MULTISELECT = "multiselect"
    TYPE__FREE_ENTRY = "free_entry"

    ALL_ENABLED_DISABLED_TYPES = [
        TYPE__ENABLED_DISABLED,
        TYPE__ENABLED_DISABLED_PROMPT,
        TYPE__ENABLED_DISABLED_PROMPT_REQUIRED,
    ]

    # Electrum seed constants
    ELECTRUM_SEED_STANDARD = "01"
    ELECTRUM_SEED_SEGWIT = "100"
    ELECTRUM_SEED_2FA = "101"
    ELECTRUM_PBKDF2_ROUNDS = 2048

    # Label strings
    LABEL__BIP39_PASSPHRASE = "BIP-39 Passphrase"
    # TRANSLATOR_NOTE: Terminology used by Electrum seeds; equivalent to bip39 passphrase
    custom_extension = "Custom Extension"
    LABEL__CUSTOM_EXTENSION = custom_extension


@dataclass
class SettingsEntry:
    """
    Defines all the parameters for a single settings entry.

    * category: Mostly for organizational purposes when displaying options in the
        SettingsQR UI. Potentially an additional sub-level breakout in the menus
        on the device itself, too.

    * selection_options: May be specified as a List(Any) or List(tuple(Any, str)).
        The tuple form is to provide a human-readable display_name. Probably all
        entries should shift to using the tuple form.
    """

    # TODO: Handle multi-language `display_name` and `help_text`
    attr_name: str
    abbreviated_name: str = None
    visibility: str = SettingsConstants.VISIBILITY__GENERAL
    type: str = SettingsConstants.TYPE__ENABLED_DISABLED
    help_text: str = None
    selection_options: list[tuple[str | int], str] = None
    default_value: Any = None

    def __post_init__(self):
        if self.type == SettingsConstants.TYPE__ENABLED_DISABLED:
            self.selection_options = SettingsConstants.OPTIONS__ENABLED_DISABLED

        elif self.type == SettingsConstants.TYPE__ENABLED_DISABLED_PROMPT:
            self.selection_options = SettingsConstants.OPTIONS__ENABLED_DISABLED_PROMPT

        elif self.type == SettingsConstants.TYPE__ENABLED_DISABLED_PROMPT_REQUIRED:
            self.selection_options = SettingsConstants.ALL_OPTIONS

        # Account for List[tuple] and tuple formats as default_value
        if type(self.default_value) == list and type(self.default_value[0]) == tuple:
            self.default_value = [v[0] for v in self.default_value]
        elif type(self.default_value) == tuple:
            self.default_value = self.default_value[0]

    @property
    def selection_options_display_names(self) -> List[str]:
        if type(self.selection_options[0]) == tuple:
            return [v[1] for v in self.selection_options]
        else:
            # Always return a copy so the original can't be altered
            return list(self.selection_options)

    def get_selection_option_value(self, i: int):
        """Returns the value of the selection option at index `i`"""
        value = self.selection_options[i]
        if type(value) == tuple:
            value = value[0]
        return value

    def get_selection_option_display_name_by_value(self, value) -> str:
        for option in self.selection_options:
            if type(option) == tuple:
                option_value = option[0]
                display_name = option[1]
            else:
                option_value = option
                display_name = option
            if option_value == value:
                return display_name

    def get_selection_option_value_by_display_name(self, display_name: str):
        for option in self.selection_options:
            if type(option) == tuple:
                option_value = option[0]
                option_display_name = option[1]
            else:
                option_value = option
                option_display_name = option
            if option_display_name == display_name:
                return option_value

    def to_dict(self) -> dict:
        if self.selection_options:
            selection_options = []
            for option in self.selection_options:
                if type(option) == tuple:
                    value = option[0]
                    display_name = option[1]
                else:
                    display_name = option
                    value = option
                selection_options.append({"display_name": display_name, "value": value})
        else:
            selection_options = None

        return {
            "category": self.category,
            "attr_name": self.attr_name,
            "abbreviated_name": self.abbreviated_name,
            "display_name": self.display_name,
            "visibility": self.visibility,
            "type": self.type,
            "help_text": self.help_text,
            "selection_options": selection_options,
            "default_value": self.default_value,
        }


class SettingsDefinition:
    """
    Master list of all settings, their possible options, their defaults, on-device
    display strings, and enriched SettingsQR UI options.

    Used to auto-build the Settings UI menuing with no repetitive boilerplate code.

    Defines the on-disk persistent storage structure and can read that format back
    and validate the values.

    Used to generate a master json file that documents all these params which can
    then be read in by the SettingsQR UI to auto-generate the necessary html inputs.
    """

    # Increment if there are any breaking changes; write migrations to bridge from
    # incompatible prior versions.
    version: int = 1

    settings_entries: List[SettingsEntry] = [
        # Locale Settings
        SettingsEntry(
            attr_name=SettingsConstants.SETTING__LOCALE,
            abbreviated_name="locale",
            type=SettingsConstants.TYPE__SELECT_1,
            selection_options=SettingsConstants.get_detected_languages(),
            default_value=SettingsConstants.LOCALE__ENGLISH,
            help_text="Language of the user interface",
        ),
        # Language Settings
        SettingsEntry(
            attr_name=SettingsConstants.SETTING__WORDLIST_LANGUAGE,
            type=SettingsConstants.TYPE__SELECT_1,
            selection_options=SettingsConstants.ALL_WORDLIST_LANGUAGES,
            default_value=SettingsConstants.WORDLIST_LANGUAGE__ENGLISH,
        ),
        # Camera Settings
        SettingsEntry(
            attr_name=SettingsConstants.SETTING__CAMERA_ROTATION,
            type=SettingsConstants.TYPE__SELECT_1,
            selection_options=SettingsConstants.ALL_CAMERA_ROTATIONS,
            default_value=SettingsConstants.CAMERA_ROTATION__270,
        ),
        # Seed Protocol Settings
        SettingsEntry(
            attr_name=SettingsConstants.SETTING__SEED_PROTOCOL,
            type=SettingsConstants.TYPE__SELECT_1,
            selection_options=SettingsConstants.ALL_SEED_PROTOCOLS,
            default_value=SettingsConstants.SEED_PROTOCOL__BIP39,
        ),
        # Choose Words Settings
        SettingsEntry(
            attr_name=SettingsConstants.SETTING__CHOOSE_WORDS,
            type=SettingsConstants.TYPE__SELECT_1,
            default_value=SettingsConstants.CHOOSE_BIP39_WORDS,
        ),
        # Hardware config
        SettingsEntry(
            attr_name=SettingsConstants.SETTING__COORDINATORS,
            type=SettingsConstants.TYPE__SELECT_1,
            selection_options=SettingsConstants.ALL_DISPLAY_CONFIGURATIONS,
            default_value=SettingsConstants.DISPLAY_CONFIGURATION__ST7789__240x240,
        ),
        # Display Settings
        SettingsEntry(
            attr_name=SettingsConstants.SETTING__DISPLAY_CONFIGURATION,
            abbreviated_name="display_config",
            type=SettingsConstants.TYPE__SELECT_1,
            selection_options=SettingsConstants.ALL_DISPLAY_CONFIGURATIONS,
            default_value=SettingsConstants.DISPLAY_CONFIGURATION__ST7789__240x240,
            help_text="Display configuration",
        ),
        SettingsEntry(
            attr_name=SettingsConstants.SETTING__DISPLAY_COLOR_INVERTED,
            abbreviated_name="color_inverted",
            type=SettingsConstants.TYPE__ENABLED_DISABLED,
        ),
        SettingsEntry(
            attr_name=SettingsConstants.SETTING__QR_BRIGHTNESS,
            type=SettingsConstants.TYPE__FREE_ENTRY,
            default_value=255,
            visibility=SettingsConstants.VISIBILITY__GENERAL,
        ),
    ]

    @classmethod
    def get_settings_entries(
        cls, visibility: str = SettingsConstants.VISIBILITY__GENERAL
    ) -> List[SettingsEntry]:
        entries = []
        for entry in cls.settings_entries:
            if entry.visibility == visibility:
                entries.append(entry)
        return entries

    @classmethod
    def get_settings_entry(cls, attr_name) -> SettingsEntry:
        for entry in cls.settings_entries:
            if entry.attr_name == attr_name:
                return entry

    @classmethod
    def get_settings_entry_by_abbreviated_name(
        cls, abbreviated_name: str
    ) -> SettingsEntry:
        for entry in cls.settings_entries:
            if abbreviated_name in [entry.abbreviated_name, entry.attr_name]:
                return entry

    @classmethod
    def get_defaults(cls) -> dict:
        as_dict = {}
        for entry in SettingsDefinition.settings_entries:
            if type(entry.default_value) == list:
                # Must copy the default_value list, otherwise we'll inadvertently change
                # defaults when updating these attrs
                as_dict[entry.attr_name] = list(entry.default_value)
            else:
                as_dict[entry.attr_name] = entry.default_value
        return as_dict

    @classmethod
    def to_dict(cls) -> dict:
        output = {
            "settings_entries": [],
        }
        for settings_entry in cls.settings_entries:
            output["settings_entries"].append(settings_entry.to_dict())

        return output


if __name__ == "__main__":
    import json
    import os

    hostname = os.uname()[1]

    try:
        output_file = "/mnt/microsd/settings_definition.json"
    except FileNotFoundError:
        raise FileNotFoundError(
            "Unable to write settings_definition.json to /mnt/microsd. "
            "Please ensure the SD card is inserted and mounted."
        )
    finally:
        output_file = "settings_definition.json"

    with open(output_file, "w") as json_file:
        json.dump(SettingsDefinition.to_dict(), json_file, indent=4)
