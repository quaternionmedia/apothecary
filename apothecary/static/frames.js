/* The site's frame and three.js's, and a machine's frame in the site.
 *
 * The site is z-up, in millimetres; three.js is y-up. A point of the site stands in
 * the scene a quarter turn about x: (x, y, z) -> (x, z, -y), the site's y running
 * into the screen along three.js's -z. A turn, not a mirror: what stands on the
 * site's right stands on the scene's right.
 *
 * A machine's frame is api.machine_frame's record, which GET
 * /firmware/printers/where and the site's tree both carry (docs/viewer.md, A
 * machine's frame): `position`, the machine's origin in the site; `origin`, where
 * its volume's (0, 0, 0) stands in its own frame with the bed at rest; `volume`,
 * the working volume in mm. A point of the volume -- the work's coordinates,
 * counted up from the volume's low corner -- stands in the site at the machine's
 * origin plus `origin` plus the point, and a bed that carries Y carries what is on
 * it `bedOffset` mm along Y from where it rests.
 */

import * as THREE from "three";

// A point of the site's frame in three.js's.
export const sceneAt = (x, y, z) => new THREE.Vector3(x, z, -y);
// The same, for a point given as { x, y, z }.
export const toScene = (p) => sceneAt(p.x, p.y, p.z);
// A point of three.js's frame back in the site's, as [x, y, z].
export const siteAt = (v) => [v.x, -v.z, v.y];

// Where the volume's (0, 0, 0) stands in the site with the bed at rest. `at` is the
// machine's origin as the page holds it now (its node's position, which a layout
// edit moves before the server answers); the frame's own `position` without it.
export function bedOrigin(frame, at = null) {
    const p = at || { x: frame.position[0], y: frame.position[1], z: frame.position[2] };
    return { x: p.x + frame.origin[0], y: p.y + frame.origin[1], z: p.z + frame.origin[2] };
}

// A point of the machine's volume in the site, the bed `bedOffset` mm along Y from
// where it rests (0 for what does not ride the bed).
export function volumeToSite(frame, p, { at = null, bedOffset = 0 } = {}) {
    const o = bedOrigin(frame, at);
    return { x: o.x + p.x, y: o.y + p.y + bedOffset, z: o.z + p.z };
}
