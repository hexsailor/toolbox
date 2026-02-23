#!/usr/bin/env python3
"""
Simple hex parser for Teltonika protocol messages
Parses hex strings and identifies codec type and message structure


python hex_parser.py 00000000230000009101011b0000004c32533a6578437a537472513a20644c3a2032323320784c3a20300100006000
"""

import binascii
import sys
import json

# Import codec modules
try:
    from helpers.fm_codec87 import Codec87, Codec87BM50
    from helpers.fm_codec88 import Codec88, Codec88BM50
    from helpers.fm_codec89 import Codec89, Codec89BM
    from helpers.fm_codec90 import Codec90, Codec90BM
    from helpers.fm_codec92 import Codec92, Codec92BM
    from helpers.fm_codec94 import Codec94, Codec94BM
    from helpers.fm_codecA0 import CodecA0
    from helpers.fm_codecA4 import CodecA4
    from helpers.fm_codecA7 import CodecA7
    from helpers.fm_codecA8 import CodecA8
    from helpers.fm_codecA1 import CodecA1
    CODECS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import codec modules: {e}")
    print("Decoded data will not be available.\n")
    CODECS_AVAILABLE = False


def parse_hex_message(hex_string):
    """Parse a hex message and display its structure"""

    # Remove spaces and ensure it's uppercase
    hex_string = hex_string.replace(" ", "").upper()

    print(f"\n{'='*60}")
    print(f"HEX MESSAGE PARSER")
    print(f"{'='*60}\n")

    print(f"Full hex: {hex_string}")
    print(f"Length: {len(hex_string)} characters ({len(hex_string)//2} bytes)\n")

    try:
        # Convert to bytes for display
        raw_bytes = binascii.unhexlify(hex_string)
        print(f"Raw bytes view:")
        for i in range(0, len(raw_bytes), 16):
            hex_part = " ".join(f"{b:02x}" for b in raw_bytes[i : i + 16])
            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in raw_bytes[i : i + 16])
            print(f"{i:08x}: {hex_part:<48} {ascii_part}")
        print()

        # Parse structure
        pos = 0

        # Preamble (4 bytes / 8 hex chars)
        if len(hex_string) >= 8:
            preamble = hex_string[pos : pos + 8]
            print(f"[{pos:04d}-{pos+7:04d}] Preamble:    {preamble}")
            pos += 8

        # Data length (4 bytes / 8 hex chars)
        if len(hex_string) >= pos + 8:
            data_length_hex = hex_string[pos : pos + 8]
            data_length = int(data_length_hex, 16)
            print(f"[{pos:04d}-{pos+7:04d}] Data Length: {data_length_hex} ({data_length} bytes)")
            pos += 8

        # Codec ID (1 byte / 2 hex chars)
        if len(hex_string) >= pos + 2:
            codec_id = hex_string[pos : pos + 2]
            print(f"[{pos:04d}-{pos+1:04d}] Codec ID:    {codec_id}")
            pos += 2

            # Identify codec
            codec_info = get_codec_info(codec_id)
            print(f"\n{'='*60}")
            print(f"CODEC INFORMATION")
            print(f"{'='*60}")
            print(f"Codec ID: {codec_id}")
            print(f"Type: {codec_info['type']}")
            print(f"Description: {codec_info['description']}")
            print(f"Parser Class: {codec_info['parser']}")
            print(f"{'='*60}\n")

            # Decode the data using the appropriate codec
            if CODECS_AVAILABLE:
                decoded_data = decode_with_codec(hex_string, codec_id)
                if decoded_data:
                    print(f"{'='*60}")
                    print(f"DECODED DATA")
                    print(f"{'='*60}")
                    print(json.dumps(decoded_data, indent=2, default=str))
                    print(f"{'='*60}\n")

        # Payload (remaining data minus CRC)
        if len(hex_string) >= pos + 8:
            # CRC is last 4 bytes (8 hex chars)
            payload_end = len(hex_string) - 8
            payload = hex_string[pos:payload_end]

            print(f"[{pos:04d}-{payload_end-1:04d}] Payload:     {payload}")

            # Try to decode payload as ASCII if it looks like text
            try:
                payload_bytes = binascii.unhexlify(payload)
                ascii_text = payload_bytes.decode("utf-8", errors="ignore")
                printable = "".join(c if c.isprintable() or c == "\n" else "." for c in ascii_text)
                if printable.strip():
                    print(f"                 (ASCII): {printable}")
            except:
                pass

            pos = payload_end

        # CRC (4 bytes / 8 hex chars)
        if len(hex_string) >= pos + 8:
            crc = hex_string[pos : pos + 8]
            print(f"[{pos:04d}-{pos+7:04d}] CRC:         {crc}")

    except Exception as e:
        print(f"\nError parsing hex: {e}")


