import os
from dataclasses import dataclass
from typing import Any, List

import logging

logger = logging.getLogger(__name__)


class SettingsConstants:
    # Basic defaults
    OPTION__ENABLED = "E"
    OPTION__DISABLED = "D"
    OPTION__PROMPT = "P"
    OPTION__REQUIRED = "R"
    OPTIONS__ENABLED_DISABLED = [
        (OPTION__ENABLED, ("Enabled")),
        (OPTION__DISABLED, ("Disabled")),
    ]
    OPTIONS__ONLY_DISABLED = [
        (OPTION__DISABLED, ("Disabled")),
    ]
    OPTIONS__PROMPT_REQUIRED_DISABLED = [
        (OPTION__PROMPT, ("Prompt")),
        (OPTION__REQUIRED, ("Required")),
        (OPTION__DISABLED, ("Disabled")),
    ]
    OPTIONS__ENABLED_DISABLED_REQUIRED = OPTIONS__ENABLED_DISABLED + [
        (OPTION__REQUIRED, ("Required")),
    ]
    OPTIONS__ENABLED_DISABLED_PROMPT = OPTIONS__ENABLED_DISABLED + [
        (OPTION__PROMPT, ("Prompt")),
    ]
    ALL_OPTIONS = OPTIONS__ENABLED_DISABLED_PROMPT + [
        (OPTION__REQUIRED, ("Required")),
    ]

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

    # Over-specifying current and possible future locales to reduce/eliminate main repo
    # changes when adding/testing new languages.
    LOCALE__ARABIC = "ar"
    LOCALE__BENGALI = "bn"
    LOCALE__BULGARIAN = "bg"
    LOCALE__CATALAN = "ca"
    LOCALE__CHINESE_SIMPLIFIED = "zh_Hans_CN"
    LOCALE__CHINESE_TRADITIONAL = "zh_Hant_TW"
    LOCALE__CROATIAN = "hr"
    LOCALE__CZECH = "cs"
    LOCALE__DANISH = "da"
    LOCALE__DUTCH = "nl"
    LOCALE__EGYPTIAN = "ar_EG"
    LOCALE__ENGLISH = "en"
    LOCALE__ESTONIAN = "et"
    LOCALE__FINNISH = "fi"
    LOCALE__FRENCH = "fr"
    LOCALE__GAELIC = "gd"
    LOCALE__GERMAN = "de"
    LOCALE__GREEK = "el"
    LOCALE__GUJARATI = "gu"
    LOCALE__HAUSA = "ha"
    LOCALE__HEBREW = "he"
    LOCALE__HINDI = "hi"
    LOCALE__HUNGARIAN = "hu"
    LOCALE__INDONESIAN = "id"
    LOCALE__ITALIAN = "it"
    LOCALE__JAPANESE = "ja"
    LOCALE__JAVANESE = "jv"
    LOCALE__KOREAN = "ko"
    LOCALE__LAO = "lo"
    LOCALE__LATVIAN = "lv"
    LOCALE__LITHUANIAN = "lt"
    LOCALE__MALAY = "ms"
    LOCALE__MALTESE = "mt"
    LOCALE__MARATHI = "mr"
    LOCALE__NORWEGIAN = "no"
    LOCALE__PERSIAN = "fa"
    LOCALE__POLISH = "pl"
    LOCALE__PORTUGUESE_BR = "pt_BR"
    LOCALE__PORTUGUESE_PT = "pt_PT"
    LOCALE__PUNJABI = "pa"
    LOCALE__ROMANIAN = "ro"
    LOCALE__RUSSIAN = "ru"
    LOCALE__SLOVAK = "sk"
    LOCALE__SLOVENIAN = "sl"
    LOCALE__SPANISH = "es"
    LOCALE__SWEDISH = "sv"
    LOCALE__TAGALOG = "tl"
    LOCALE__TAMIL = "ta"
    LOCALE__TELUGU = "te"
    LOCALE__THAI = "th"
    LOCALE__TURKISH = "tr"
    LOCALE__UKRANIAN = "uk"
    LOCALE__URDU = "ur"
    LOCALE__VIETNAMESE = "vi"

    # Do not wrap for translation. Present each language in its native form (i.e. either
    # using its native chars or how they write it in Latin chars; e.g. Spanish is listed
    # and sorted as "Español").
    # Sort fully-vetted languages first, then beta languages, then the "placeholders /
    # coming soon" languages.
    # Sort by native form when written in Latin chars, otherwise sort by English name.
    # Include English name in parens for languages that don't use Latin chars.
    # Include region/country in parens for specific dialects (e.g. "Português (Brasil)").
    # Note that dicts preserve insertion order as of Python 3.7.
    ALL_LOCALES = {
        # --------- Fully supported languages -------------------------------------------
        LOCALE__CATALAN: "Català",
        LOCALE__GERMAN: "Deutsch",
        LOCALE__ENGLISH: "English",
        LOCALE__SPANISH: "Español",
        LOCALE__FRENCH: "Français",
        LOCALE__ITALIAN: "Italiano",
        LOCALE__DUTCH: "Nederlands",
        # --------- Beta languages ------------------------------------------------------
        LOCALE__CHINESE_SIMPLIFIED: "(beta) 简体中文 (Chinese Simplified)",
        LOCALE__JAPANESE: "(beta) 日本語 (Japanese)",
        LOCALE__KOREAN: "(beta) 한국어 (Korean)",
        # --------- Placeholders / Coming soon ------------------------------------------
        # Commented out options require explicit additional font support.
        # -------------------------------------------------------------------------------
        # LOCALE__ARABIC: "العربية (Arabic)",
        # LOCALE__BENGALI: "বাংলা (Bengali)",
        LOCALE__BULGARIAN: "български (Bulgarian)",  # OpenSans includes cyrillic chars
        LOCALE__CZECH: "čeština",
        # LOCALE__CHINESE_TRADITIONAL: "繁體中文 (Chinese Traditional)",
        LOCALE__DANISH: "Dansk",
        LOCALE__ESTONIAN: "Eesti",
        # LOCALE__EGYPTIAN: "مصرى (Egyptian)",
        LOCALE__GAELIC: "Gaeilge",
        LOCALE__GREEK: "Ελληνικά (Greek)",  # OpenSans includes Greek chars
        # LOCALE__GUJARATI: "ગુજરાતી (Gujarati)",
        LOCALE__HAUSA: "Hausa",
        # LOCALE__HEBREW: "עברית (Hebrew)",
        # LOCALE__HINDI: "हिन्दी (Hindi)",
        LOCALE__CROATIAN: "Hrvatski",
        LOCALE__INDONESIAN: "Indonesia",
        LOCALE__JAVANESE: "Jawa (Javanese)",
        # LOCALE__LAO: "ລາວ (Lao)",
        LOCALE__LATVIAN: "Latviešu",
        LOCALE__LITHUANIAN: "Lietuvių",
        LOCALE__HUNGARIAN: "Magyar",
        LOCALE__MALAY: "Melayu",
        LOCALE__MALTESE: "Malti",
        # LOCALE__MARATHI: "मराठी (Marathi)",
        LOCALE__NORWEGIAN: "Norsk",
        # LOCALE__PERSIAN: "فارسی (Persian)",
        LOCALE__POLISH: "Polski",
        LOCALE__PORTUGUESE_BR: "Português (Brasil)",
        LOCALE__PORTUGUESE_PT: "Português (Portugal)",
        # LOCALE__PUNJABI: "ਪੰਜਾਬੀ (Punjabi)",
        LOCALE__ROMANIAN: "Română",
        LOCALE__RUSSIAN: "русский (Russian)",  # OpenSans includes cyrillic chars
        LOCALE__SLOVAK: "Slovenčina",
        LOCALE__SLOVENIAN: "Slovenščina",
        LOCALE__FINNISH: "Suomi",
        LOCALE__SWEDISH: "Svenska",
        LOCALE__TAGALOG: "Tagalog",
        # LOCALE__TAMIL: "தமிழ் (Tamil)",
        # LOCALE__TELUGU: "తెలుగు (Telugu)",
        # LOCALE__THAI: "ไทย (Thai)",
        LOCALE__TURKISH: "Türkçe",
        LOCALE__UKRANIAN: "українська (Ukranian)",  # OpenSans includes cyrillic chars
        # LOCALE__URDU: "اردو (Urdu)",
        LOCALE__VIETNAMESE: "Tiếng Việt (Vietnamese)",
    }

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
            os.path.join(
                cwd, "seedsigner", "resources", "seedsigner-translations", "l10n"
            )
        ):
            for file in [f for f in files if f.endswith(".mo")]:
                # `root` will be [...]seedsigner/resources/seedsigner-translations/l10n/pt_BR/LC_MESSAGES
                locales_present.add(root.split(f"l10n{ os.sep }")[1].split(os.sep)[0])

        for locale in cls.ALL_LOCALES.keys():
            if locale in locales_present:
                detected_languages.append((locale, cls.ALL_LOCALES[locale]))

        return detected_languages

    BTC_DENOMINATION__BTC = "btc"
    BTC_DENOMINATION__SATS = "sats"
    BTC_DENOMINATION__THRESHOLD = "thr"
    BTC_DENOMINATION__BTCSATSHYBRID = "hyb"
    ALL_BTC_DENOMINATIONS = [
        (BTC_DENOMINATION__BTC, ("BTC")),
        (BTC_DENOMINATION__SATS, ("sats")),
        (BTC_DENOMINATION__THRESHOLD, ("Threshold at 0.01")),
        (BTC_DENOMINATION__BTCSATSHYBRID, ("BTC | sats hybrid")),
    ]

    CAMERA_ROTATION__0 = 0
    CAMERA_ROTATION__90 = 90
    CAMERA_ROTATION__180 = 180
    CAMERA_ROTATION__270 = 270
    ALL_CAMERA_ROTATIONS = [
        (CAMERA_ROTATION__0, ("0°")),
        (CAMERA_ROTATION__90, ("90°")),
        (CAMERA_ROTATION__180, ("180°")),
        (CAMERA_ROTATION__270, ("270°")),
    ]

    # QR code constants
    DENSITY__LOW = "L"
    DENSITY__MEDIUM = "M"
    DENSITY__HIGH = "H"
    # TRANSLATOR_NOTE: QR code density option: Low, Medium, High
    density_low = "Low"
    # TRANSLATOR_NOTE: QR code density option: Low, Medium, High
    density_medium = "Medium"
    # TRANSLATOR_NOTE: QR code density option: Low, Medium, High
    density_high = "High"
    ALL_DENSITIES = [
        (DENSITY__LOW, density_low),
        (DENSITY__MEDIUM, density_medium),
        (DENSITY__HIGH, density_high),
    ]

    # Seed-related constants
    MAINNET = "M"
    TESTNET = "T"
    REGTEST = "R"
    ALL_NETWORKS = [
        (MAINNET, ("Mainnet")),
        (TESTNET, ("Testnet")),
        (REGTEST, ("Regtest")),
    ]

    @classmethod
    def map_network_to_embit(cls, network) -> str:
        # Note these are `embit` constants; do not wrap for translation
        if network == SettingsConstants.MAINNET:
            return "main"
        elif network == SettingsConstants.TESTNET:
            return "test"
        if network == SettingsConstants.REGTEST:
            return "regtest"

    PERSISTENT_SETTINGS__SD_INSERTED__HELP_TEXT = "Store Settings on SD card"
    PERSISTENT_SETTINGS__SD_REMOVED__HELP_TEXT = "Insert SD card to enable"

    SINGLE_SIG = "ss"
    MULTISIG = "ms"
    ALL_SIG_TYPES = [
        (SINGLE_SIG, ("Single Sig")),
        (MULTISIG, ("Multisig")),
    ]

    LEGACY_P2PKH = "leg"
    NATIVE_SEGWIT = "nat"
    NESTED_SEGWIT = "nes"
    TAPROOT = "tr"
    CUSTOM_DERIVATION = "cus"
    ALL_SCRIPT_TYPES = [
        (NATIVE_SEGWIT, ("Native Segwit")),
        (NESTED_SEGWIT, ("Nested Segwit")),
        (LEGACY_P2PKH, ("Legacy")),
        (TAPROOT, ("Taproot")),
        (CUSTOM_DERIVATION, ("Custom Derivation")),
    ]

    WORDLIST_LANGUAGE__ENGLISH = "en"
    WORDLIST_LANGUAGE__CHINESE_SIMPLIFIED = "zh_Hans_CN"
    WORDLIST_LANGUAGE__CHINESE_TRADITIONAL = "zh_Hant_TW"
    WORDLIST_LANGUAGE__FRENCH = "fr"
    WORDLIST_LANGUAGE__ITALIAN = "it"
    WORDLIST_LANGUAGE__JAPANESE = "jp"
    WORDLIST_LANGUAGE__KOREAN = "kr"
    WORDLIST_LANGUAGE__PORTUGUESE = "pt"
    ALL_WORDLIST_LANGUAGES = [
        (WORDLIST_LANGUAGE__ENGLISH, "English"),
        # (WORDLIST_LANGUAGE__CHINESE_SIMPLIFIED, "简体中文"),
        # (WORDLIST_LANGUAGE__CHINESE_TRADITIONAL, "繁體中文"),
        # (WORDLIST_LANGUAGE__FRENCH, "Français"),
        # (WORDLIST_LANGUAGE__ITALIAN, "Italiano"),
        # (WORDLIST_LANGUAGE__JAPANESE, "日本語"),
        # (WORDLIST_LANGUAGE__KOREAN, "한국어"),
        # (WORDLIST_LANGUAGE__PORTUGUESE, "Português"),
    ]

    # Individual SettingsEntry attr_names
    # Note: attr_names are internal constants; do not wrap for translation
    SETTING__LOCALE = "locale"
    SETTING__WORDLIST_LANGUAGE = "wordlist_language"
    SETTING__PERSISTENT_SETTINGS = "persistent_settings"
    SETTING__COORDINATORS = "coordinators"
    SETTING__BTC_DENOMINATION = "denomination"

    SETTING__DISPLAY_CONFIGURATION = "display_config"
    SETTING__DISPLAY_COLOR_INVERTED = "color_inverted"

    SETTING__NETWORK = "network"
    SETTING__QR_DENSITY = "qr_density"
    SETTING__XPUB_EXPORT = "xpub_export"
    SETTING__SIG_TYPES = "sig_types"
    SETTING__SCRIPT_TYPES = "script_types"
    SETTING__XPUB_DETAILS = "xpub_details"
    SETTING__PASSPHRASE = "passphrase"
    SETTING__CAMERA_ROTATION = "camera_rotation"
    SETTING__COMPACT_SEEDQR = "compact_seedqr"
    SETTING__BIP85_CHILD_SEEDS = "bip85_child_seeds"
    SETTING__ELECTRUM_SEEDS = "electrum_seeds"
    SETTING__MESSAGE_SIGNING = "message_signing"
    SETTING__PRIVACY_WARNINGS = "privacy_warnings"
    SETTING__DIRE_WARNINGS = "dire_warnings"
    SETTING__QR_BRIGHTNESS_TIPS = "qr_brightness_tips"
    SETTING__PARTNER_LOGOS = "partner_logos"

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
    category: str
    attr_name: str
    display_name: str
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
        # General options
        SettingsEntry(
            category=SettingsConstants.CATEGORY__SYSTEM,
            attr_name=SettingsConstants.SETTING__LOCALE,
            abbreviated_name="lang",
            display_name=("Language"),
            type=SettingsConstants.TYPE__SELECT_1,
            selection_options=SettingsConstants.get_detected_languages(),
            default_value=SettingsConstants.LOCALE__ENGLISH,
        ),
        # TODO: Support other bip-39 wordlist languages! Until then, type == HIDDEN
        SettingsEntry(
            category=SettingsConstants.CATEGORY__SYSTEM,
            attr_name=SettingsConstants.SETTING__WORDLIST_LANGUAGE,
            abbreviated_name="wordlist_lang",
            display_name=("Mnemonic language"),
            type=SettingsConstants.TYPE__SELECT_1,
            visibility=SettingsConstants.VISIBILITY__HIDDEN,
            selection_options=SettingsConstants.ALL_WORDLIST_LANGUAGES,
            default_value=SettingsConstants.WORDLIST_LANGUAGE__ENGLISH,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__SYSTEM,
            attr_name=SettingsConstants.SETTING__PERSISTENT_SETTINGS,
            abbreviated_name="persistent",
            display_name=("Persistent settings"),
            help_text=SettingsConstants.PERSISTENT_SETTINGS__SD_INSERTED__HELP_TEXT,
            default_value=SettingsConstants.OPTION__DISABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__WALLET,
            attr_name=SettingsConstants.SETTING__COORDINATORS,
            abbreviated_name="coords",
            display_name=("Coordinator software"),
            type=SettingsConstants.TYPE__MULTISELECT,
            selection_options=SettingsConstants.ALL_COORDINATORS,
            default_value=[
                SettingsConstants.COORDINATOR__BLUE_WALLET,
                SettingsConstants.COORDINATOR__NUNCHUK,
                SettingsConstants.COORDINATOR__SPARROW,
                SettingsConstants.COORDINATOR__SPECTER_DESKTOP,
            ],
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__SYSTEM,
            attr_name=SettingsConstants.SETTING__BTC_DENOMINATION,
            abbreviated_name="denom",
            display_name=("Denomination display"),
            type=SettingsConstants.TYPE__SELECT_1,
            selection_options=SettingsConstants.ALL_BTC_DENOMINATIONS,
            default_value=SettingsConstants.BTC_DENOMINATION__THRESHOLD,
        ),
        # Advanced options
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__NETWORK,
            display_name=("Bitcoin network"),
            type=SettingsConstants.TYPE__SELECT_1,
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            selection_options=SettingsConstants.ALL_NETWORKS,
            default_value=SettingsConstants.MAINNET,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__QR_DENSITY,
            display_name=("QR code density"),
            type=SettingsConstants.TYPE__SELECT_1,
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            selection_options=SettingsConstants.ALL_DENSITIES,
            default_value=SettingsConstants.DENSITY__MEDIUM,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__XPUB_EXPORT,
            display_name=("Xpub export"),
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            default_value=SettingsConstants.OPTION__ENABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__SIG_TYPES,
            abbreviated_name="sigs",
            display_name=("Sig types"),
            type=SettingsConstants.TYPE__MULTISELECT,
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            selection_options=SettingsConstants.ALL_SIG_TYPES,
            default_value=SettingsConstants.ALL_SIG_TYPES,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__SCRIPT_TYPES,
            abbreviated_name="scripts",
            display_name=("Script types"),
            type=SettingsConstants.TYPE__MULTISELECT,
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            selection_options=SettingsConstants.ALL_SCRIPT_TYPES,
            default_value=[
                SettingsConstants.NATIVE_SEGWIT,
                SettingsConstants.NESTED_SEGWIT,
                SettingsConstants.TAPROOT,
            ],
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__XPUB_DETAILS,
            display_name=("Show xpub details"),
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            default_value=SettingsConstants.OPTION__ENABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__PASSPHRASE,
            display_name=("BIP-39 passphrase"),
            type=SettingsConstants.TYPE__SELECT_1,
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            selection_options=SettingsConstants.OPTIONS__ENABLED_DISABLED_REQUIRED,
            default_value=SettingsConstants.OPTION__ENABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__CAMERA_ROTATION,
            abbreviated_name="camera",
            display_name=("Camera rotation"),
            type=SettingsConstants.TYPE__SELECT_1,
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            selection_options=SettingsConstants.ALL_CAMERA_ROTATIONS,
            default_value=SettingsConstants.CAMERA_ROTATION__180,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__COMPACT_SEEDQR,
            display_name=("Compact SeedQR"),
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            default_value=SettingsConstants.OPTION__ENABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__BIP85_CHILD_SEEDS,
            abbreviated_name="bip85",
            display_name=("BIP-85 child seeds"),
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            default_value=SettingsConstants.OPTION__DISABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__ELECTRUM_SEEDS,
            abbreviated_name="electrum",
            display_name=("Electrum seeds"),
            help_text=("Native Segwit only"),
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            default_value=SettingsConstants.OPTION__DISABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__MESSAGE_SIGNING,
            display_name=("Message signing"),
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            default_value=SettingsConstants.OPTION__DISABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__PRIVACY_WARNINGS,
            abbreviated_name="priv_warn",
            display_name=("Show privacy warnings"),
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            default_value=SettingsConstants.OPTION__ENABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__DIRE_WARNINGS,
            abbreviated_name="dire_warn",
            display_name=("Show dire warnings"),
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            default_value=SettingsConstants.OPTION__ENABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__QR_BRIGHTNESS_TIPS,
            display_name=("Show QR brightness tips"),
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            default_value=SettingsConstants.OPTION__ENABLED,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__FEATURES,
            attr_name=SettingsConstants.SETTING__PARTNER_LOGOS,
            abbreviated_name="partners",
            display_name=("Show partner logos"),
            visibility=SettingsConstants.VISIBILITY__ADVANCED,
            default_value=SettingsConstants.OPTION__ENABLED,
        ),
        # Hardware config
        SettingsEntry(
            category=SettingsConstants.CATEGORY__SYSTEM,
            attr_name=SettingsConstants.SETTING__DISPLAY_CONFIGURATION,
            abbreviated_name="disp_conf",
            # TRANSLATOR_NOTE: Hardware settings option to specify the screen driver (e.g. st7789 vs ili9341)
            display_name=("Display type"),
            type=SettingsConstants.TYPE__SELECT_1,
            visibility=SettingsConstants.VISIBILITY__HARDWARE,
            selection_options=SettingsConstants.ALL_DISPLAY_CONFIGURATIONS,
            default_value=SettingsConstants.DISPLAY_CONFIGURATION__ST7789__240x240,
        ),
        SettingsEntry(
            category=SettingsConstants.CATEGORY__SYSTEM,
            attr_name=SettingsConstants.SETTING__DISPLAY_COLOR_INVERTED,
            abbreviated_name="rgb_inv",
            # TRANSLATOR_NOTE: Hardware settings option to invert how the screen driver displays colors.
            display_name=("Invert colors"),
            type=SettingsConstants.TYPE__ENABLED_DISABLED,
            visibility=SettingsConstants.VISIBILITY__HARDWARE,
            default_value=SettingsConstants.OPTION__DISABLED,
        ),
        # Developer options
        # TODO: No real Developer options needed yet. Disable for now.
        # SettingsEntry(category=SettingsConstants.CATEGORY__SYSTEM,
        #               attr_name=SettingsConstants.SETTING__DEBUG,
        #               display_name="Debug",
        #               visibility=SettingsConstants.VISIBILITY__DEVELOPER,
        #               default_value=SettingsConstants.OPTION__DISABLED),
        # "Hidden" settings with no UI interaction
        SettingsEntry(
            category=SettingsConstants.CATEGORY__SYSTEM,
            attr_name=SettingsConstants.SETTING__QR_BRIGHTNESS,
            abbreviated_name="qr_brightness",
            display_name=("QR background color"),
            type=SettingsConstants.TYPE__FREE_ENTRY,
            visibility=SettingsConstants.VISIBILITY__HIDDEN,
            default_value=62,
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

    if hostname == "seedsigner-os":
        output_file = "/mnt/microsd/settings_definition.json"
    else:
        output_file = "settings_definition.json"

    with open(output_file, "w") as json_file:
        json.dump(SettingsDefinition.to_dict(), json_file, indent=4)
