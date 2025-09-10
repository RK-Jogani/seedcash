import logging
import os
import time

from seedcash.models.singleton import Singleton
from seedcash.models.threads import BaseThread

logger = logging.getLogger(__name__)


class MicroSD(Singleton, BaseThread):
    MOUNT_POINT = "/mnt/microsd"
    FIFO_PATH = "/tmp/mdev_fifo"
    FIFO_MODE = 0o600
    ACTION__INSERTED = "add"
    ACTION__REMOVED = "remove"

    @classmethod
    def get_instance(cls):
        # This is the only way to access the one and only instance
        if cls._instance is None:
            # Instantiate the one and only instance
            microsd = cls.__new__(cls)
            cls._instance = microsd

            # explicitly call BaseThread __init__ since multiple class inheritance
            BaseThread.__init__(microsd)

        return cls._instance

    @property
    def is_inserted(self):
        from seedcash.models.settings import (
            Settings,
        )  # Import here to avoid circular import issues

        if Settings.HOSTNAME == Settings.SEEDCASH_OS:
            return os.path.exists(MicroSD.MOUNT_POINT)
        else:
            # Always True for Raspi OS
            return True

    def start_detection(self):
        self.start()

    def run(self):
        from seedcash.controller import Controller
        from seedcash.gui.toast import SDCardStateChangeToastManagerThread
        from seedcash.models.settings import (
            Settings,
        )  # Import here to avoid circular import issues

        action = ""

        # explicitly only microsd add/remove detection in seedcash-os
        if Settings.HOSTNAME == Settings.SEEDCASH_OS:

            # at start-up, get current status and inform Settings
            Settings.handle_microsd_state_change(
                action=(
                    MicroSD.ACTION__INSERTED
                    if self.is_inserted
                    else MicroSD.ACTION__REMOVED
                )
            )

            if os.path.exists(self.FIFO_PATH):
                os.remove(self.FIFO_PATH)

            os.mkfifo(self.FIFO_PATH, self.FIFO_MODE)

            while self.keep_running:
                with open(self.FIFO_PATH) as fifo:
                    action = fifo.read()
                    logger.info(f"fifo message: {action}")

                    Settings.handle_microsd_state_change(action=action)
                    Controller.get_instance().activate_toast(
                        SDCardStateChangeToastManagerThread(action=action)
                    )

                time.sleep(0.1)
