import time

from takeout_photos.utils.timer import Timer


def test_timer_format_seconds():
    """Test formatting for seconds only."""
    timer = Timer()
    timer.elapsed = 3.5
    assert timer.format_elapsed() == "3s"


def test_timer_format_minutes_seconds():
    """Test formatting for minutes and seconds."""
    timer = Timer()
    timer.elapsed = 344.2  # 5m 44s
    assert timer.format_elapsed() == "5m 44s"


def test_timer_format_hours_minutes_seconds():
    """Test formatting for hours, minutes, and seconds."""
    timer = Timer()
    timer.elapsed = 4452.7  # 1h 14m 12s
    assert timer.format_elapsed() == "1h 14m 12s"


def test_timer_context_manager():
    """Test timer as context manager."""
    with Timer() as t:
        time.sleep(0.1)
    assert t.elapsed >= 0.1
    assert "0s" in t.format_elapsed() or "1s" in t.format_elapsed()


def test_timer_format_zero():
    """Test formatting when elapsed is None."""
    timer = Timer()
    assert timer.format_elapsed() == "0s"


def test_timer_format_exactly_one_minute():
    """Test formatting for exactly 1 minute."""
    timer = Timer()
    timer.elapsed = 60.0
    assert timer.format_elapsed() == "1m 0s"


def test_timer_format_exactly_one_hour():
    """Test formatting for exactly 1 hour."""
    timer = Timer()
    timer.elapsed = 3600.0
    assert timer.format_elapsed() == "1h 0m 0s"


def test_timer_name_parameter():
    """Test that name parameter can be set."""
    timer = Timer(name="test_operation")
    assert timer.name == "test_operation"