def decode_with_codec(hex_string, codec_id):
    """Decode the hex message using the appropriate codec"""

    if not CODECS_AVAILABLE:
        return None

    codec_id_upper = codec_id.upper()
    codec = None

    try:
        # Map codec ID to codec class (default non-BM50 version)
        if codec_id_upper == "87":
            codec = Codec87(hex_string)
        elif codec_id_upper == "88":
            codec = Codec88(hex_string)
        elif codec_id_upper == "89":
            codec = Codec89(hex_string)
        elif codec_id_upper == "90":
            codec = Codec90(hex_string)
        elif codec_id_upper == "91":
            # Codec 91 is parsed by Codec89
            codec = Codec89(hex_string)
        elif codec_id_upper == "92":
            codec = Codec92(hex_string)
        elif codec_id_upper == "94":
            codec = Codec94(hex_string)
        elif codec_id_upper == "A0":
            codec = CodecA0(hex_string)
        elif codec_id_upper == "A4":
            codec = CodecA4(hex_string)
        elif codec_id_upper == "A7":
            codec = CodecA7(hex_string)
        elif codec_id_upper == "A8":
            codec = CodecA8(hex_string)
        elif codec_id_upper == "A1":
            codec = CodecA1(hex_string)
        else:
            print(f"No decoder available for codec {codec_id_upper}")
            return None

        # Decode the data
        if codec:
            data_decoded = codec.decode()
            return data_decoded

    except Exception as e:
        print(f"Error decoding with codec {codec_id_upper}: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_codec_info(codec_id):
    """Return information about the codec"""

    codecs = {
        "87": {
            "type": "AVL Data (High Priority)",
            "description": "High priority AVL data with extended records",
            "parser": "Codec87 or Codec87BM50 (for BM50)",
        },
        "88": {
            "type": "AVL Data (Extended)",
            "description": "Extended AVL data packet",
            "parser": "Codec88 or Codec88BM50 (for BM50)",
        },
        "89": {
            "type": "Command Response",
            "description": "Response to commands sent to device",
            "parser": "Codec89 or Codec89BM (for BM50)",
        },
        "90": {
            "type": "Sensor List",
            "description": "List of available sensors on the device",
            "parser": "Codec90 or Codec90BM (for BM50)",
        },
        "91": {
            "type": "Log Response",
            "description": "Log data from device (parsed by Codec89)",
            "parser": "Codec89 or Codec89BM (for BM50)",
        },
        "92": {
            "type": "PGN List",
            "description": "List of CAN PGN (Parameter Group Numbers)",
            "parser": "Codec92 or Codec92BM (for BM50)",
        },
        "94": {
            "type": "Source List",
            "description": "List of data sources",
            "parser": "Codec94 or Codec94BM (for BM50)",
        },
        "95": {"type": "Log Data", "description": "Debug log data (mobile app)", "parser": "parse_log_data() method"},
        "A0": {"type": "Login/ACK", "description": "Login acknowledgment for BM50 protocol", "parser": "CodecA0"},
        "A4": {"type": "Sensor List (BM50)", "description": "BM50 sensor list", "parser": "CodecA4"},
        "A7": {"type": "AVL Data (BM50)", "description": "BM50 AVL data", "parser": "CodecA7"},
        "A8": {"type": "AVL Data (BM50 Extended)", "description": "BM50 extended AVL data", "parser": "CodecA8"},
    }

    codec_id_upper = codec_id.upper()
    if codec_id_upper in codecs:
        return codecs[codec_id_upper]
    else:
        return {"type": "Unknown", "description": f"Unknown codec ID: {codec_id}", "parser": "No parser available"}


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Get hex from command line argument
        hex_input = sys.argv[1]
    else:
        # Default example
        hex_input = "00000000230000009101011b0000004c32533a6578437a537472513a20644c3a2032323320784c3a20300100006000"

    parse_hex_message(hex_input)

    print("\n" + "=" * 60)
    print("USAGE:")
    print("=" * 60)
    print(f"  python3 {sys.argv[0]} <hex_string>")
    print(f"  python3 {sys.argv[0]} 00000000230000009101011b...")
    print("=" * 60 + "\n")
