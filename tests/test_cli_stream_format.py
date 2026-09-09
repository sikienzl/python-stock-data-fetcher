from datetime import datetime, timezone

from src.cli import cli


def test_stream_format_uses_utc_timestamp():
    timestamp = 1_700_000_000_000
    human_time = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    assert human_time == "2023-11-14 22:13:20 UTC"


def test_cli_command_registered():
    command_names = {command.name for command in cli.commands.values()}

    assert {"fetch", "news", "stream"}.issubset(command_names)