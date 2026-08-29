"""Unit tests for the external-block classifier used by the agent playbook."""

from src.naukri_agent.bot.block_detector import classify_block


def test_no_block():
    assert classify_block("") is None
    assert classify_block("application submitted successfully") is None


def test_captcha():
    assert classify_block("Please complete the captcha to continue") == "captcha"
    assert classify_block("Verify you are human") == "captcha"


def test_otp():
    assert classify_block("Enter the OTP sent to your phone") == "otp"


def test_ip_ban():
    assert classify_block("Your IP has been blocked due to unusual activity") == "ip_ban"
    assert classify_block("429 Too Many Requests") == "ip_ban"
