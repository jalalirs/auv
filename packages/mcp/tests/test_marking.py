"""The rule the whole server exists to keep: no naked numbers.

Called test_marking rather than test_provenance because tools/ has a
test_provenance.py of its own, and pytest names a test module by its
basename: two files of one name in one run collide and the second never
gets collected. Which means the whole suite could not be run in one
command — the sort of thing that is discovered by a green tick on half
of it.

An assistant asked for a number will produce one. The risk of putting one
between an operator and a decision is that nothing in the loop knows which
numbers were measured — and the answer this platform can give, which a wrapper
around a simulator cannot, is that its transport will not carry a bare figure.

So it is tested as a property of the answers rather than checked by hand.
"""

from __future__ import annotations

import pytest

from iocean_mcp import provenance as s


def test_a_value_needs_a_kind_we_recognise():
    with pytest.raises(ValueError):
        s.said(19.11, "probably", "the Atlas")


def test_a_value_needs_somebody_to_blame():
    """A measured value with no instrument named is the laundered measurement
    this platform exists to refuse. Cheaper to refuse here than to find it in
    somebody's report."""
    for empty in ("", "   ", None):
        with pytest.raises(ValueError):
            s.said(2.0, s.MEASURED, empty)


def test_unknown_is_not_zero_and_not_null():
    """A bench row written before the water was a field did not fly in still
    water. Nobody wrote down what it flew in."""
    said = s.unknown("nobody recorded the water")
    assert said["value"] is None
    assert said["kind"] is None
    assert "nobody recorded" in said["unknown"]


def test_numbers_finds_a_bare_figure_anywhere_in_a_tree():
    clean = {"a": s.said(1.0, s.MEASURED, "a ruler"),
             "b": [s.said(2, s.DERIVED, "arithmetic")],
             "c": {"d": s.said(3, s.CHOSEN, "somebody picked it")}}
    assert s.numbers(clean) == []
    leaky = dict(clean, rmsAfterM=2.0)
    assert s.numbers(leaky) == ["rmsAfterM"]
    deep = {"fit": {"bands": [{"medianM": -16.35}]}}
    assert s.numbers(deep) == ["fit.bands[0].medianM"]


def test_a_bool_is_not_a_number():
    """`published: true` is not a figure anybody can misreport as measured."""
    assert s.numbers({"published": True, "flyable": False}) == []


def test_the_four_words_are_the_platform_s_own():
    assert set(s.KINDS) == {"measured", "derived", "chosen", "assumed"}


# ── how an agent gets in ─────────────────────────────────────────────────────

def test_a_service_credential_uses_its_own_scheme(monkeypatch):
    """`Authorization: Service <principalId>:<secret>`, not Bearer.

    The platform reads two schemes and they mean different things: Bearer is a
    person's session and expires, Service is a program's own principal and does
    not. An agent on a Bearer token would be signing in as a person to renew it.
    """
    from iocean_mcp.platform import Platform

    seen = {}

    def catch(request, timeout=0):
        seen["auth"] = request.headers.get("Authorization")
        raise RuntimeError("far enough")

    monkeypatch.setattr("urllib.request.urlopen", catch)
    with pytest.raises(RuntimeError):
        Platform("http://x", service="prin_1:secret").request("GET", "/api/v1/me")
    assert seen["auth"] == "Service prin_1:secret"

    with pytest.raises(RuntimeError):
        Platform("http://x", token="tok").request("GET", "/api/v1/me")
    assert seen["auth"] == "Bearer tok"


def test_a_credential_can_come_from_a_file(monkeypatch, tmp_path):
    """An environment is inherited by every child process and readable by
    anything that can see /proc. The platform writes the worker's credential to
    a file for the same reason."""
    from iocean_mcp.platform import Platform

    where = tmp_path / "mcp"
    where.write_text("prin_2:from-a-file\n")
    monkeypatch.setenv("IOCEAN_PLATFORM", "http://x")
    monkeypatch.setenv("IOCEAN_SERVICE_FILE", str(where))
    monkeypatch.delenv("IOCEAN_SERVICE", raising=False)
    platform = Platform.from_environment()
    assert platform.service == "prin_2:from-a-file"
    assert platform.token is None


def test_a_missing_credential_file_says_which_one(monkeypatch, tmp_path):
    from iocean_mcp.platform import Platform, Refused

    monkeypatch.setenv("IOCEAN_PLATFORM", "http://x")
    monkeypatch.setenv("IOCEAN_SERVICE_FILE", str(tmp_path / "nope"))
    monkeypatch.delenv("IOCEAN_SERVICE", raising=False)
    with pytest.raises(Refused) as no:
        Platform.from_environment()
    assert "nope" in str(no.value)
