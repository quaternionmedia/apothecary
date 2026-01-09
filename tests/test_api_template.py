from fastapi.testclient import TestClient

from apothecary.api import app
from apothecary.example import create_example_scene


def test_render_scene_with_template_endpoint():
    client = TestClient(app)
    scene = create_example_scene()
    tpl = "// T: {{ scene_name }}\n{{ scene_code }}"
    r = client.post("/render/template", json={"scene": scene.model_dump(), "template": tpl})
    assert r.status_code == 200
    data = r.json()
    assert data.get("success") is True
    assert data["code"].startswith("// T:")
