"""Kept: every pin a page made and every picture the browser kept, every site's,
each taken back from its row -- from another site's page, without switching to it.

A stub of the pictures plan's Phase 5. A camera and a look are pinned in
``garage`` and two pictures kept (one pinned there as the look, one pinned
nowhere); the page shows ``parts_library``. Kept lists all of it, each row naming
its site, and takes back the camera, the look and the unpinned picture from their
rows; the site on screen and the URL never change.
"""

from __future__ import annotations

import io
import re

import pytest
from PIL import Image, ImageDraw
from playwright.sync_api import expect

CAMERA = "kept_panel_camera"


def _png(offset: int) -> bytes:
    img = Image.new("L", (400, 300), 245)
    ImageDraw.Draw(img).rectangle((40 + offset, 40, 200 + offset, 160), fill=30)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def _keep(page, base_url: str, name: str, offset: int, where: str = "") -> dict:
    kept = page.request.post(
        f"{base_url}/photos/pictures?name={name}&kept=upload{where}",
        data=_png(offset),
        headers={"Content-Type": "image/png"},
    )
    assert kept.status == 201, kept.text()
    return kept.json()


@pytest.fixture
def leaves_as_found(page, base_url: str):
    """After the test: the camera, looks and kept pictures it added are taken back."""
    api = page.request
    looks = {lk["id"] for lk in api.get(f"{base_url}/placed").json()["looks"]}
    pictures = {p["path"] for p in api.get(f"{base_url}/photos/pictures").json()}
    yield
    api.delete(f"{base_url}/cameras/{CAMERA}")
    for look in api.get(f"{base_url}/placed").json()["looks"]:
        if look["id"] not in looks:
            api.delete(f"{base_url}/sites/{look['site']}/looks/{look['id']}")
    for picture in api.get(f"{base_url}/photos/pictures").json():
        if picture["path"] not in pictures and picture["kept"]:
            api.delete(f"{base_url}/photos/pictures/{picture['path']}")


@pytest.mark.e2e
def test_kept_takes_back_another_sites_pins_and_a_kept_picture_without_switching(
    page, base_url: str, leaves_as_found
):
    api = page.request
    placed = api.put(
        f"{base_url}/cameras/{CAMERA}",
        data={"label": "kept test camera", "site": "garage", "path": "workbench"},
    )
    assert placed.ok, placed.text()
    pinned = _keep(page, base_url, "kept_look.png", 0, "&site=garage&host=workbench")
    look = pinned["look"]
    assert look, pinned
    loose = _keep(page, base_url, "kept_loose.png", 60)
    assert not loose.get("look")

    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base_url}/viewer/sites/parts_library")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    url = page.url
    status = page.locator("#status")

    page.evaluate("() => window.apothecaryPanels.open('kept')")
    panel = page.locator(".panel[data-panel='kept']")
    expect(panel).to_be_visible(timeout=3000)
    expect(panel.locator(".panel-name")).to_have_text("Kept")

    # Each row names its site; garage's are not this page's.
    camera = panel.locator(".kept-row.camera", has_text="kept test camera")
    expect(camera).to_contain_text("garage › workbench", timeout=5000)
    expect(camera).not_to_have_class(re.compile(r"\bhere\b"))
    row = panel.locator(f".kept-row.look:has(.kept-look-unpin[data-id='{look['id']}'])")
    expect(row).to_contain_text("garage › workbench")
    picture = panel.locator(f".kept-row.picture[data-path='{loose['path']}']")
    expect(picture).to_be_visible()
    expect(panel.locator(f".kept-row.picture[data-path='{pinned['path']}']")).to_be_visible()

    # The camera, unpinned from its row.
    camera.locator(".kept-camera-unpin").click()
    expect(camera).to_have_count(0, timeout=5000)
    assert CAMERA not in {c["id"] for c in api.get(f"{base_url}/cameras").json()}
    expect(status).to_contain_text("camera unpinned from garage › workbench")

    # The look, unpinned from its row; its picture stays kept.
    row.locator(".kept-look-unpin").click()
    expect(row).to_have_count(0, timeout=5000)
    looks = api.get(f"{base_url}/sites/garage/attached").json()["looks"]
    assert look["id"] not in {lk["id"] for lk in looks}
    expect(panel.locator(f".kept-row.picture[data-path='{pinned['path']}']")).to_be_visible()

    # The picture pinned nowhere, forgotten from its row.
    picture.locator(".kept-forget").click()
    expect(picture).to_have_count(0, timeout=5000)
    kept = {p["path"] for p in api.get(f"{base_url}/photos/pictures").json()}
    assert loose["path"] not in kept and pinned["path"] in kept

    # Nothing switched the site.
    assert page.url == url
    assert page.evaluate("() => window.fractalViewer.siteName") == "parts_library"
    expect(page.locator("#site-select")).to_have_value("parts_library")
    expect(status).not_to_have_class(re.compile(r"\berror\b"))
    assert errors == []


@pytest.mark.e2e
def test_folder_more_opens_kept(page, base_url: str):
    """The eighth leaf of Picture › Folder, More, opens Kept."""
    page.goto(f"{base_url}/viewer/sites/garage")
    expect(page.locator("#contents-list .contents-item").first).to_be_visible(timeout=20000)
    page.evaluate("() => localStorage.removeItem('apothecary.panels')")
    carried = page.evaluate(
        "() => window.apothecaryPictureVerbs.carry({ action: 'picture:kept',"
        " context: { pointing: 'node', targets: ['workbench'] } })"
    )
    assert carried is True
    expect(page.locator(".panel[data-panel='kept']")).to_be_visible(timeout=3000)
    expect(page.locator("#status")).to_contain_text("Kept")
