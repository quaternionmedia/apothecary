from apothecary import Scene
from apothecary.projects.parts.rc.snowplow import snowplow_assembly

scene = Scene(
    name="rc_car_snowplow_demo",
    objects=[snowplow_assembly()],
)

if __name__ == "__main__":
    print(scene.render())
