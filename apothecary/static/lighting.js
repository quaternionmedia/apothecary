/* The lighting rig, lit by the console.
 *
 * Each placed fixture glows the colour the console's levels give it (GET
 * /sites/{s}/lighting/state, polled), with a beam cone from its lens. The
 * unplaced patches are listed in a panel with their live levels, and the panel
 * says when the feed is silent. The rig comes from GET /sites/{s}/lighting when
 * the site changes; a site with no rig (rig: null) gets no overlay.
 *
 * mountLighting({ scene, base }) -> { setSite(name), stats() }
 *   setSite(name): the page is on this site now; "" or a site with no rig clears it.
 *   stats(): what is drawn, for a test: { placed, lit, unplaced, seq }.
 *
 * shortcut: the beam takes the rig's ORIENTATION as Euler degrees, XYZ, in the
 * site's frame, which is an assumption about the venue's convention, not checked
 * against it; scenic elements are not lit; the panel lists the unplaced patches
 * without a way to select one.
 */

import * as THREE from "three";

const POLL_MS = 200;
const DEG = Math.PI / 180;
const GLOW_MM = 250;
const BEAM_MM = 6000;
const BEAM_RADIUS_MM = 1500;

// apothecary (x, y, z) z-up -> three.js (x, z, y) y-up; site units are mm.
const toScene = (x, y, z) => new THREE.Vector3(x, z, y);

export function mountLighting({ scene, base }) {
  const group = new THREE.Group();
  group.name = "lighting";
  scene.add(group);

  const panel = document.createElement("div");
  panel.className = "lighting-panel";
  panel.hidden = true;
  panel.style.cssText =
    "position:fixed;right:12px;bottom:12px;max-height:40vh;overflow:auto;width:260px;" +
    "background:rgba(20,20,24,0.85);color:#ddd;font:12px/1.4 sans-serif;padding:8px;border-radius:6px;z-index:5";
  document.body.appendChild(panel);

  let site = null;
  let token = 0;
  let busy = false;
  let rig = null;
  let placed = [];  // { channel, fixture_type, glow, beam } for each located patch
  let unplaced = [];
  let feed = { seq: 0, age: null, rgb: {}, status: {} };

  const getJson = async (url) => {
    const r = await fetch(url, { cache: "no-store" });
    return r.ok ? r.json() : null;
  };

  const clear = () => {
    for (const f of placed) {
      f.glow.geometry.dispose(); f.glow.material.dispose();
      f.beam.geometry.dispose(); f.beam.material.dispose();
    }
    group.clear();
    placed = [];
    unplaced = [];
    rig = null;
    panel.hidden = true;
  };

  const build = (r) => {
    rig = r.rig;
    for (const p of rig.patches) {
      if (!p.location) { unplaced.push(p); continue; }
      const at = toScene(p.location.x * 1000, p.location.y * 1000, p.location.z * 1000);
      const holder = new THREE.Group();
      holder.position.copy(at);
      const o = p.orientation || { x: 0, y: 0, z: 0 };
      // Beam default: three.js -y, which is site -z, i.e. down. Orientation as Euler XYZ, see shortcut.
      holder.rotation.set(o.x * DEG, o.z * DEG, o.y * DEG, "XYZ");
      const glow = new THREE.Mesh(
        new THREE.SphereGeometry(GLOW_MM, 12, 8),
        new THREE.MeshBasicMaterial({ color: 0x000000 }),
      );
      const beamGeo = new THREE.ConeGeometry(BEAM_RADIUS_MM, BEAM_MM, 16, 1, true);
      beamGeo.translate(0, -BEAM_MM / 2, 0);  // apex at the lens, opening along -y
      const beam = new THREE.Mesh(
        beamGeo,
        new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide }),
      );
      holder.add(glow, beam);
      group.add(holder);
      placed.push({ channel: p.channel, fixture_type: p.fixture_type, glow, beam });
    }
    panel.hidden = false;
    renderPanel();
  };

  // A list of text, not markup: a label is whatever the venue typed.
  const renderPanel = () => {
    const head = feed.seq === 0 ? "no console feed" : `console ${Math.round(feed.age)} s ago`;
    panel.replaceChildren();
    const title = document.createElement("div");
    title.style.fontWeight = "bold";
    title.textContent = `Lighting: ${head}, ${unplaced.length} unplaced`;
    panel.appendChild(title);
    // What the console says of itself (OSC), as text: its command line, its active channels.
    for (const [label, address] of [["cmd", "/eos/out/cmd"], ["active", "/eos/out/active/chan"]]) {
      const args = feed.status[address];
      if (!args || args.length === 0) continue;
      const line = document.createElement("div");
      line.textContent = `${label}: ${args.join(" ")}`;
      panel.appendChild(line);
    }
    for (const p of unplaced) {
      const row = document.createElement("div");
      const rgb = feed.rgb[String(p.channel)] || [0, 0, 0];
      const swatch = document.createElement("span");
      swatch.style.cssText = `display:inline-block;width:10px;height:10px;margin-right:6px;background:rgb(${rgb.join(",")})`;
      row.append(swatch, document.createTextNode(`${p.channel} ${p.label || p.fixture_type}`));
      panel.appendChild(row);
    }
  };

  const apply = (s) => {
    feed = { seq: s.seq, age: s.age, rgb: s.rgb || {}, status: s.status || {} };
    for (const f of placed) {
      const rgb = feed.rgb[String(f.channel)] || [0, 0, 0];
      const c = new THREE.Color(rgb[0] / 255, rgb[1] / 255, rgb[2] / 255);
      f.glow.material.color.copy(c);
      f.beam.material.color.copy(c);
      f.beam.material.opacity = 0.05 + 0.25 * Math.max(...rgb) / 255;
    }
    renderPanel();
  };

  const poll = async () => {
    if (busy || !site || !rig) return;
    busy = true;
    const mine = token;
    try {
      const s = await getJson(`${base}/sites/${site}/lighting/state`);
      if (mine === token && s) apply(s);
    } finally {
      busy = false;
    }
  };

  setInterval(poll, POLL_MS);

  return {
    async setSite(name) {
      token++;
      clear();
      site = name || null;
      if (!site) return;
      const mine = token;
      const r = await getJson(`${base}/sites/${site}/lighting`);
      if (mine !== token || !r || !r.rig) return;  // a site with no rig: nothing to draw
      build(r);
      poll();
    },
    stats() {
      return {
        placed: placed.length,
        lit: placed.filter((f) => (feed.rgb[String(f.channel)] || []).some((v) => v > 0)).length,
        unplaced: unplaced.length,
        seq: feed.seq,
      };
    },
  };
}
