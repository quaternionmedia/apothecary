from typing import Optional

from jinja2 import BaseLoader, Environment

from .scene import Scene


class TemplateRenderer:
    """Jinja2-based template renderer for OpenSCAD code"""

    def __init__(self):
        self.env = Environment(loader=BaseLoader())

    def render_template(self, template_str: str, context: dict) -> str:
        """Render a Jinja2 template with the given context"""
        template = self.env.from_string(template_str)
        return template.render(**context)

    def render_scene_template(self, scene: Scene, template_str: Optional[str] = None) -> str:
        """Render a scene using a template"""
        if template_str is None:
            template_str = "{{ scene_code }}"

        context = {
            "scene_code": scene.render(),
            "scene_name": scene.name,
            "version": scene.version,
            "object_count": len(scene.objects),
        }

        return self.render_template(template_str, context)
