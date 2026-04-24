from __future__ import annotations

import cantools
import cantools.database
from loguru import logger

from capl_gen.core.exceptions import ParseError
from capl_gen.schemas.signal import (
    ByteOrder,
    CANMessageModel,
    CANSignalModel,
    ParsedCANData,
)
from capl_gen.signals.base_parser import BaseParser
from capl_gen.signals.registry import register


@register
class CANDBCParser(BaseParser):
    """
    Parses CAN DBC files using ``cantools`` and returns a ``ParsedCANData`` model.

    Supported extensions: ``.dbc``

    What is extracted per message
    ------------------------------
    - Frame ID (decimal + hex)
    - DLC (data length code)
    - Sender node(s)
    - Message-level comment

    What is extracted per signal
    ----------------------------
    - Start bit, bit length, byte order
    - Signed/unsigned flag
    - Scaling (factor, offset)
    - Physical range (min, max)
    - Unit string
    - Value/mux table (choices)
    - Signal comment
    """

    signal_type = "CAN_DBC"
    supported_extensions: tuple[str, ...] = (".dbc",)

    # CAN-FD frames have DLC > 8; standard CAN tops at 8.
    _CANFD_DLC_THRESHOLD = 8

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def parse(self) -> ParsedCANData:
        """
        Load and parse the DBC file.

        Returns
        -------
        ParsedCANData
            Fully validated Pydantic model containing all messages and signals.

        Raises
        ------
        ParseError
            If cantools cannot load the file, or if any message/signal
            fails Pydantic validation.
        """
        logger.info(f"Parsing CAN DBC file: {self.file_path}")

        db = self._load_database()
        messages = self._extract_messages(db)

        result = ParsedCANData(
            source_file=str(self.file_path),
            messages=messages,
        )

        logger.success(
            f"DBC parsed — {result.message_count} messages, "
            f"{result.signal_count} signals  [{self.file_name}]"
        )
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_database(self) -> cantools.database.Database:
        """Wrap cantools load in a ParseError so callers see consistent errors."""
        try:
            db = cantools.database.load_file(str(self.file_path))
            logger.debug(f"cantools loaded {len(db.messages)} messages from DBC")
            return db
        except cantools.database.UnsupportedDatabaseFormatError as exc:
            raise ParseError(
                f"Unsupported DBC format in '{self.file_name}': {exc}"
            ) from exc
        except Exception as exc:
            raise ParseError(
                f"Failed to load DBC file '{self.file_name}': {exc}"
            ) from exc

    def _extract_messages(
        self, db: cantools.database.Database
    ) -> list[CANMessageModel]:
        messages: list[CANMessageModel] = []

        for raw_msg in db.messages:
            try:
                msg_model = self._map_message(raw_msg)
                messages.append(msg_model)
            except Exception as exc:
                # Log and skip bad messages — don't abort entire parse
                logger.warning(
                    f"Skipping message '{raw_msg.name}' "
                    f"(ID=0x{raw_msg.frame_id:X}): {exc}"
                )

        return messages

    def _map_message(
        self, raw_msg: cantools.database.Message
    ) -> CANMessageModel:
        signals = [self._map_signal(s) for s in raw_msg.signals]

        return CANMessageModel(
            name=raw_msg.name,
            frame_id=raw_msg.frame_id,
            length=raw_msg.length,
            is_fd=raw_msg.length > self._CANFD_DLC_THRESHOLD,
            signals=signals,
            comment=raw_msg.comment or None,
            senders=list(raw_msg.senders) if raw_msg.senders else [],
        )

    @staticmethod
    def _map_signal(raw_sig: cantools.database.Signal) -> CANSignalModel:
        byte_order = (
            ByteOrder.BIG_ENDIAN
            if raw_sig.byte_order == "big_endian"
            else ByteOrder.LITTLE_ENDIAN
        )

        # cantools gives choices as {int_value: "label"} or None
        choices: dict[int, str] = {}
        if raw_sig.choices:
            choices = {int(k): str(v) for k, v in raw_sig.choices.items()}

        return CANSignalModel(
            name=raw_sig.name,
            start_bit=raw_sig.start,
            length=raw_sig.length,
            byte_order=byte_order,
            is_signed=raw_sig.is_signed,
            factor=float(raw_sig.scale) if raw_sig.scale is not None else 1.0,
            offset=float(raw_sig.offset) if raw_sig.offset is not None else 0.0,
            minimum=float(raw_sig.minimum) if raw_sig.minimum is not None else None,
            maximum=float(raw_sig.maximum) if raw_sig.maximum is not None else None,
            unit=raw_sig.unit or "",
            choices=choices,
            comment=raw_sig.comment or None,
        )