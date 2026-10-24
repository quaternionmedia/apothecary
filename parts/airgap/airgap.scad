// airgap — a rotor/stator pair of any base form, with the conductors that wind it.
//
// Every surface is computed here, from the assignments below, so the rotor, the stator and the
// windings are edited as text: change a base form, a feature ratio, a coverage or a slot string
// and the part follows. Each surface starts from a base curve (circle, ellipse, superellipse,
// rounded polygon or a constant-width support curve), is scaled in its own frame by
// spiral(psi) * (1 + ribbon(psi)) * (1 + teeth(psi)) -- a nautilus step, a Möbius ribbon's reach,
// fractal gearing -- then rotated and offset from the machine axis and re-sampled as a polar
// profile about that axis. The rotor spins rigidly about the axis, so an offset rotor is
// eccentric; an offset stator is a displaced bore. The bore scale is solved so the closest
// approach over every rotor angle equals the nominal air gap. Windings reduce to conductor
// stations (a signed turn count at a stator angle) and are swept as bundles.
//
// Units: mm and degrees. Ratios are of r0. apothecary/projects/parts/airgap.py mirrors the
// surface pipeline for bounds and checks the values; its defaults are the literals here.
// Tools: drafted with Claude in an airgap session; a human ratifies before merge.

/* [Scale] */
r0 = 30;            // [5:1:200] rotor base radius [mm]
stack = 20;         // [2:1:200] axial stack length [mm]
gap = 1.5;          // [0.1:0.1:10] nominal air gap [mm]
phi = 0;            // [0:1:360] rotor angle [deg]
resolution = 360;   // [72:36:1440] polar samples about the axis
show_rotor = true;
show_stator = true;
show_windings = true;

/* [Rotor] */
rotor_base_form = "circle";     // [circle, ellipse, superellipse, polygon, constwidth]
rotor_base_ratio = 0.8;         // [0.2:0.01:1] minor/major axis of an ellipse or superellipse
rotor_base_exp = 4;             // [1:0.1:12] superellipse exponent
rotor_base_sides = 4;           // [3:1:16] polygon sides
rotor_base_round = 0.3;         // [0:0.01:1] polygon rounding, 1 is a circle
rotor_base_width_k = 3;         // [3:2:15] constant-width lobes (odd)
rotor_base_width_a = 0.08;      // [0:0.005:0.3] constant-width lobe depth
rotor_rot = 0;                  // [-180:1:180] rotation about its own centre [deg]
rotor_off_x = 0;                // [-0.4:0.01:0.4] offset from the axis [x r0]
rotor_off_y = 0;                // [-0.4:0.01:0.4] offset from the axis [x r0]
rotor_spiral_b = 0.35;          // [0:0.01:2] nautilus growth per turn (0 is none)
rotor_spiral_k = 2;             // [1:1:16] nautilus steps per revolution
rotor_spiral_s = 0.85;          // [0:0.01:1] step sharpness
rotor_rib_k = 3;                // [0:1:32] Möbius ribbon lobes (0 is none)
rotor_rib_w = 0.12;             // [0:0.01:0.5] ribbon reach
rotor_rib_p = 1;                // [0.1:0.1:6] ribbon lobe sharpness
rotor_rib_mode = "envelope";    // [single, envelope, woven]
rotor_teeth_n = 0;              // [0:1:256] teeth (0 is none)
rotor_teeth_h = 0.08;           // [0:0.005:0.5] tooth height
rotor_teeth_l = 0;              // [0:1:6] fractal levels under each tooth
rotor_teeth_m = 3;              // [2:1:8] teeth per tooth, each level down
rotor_teeth_rho = 0.5;          // [0:0.01:0.99] height ratio, each level down
rotor_teeth_shape = "trap";     // [trap, sine, tri, saw]

/* [Stator] */
stator_base_form = "circle";    // [circle, ellipse, superellipse, polygon, constwidth]
stator_base_ratio = 0.8;        // [0.2:0.01:1]
stator_base_exp = 4;            // [1:0.1:12]
stator_base_sides = 4;          // [3:1:16]
stator_base_round = 0.3;        // [0:0.01:1]
stator_base_width_k = 3;        // [3:2:15]
stator_base_width_a = 0.08;     // [0:0.005:0.3]
stator_rot = 0;                 // [-180:1:180] rotation about its own centre [deg]
stator_off_x = 0;               // [-0.4:0.01:0.4] bore offset from the axis [x r0]
stator_off_y = 0;               // [-0.4:0.01:0.4] bore offset from the axis [x r0]
stator_spiral_b = 0;            // [0:0.01:2]
stator_spiral_k = 2;            // [1:1:16]
stator_spiral_s = 0.8;          // [0:0.01:1]
stator_rib_k = 0;               // [0:1:32]
stator_rib_w = 0.1;             // [0:0.01:0.5]
stator_rib_p = 1;               // [0.1:0.1:6]
stator_rib_mode = "envelope";   // [single, envelope, woven]
stator_teeth_n = 12;            // [0:1:256] teeth, one slot each unless slots is set
stator_teeth_h = 0.08;          // [0:0.005:0.5]
stator_teeth_l = 3;             // [0:1:6]
stator_teeth_m = 3;             // [2:1:8]
stator_teeth_rho = 0.5;         // [0:0.01:0.99]
stator_teeth_shape = "trap";    // [trap, sine, tri, saw]
stator_cov_segs = 1;            // [1:1:24] stator segments
stator_cov_arc = 1;             // [0.05:0.01:1] fraction of the ring the segments cover
stator_cov_rot = 0;             // [-180:1:180] where the first segment is centred [deg]
stator_outer_form = "concentric"; // [concentric, round, square, hex]
stator_yoke = 6;                // [1:0.5:60] yoke thickness behind the teeth [mm]

/* [Windings] */
topology = "tooth";             // [tooth, lap, wave, toroidal, sinusoidal, custom]
phases = 3;                     // [0:1:6]
pattern = "diametral";          // [diametral, sequential, paired, custom]
layout = "";                    // slot string when pattern is custom: "A+ A+ C- C- B+ B+ A- A- C+ C+ B- B-"
custom_stations = "";           // when topology is custom: "A: 0:50 90:-50; B: 30:50 120:-50" (deg:turns)
turns = 50;                     // [1:1:1000] turns per coil
span = 0.6;                     // [0.05:0.01:1] tooth coil span, in slot pitches
pitch = 1;                      // [1:1:48] lap coil pitch, in slots
slots = 0;                      // [0:1:256] slots; 0 is one per stator tooth
skew_deg = 0;                   // [0:1:90] conductor skew over the stack [deg]
wire_d = 1.2;                   // [0.2:0.1:20] conductor bundle diameter [mm]
pole_pairs = 4;                 // [1:1:32] of a sinusoidal sheet

/* [Hidden] */
own_samples = 2880;             // samples of each surface in its own frame before re-sampling
sweep_sides = 8;                // facets of a conductor bundle
sweep_hulls = false;            // true sweeps each bundle as hulls of spheres instead of one polyhedron (slow on CGAL)
echo_surfaces = false;          // -D echo_surfaces=true prints the sampled surfaces for checking
phase_colors = ["#d9925a", "#4fb3a6", "#6f9ad8", "#b57bd1", "#b7c45a", "#e07a9a"];
PHASES = "ABCDEF";

// A side packed for the functions below; the order is that of Side in the Python mirror.
rotor_side = [rotor_base_form, rotor_base_ratio, rotor_base_exp, rotor_base_sides, rotor_base_round,
  rotor_base_width_k, rotor_base_width_a, rotor_rot, rotor_off_x, rotor_off_y,
  rotor_spiral_b, rotor_spiral_k, rotor_spiral_s, rotor_rib_k, rotor_rib_w, rotor_rib_p, rotor_rib_mode,
  rotor_teeth_n, rotor_teeth_h, rotor_teeth_l, rotor_teeth_m, rotor_teeth_rho, rotor_teeth_shape];
stator_side = [stator_base_form, stator_base_ratio, stator_base_exp, stator_base_sides, stator_base_round,
  stator_base_width_k, stator_base_width_a, stator_rot, stator_off_x, stator_off_y,
  stator_spiral_b, stator_spiral_k, stator_spiral_s, stator_rib_k, stator_rib_w, stator_rib_p, stator_rib_mode,
  stator_teeth_n, stator_teeth_h, stator_teeth_l, stator_teeth_m, stator_teeth_rho, stator_teeth_shape];
S_FORM = 0; S_RATIO = 1; S_EXP = 2; S_SIDES = 3; S_ROUND = 4; S_WK = 5; S_WA = 6; S_ROT = 7; S_OX = 8; S_OY = 9;
S_SPB = 10; S_SPK = 11; S_SPS = 12; S_RBK = 13; S_RBW = 14; S_RBP = 15; S_RBMODE = 16;
S_TN = 17; S_TH = 18; S_TL = 19; S_TM = 20; S_TRHO = 21; S_TSHAPE = 22;

// ---- small helpers ----------------------------------------------------------------------------
function frac(x) = x - floor(x);
function mod360(a) = a - 360 * floor(a / 360);
function clamp(x, lo, hi) = min(hi, max(lo, x));
function spow(x, e) = sign(x) * pow(abs(x), e);
function sum(v, i = 0) = i >= len(v) ? 0 : v[i] + sum(v, i + 1);
function range_max(v) = len(v) == 0 ? 0 : max(v);
// largest k in [lo, hi) with u[k] <= t, for u ascending and u[lo] <= t
function bsearch(u, t, lo, hi) = hi - lo <= 1 ? lo
  : let (mid = floor((lo + hi) / 2)) u[mid] <= t ? bsearch(u, t, mid, hi) : bsearch(u, t, lo, mid);
// linear interpolation in a periodic array, x in samples
function interp(arr, x) = let (n = len(arr), i0 = floor(x), f = x - i0, a = ((i0 % n) + n) % n, b = (a + 1) % n)
  arr[a] * (1 - f) + arr[b] * f;
function sort_by(v, key) = len(v) <= 1 ? v
  : let (p = v[floor(len(v) / 2)][key])
    concat(sort_by([for (x = v) if (x[key] < p) x], key),
           [for (x = v) if (x[key] == p) x],
           sort_by([for (x = v) if (x[key] > p) x], key));

// ---- feature stack of one side, psi in degrees of its own frame ------------------------------
function wave(x, form) =
  form == "sine" ? 0.5 + 0.5 * sin(x)
  : form == "trap" ? 0.5 + 0.5 * clamp(2.5 * sin(x), -1, 1)
  : form == "tri" ? let (u = frac(x / 360) * 2) 1 - abs(u - 1)
  : frac(x / 360 + 1e-9);  // a saw's drop nudged off the sample grid, so two trig libraries agree
function peak(form) = form == "tri" ? 180 : form == "saw" ? 360 * 0.999 : 90;
function spiral(s, th) = s[S_SPB] <= 0 ? 1
  : let (b = s[S_SPB], d = max(0.02, 0.5 * (1 - s[S_SPS])), u = frac(s[S_SPK] * th / 360), eb = exp(-b))
    u < 1 - d ? exp(b * (u / (1 - d) - 1))
    : let (t = (u - (1 - d)) / d) eb + (1 - eb) * (1 + cos(180 * t)) / 2;
function ribbon(s, th) = (s[S_RBK] <= 0 || s[S_RBW] <= 0) ? 0
  : let (k = s[S_RBK], w = s[S_RBW], p = s[S_RBP], a = w * pow(abs(cos(k * th / 2)), p))
    s[S_RBMODE] == "single" ? a
    : let (b = w * pow(abs(sin(k * th / 2)), p))
      s[S_RBMODE] == "envelope" ? max(a, b) : (a + b) / max(1, pow(2, 1 - p / 2));
function teeth(s, th) = (s[S_TN] <= 0 || s[S_TH] <= 0) ? 0
  : let (L = s[S_TL], rho = s[S_TRHO], m = s[S_TM], n = s[S_TN],
         acc = sum([for (j = [0 : L]) pow(rho, j) * wave(n * pow(m, j) * th, s[S_TSHAPE])]),
         norm = sum([for (j = [0 : L]) pow(rho, j)]))
    s[S_TH] * acc / norm;
function f_full(s, th) = spiral(s, th) * (1 + ribbon(s, th)) * (1 + teeth(s, th));
function f_no_teeth(s, th) = spiral(s, th) * (1 + ribbon(s, th));
function f_core(s, th) = spiral(s, th) * (1 + teeth(s, th));

// ---- base forms, placement, re-sampling (unit: r0) -----------------------------------------
function base_point(s, t) = let (c = cos(t), sn = sin(t), form = s[S_FORM])
  form == "ellipse" ? [c, s[S_RATIO] * sn]
  : form == "superellipse" ? let (e = 2 / s[S_EXP]) [spow(c, e), s[S_RATIO] * spow(sn, e)]
  : form == "polygon" ? let (k = s[S_SIDES], sec = 360 / k, u = t - sec * floor(t / sec),
                             rp = cos(180 / k) / cos(u - 180 / k), r = (1 - s[S_ROUND]) * rp + s[S_ROUND])
                        [r * c, r * sn]
  : form == "constwidth" ? let (k = s[S_WK], a = min(s[S_WA], 0.95 / (k * k - 1)),
                                h = 1 + a * cos(k * t), hp = -a * k * sin(k * t))
                           [h * c - hp * sn, h * sn + hp * c]
  : [c, sn];
// own-frame curve scaled by the feature stack: [x, y, x_root, y_root, psi] per sample
function own_curve(s, is_stator, m) = [for (i = [0 : m - 1]) let (
    t = i * 360 / m, b = base_point(s, t), psi = mod360(atan2(b[1], b[0])),
    fac = is_stator ? 2 - f_full(s, psi) : f_full(s, psi),
    fac_r = is_stator ? 2 - f_no_teeth(s, psi) : f_core(s, psi))
  [b[0] * fac, b[1] * fac, b[0] * fac_r, b[1] * fac_r, psi]];
function placed(pts, scale, s, ix = 0, iy = 1) = let (c = cos(s[S_ROT]), sn = sin(s[S_ROT]))
  [for (p = pts) let (x = p[ix] * scale, y = p[iy] * scale) [x * c - y * sn + s[S_OX], x * sn + y * c + s[S_OY]]];
// polar re-sample about the axis: [r, psi] at each of nt axis angles (psi 0 when psis is undef)
function resample(P, psis, nt) = let (
    m = len(P), ang = [for (p = P) mod360(atan2(p[1], p[0]))], rad = [for (p = P) norm(p)],
    a0 = ang[0], u = [for (a = ang) mod360(a - a0)])
  [for (j = [0 : nt - 1]) let (
      th = mod360(j * 360 / nt - a0), k = bsearch(u, th, 0, m), k1 = (k + 1) % m,
      t0 = u[k], t1 = k == m - 1 ? u[0] + 360 : u[k1], f = t1 > t0 ? (th - t0) / (t1 - t0) : 0,
      r = rad[k] * (1 - f) + rad[k1] * f,
      psi = psis == undef ? 0
        : let (d0 = psis[k1] - psis[k], d = d0 > 180 ? d0 - 360 : d0 < -180 ? d0 + 360 : d0) mod360(psis[k] + d * f))
    [r, psi]];
function covered(psi, segs, arc, rot) = arc >= 1 ? true
  : let (half = min(1, arc) * 180 / segs)
    len([for (k = [0 : segs - 1]) let (d0 = mod360(abs(psi - rot - 360 * k / segs)), d = d0 > 180 ? 360 - d0 : d0)
         if (d <= half + 1e-9) k]) > 0;
function outer_own(own, s0, form, yk) = let (
    m = len(own), rmax = max([for (p = own) norm([p[2], p[3]]) * s0]))
  [for (i = [0 : m - 1]) let (t = i * 360 / m, p = own[i])
    form == "concentric" ? let (rr = norm([p[2], p[3]]) * s0, f = (rr + yk) / rr) [p[2] * s0 * f, p[3] * s0 * f]
    : form == "round" ? [(rmax + yk) * cos(t), (rmax + yk) * sin(t)]
    : let (k = form == "square" ? 4 : 6, sec = 360 / k, off = k == 4 ? 45 : 0,
           u = (t - off) - sec * floor((t - off) / sec), rr = (rmax + yk) / cos(u - sec / 2))
      [rr * cos(t), rr * sin(t)]];

// ---- the surfaces, solved once ----------------------------------------------------------------
function min_bore(sown, s0, nt) = min([for (q = resample(placed(sown, s0, stator_side), undef, nt)) q[0]]);
function solve_s0(sown, target, nt, sa, ma, sb, mb, it) =
  (it >= 6 || abs(mb - target) <= 1e-9) ? sb
  : let (sn = abs(mb - ma) > 1e-12 ? sb + (target - mb) * (sb - sa) / (mb - ma) : sb + (target - mb))
    solve_s0(sown, target, nt, sb, mb, sn, min_bore(sown, sn, nt), it + 1);
function surfaces(nt, m) = let (
    g0 = gap / r0,
    rown = own_curve(rotor_side, false, m),
    sown = own_curve(stator_side, true, m),
    rres = resample(placed(rown, 1, rotor_side), [for (p = rown) p[4]], nt),
    R = [for (q = rres) q[0]],
    target = max(R) + g0,
    ma = min_bore(sown, 1, nt), sb = 1 + (target - ma),
    s0 = solve_s0(sown, target, nt, 1, ma, sb, min_bore(sown, sb, nt), 0),
    sres = resample(placed(sown, s0, stator_side), [for (p = sown) p[4]], nt),
    S = [for (q = sres) q[0]], psi_s = [for (q = sres) q[1]],
    mask = [for (p = psi_s) covered(p, stator_cov_segs, stator_cov_arc, stator_cov_rot) ? 1 : 0],
    oown = outer_own(sown, s0, stator_outer_form, stator_yoke / r0),
    outer = [for (q = resample(placed(oown, 1, stator_side), undef, nt)) q[0]])
  [R, S, outer, mask, psi_s, s0];
SURF = surfaces(resolution, own_samples);
ROTOR_R = SURF[0]; BORE_R = SURF[1]; OUTER_R = SURF[2]; MASK = SURF[3]; PSI_S = SURF[4]; S0 = SURF[5];
NT = resolution;
PSI_U = [for (p = PSI_S) mod360(p - PSI_S[0])];
// own angle of the stator -> axis angle, through the re-sampled map
function theta_of_psi(psi) = let (
    v = mod360(psi - PSI_S[0]), k = bsearch(PSI_U, v, 0, NT), k1 = (k + 1) % NT,
    t0 = PSI_U[k], t1 = k == NT - 1 ? PSI_U[0] + 360 : PSI_U[k1], f = t1 > t0 ? (v - t0) / (t1 - t0) : 0)
  mod360((k + f) * 360 / NT);
function bore_at(th) = interp(BORE_R, th / 360 * NT) * r0;
function outer_at(th) = interp(OUTER_R, th / 360 * NT) * r0;
function root_at(th) = S0 * (2 - f_no_teeth(stator_side, interp(PSI_S, th / 360 * NT))) * r0;

// ---- strings: slot strings and custom stations -------------------------------------------------
function is_sep(c, seps) = len([for (s = seps) if (c == s) 1]) > 0;
function split(s, seps, i = 0, cur = "", out = []) = i >= len(s) ? (cur == "" ? out : concat(out, [cur]))
  : is_sep(s[i], seps) ? split(s, seps, i + 1, "", cur == "" ? out : concat(out, [cur]))
  : split(s, seps, i + 1, str(cur, s[i]), out);
function is_digit(c) = ord(c) >= 48 && ord(c) <= 57;
function parse_int(s, i, acc) = i < len(s) && is_digit(s[i]) ? parse_int(s, i + 1, acc * 10 + ord(s[i]) - 48) : [acc, i];
function parse_frac(s, i, acc, sc) = i < len(s) && is_digit(s[i]) ? parse_frac(s, i + 1, acc + (ord(s[i]) - 48) * sc, sc / 10) : [acc, i];
// [value, index after it]; a sign, digits, an optional fraction
function parse_num(s, i) = i >= len(s) ? [0, i]
  : s[i] == "-" || s[i] == "−" ? let (r = parse_num(s, i + 1)) [-r[0], r[1]]
  : s[i] == "+" ? parse_num(s, i + 1)
  : let (ip = parse_int(s, i, 0), j = ip[1], fp = j < len(s) && s[j] == "." ? parse_frac(s, j + 1, 0, 0.1) : [0, j])
    [ip[0] + fp[0], fp[1]];
function phase_of(c) = let (o = ord(c), u = o >= 97 ? o - 32 : o) (u >= 65 && u <= 70) ? u - 65 : undef;
// "A+", "c-", "B+x2", "A×1.5" -> [phase, sign, turns multiple]
function slot_token(t) = let (ph = phase_of(t[0])) ph == undef ? undef
  : let (sg = len(t) > 1 && (t[1] == "-" || t[1] == "−") ? -1 : 1,
         j = len(t) > 1 && (t[1] == "+" || t[1] == "-" || t[1] == "−") ? 2 : 1,
         k = j < len(t) && (t[j] == "x" || t[j] == "×") ? j + 1 : j,
         mult = k < len(t) ? parse_num(t, k)[0] : 1)
    [ph, sg, mult];
function parse_layout(s) = [for (t = split(s, [" ", ",", ";", "\n", "\t"])) let (c = slot_token(t)) if (c != undef) c];
function layout_for(n) = let (m = max(1, phases))
  pattern == "custom" ? let (toks = parse_layout(layout)) (len(toks) == 0 ? [] : [for (i = [0 : n - 1]) toks[i % len(toks)]])
  : [for (i = [0 : n - 1])
      pattern == "sequential" ? [i % m, 1, 1]
      : pattern == "paired" ? [floor(i / 2) % m, i % 2 == 0 ? 1 : -1, 1]
      : [i % m, i < n / 2 ? 1 : -1, 1]];
// "A: 0:50 90:-50; B: 30:50" -> [[phase, theta, turns], ...]
function parse_custom(s) = [for (line = split(s, [";", "\n"]))
  let (toks = split(line, [" ", ",", "\t"]), ph = len(toks) > 0 ? phase_of(toks[0][0]) : undef)
  if (ph != undef) each [for (t = [for (k = [1 : 1 : len(toks) - 1]) toks[k]])
    let (a = parse_num(t, 0)) if (a[1] < len(t) && t[a[1]] == ":")
      let (b = parse_num(t, a[1] + 1)) [ph, mod360(a[0]), b[0]]]];

// ---- windings: everything becomes conductor stations ------------------------------------------
// station [theta, turns, phase, kind]; coil [phase, sign, |turns|, a, b, centre, psi, span, kind]
n_slots = slots > 0 ? slots : stator_teeth_n;
function tooth_psi(i, n) = (stator_teeth_n > 0 && slots == 0) ? (peak(stator_teeth_shape) + 360 * i) / stator_teeth_n : 360 * (i + 0.5) / n;
function cov(psi) = covered(psi, stator_cov_segs, stator_cov_arc, stator_cov_rot);
function winding() =
  topology == "sinusoidal" ? [[], [], max(1, phases)]
  : topology == "custom" ? let (sts = parse_custom(custom_stations))
      [[for (s = sts) [s[1], s[2], s[0], "bar"]], [], range_max([for (s = sts) s[0] + 1])]
  : n_slots <= 0 ? [[], [], 0]
  : let (n = n_slots, lay = layout_for(n), m = range_max([for (c = lay) c[0] + 1]), p = 360 / n)
    len(lay) == 0 ? [[], [], 0]
    : topology == "tooth" ? let (sp = min(360, span * p))
        [[for (i = [0 : n - 1]) let (c = lay[i], psi = tooth_psi(i, n)) if (cov(psi)) let (nT = c[2] * turns * c[1])
            each [[theta_of_psi(psi - sp / 2), nT, c[0], "coil"], [theta_of_psi(psi + sp / 2), -nT, c[0], "coil"]]],
         [for (i = [0 : n - 1]) let (c = lay[i], psi = tooth_psi(i, n)) if (cov(psi)) let (nT = c[2] * turns * c[1])
            [c[0], c[1], abs(nT), theta_of_psi(psi - sp / 2), theta_of_psi(psi + sp / 2), theta_of_psi(psi), psi, sp, "tooth"]],
         m]
    : topology == "lap" ? let (y = max(1, min(n - 1, pitch)))
        [[for (i = [0 : n - 1]) let (c = lay[i], p1 = tooth_psi(i, n) + p / 2, p2 = tooth_psi((i + y) % n, n) + p / 2)
            if (cov(p1) && cov(p2)) let (nT = c[2] * turns * c[1])
            each [[theta_of_psi(p1), nT, c[0], "coil"], [theta_of_psi(p2), -nT, c[0], "coil"]]],
         [for (i = [0 : n - 1]) let (c = lay[i], p1 = tooth_psi(i, n) + p / 2, p2 = tooth_psi((i + y) % n, n) + p / 2)
            if (cov(p1) && cov(p2)) let (nT = c[2] * turns * c[1])
            [c[0], c[1], abs(nT), theta_of_psi(p1), theta_of_psi(p2), theta_of_psi(p1 + y * p / 2), p1, y * p, "lap"]],
         m]
    : [[for (i = [0 : n - 1]) let (c = lay[i], ps = tooth_psi(i, n) + p / 2) if (cov(ps))
          [theta_of_psi(ps), c[2] * turns * c[1], c[0], topology == "toroidal" ? "toroid" : "bar"]],
       [], m];
WIND = winding();
STATIONS = WIND[0]; COILS = WIND[1]; N_PHASES = WIND[2];

// ---- conductor paths: [phase, diameter, closed, [[x, y, z], ...]] -------------------------------
HZ = stack / 2 + wire_d;
function p3(th, r, z) = [r * cos(th), r * sin(th), z];
// a bar down the stack: two points when straight, five when skewed
function bar(th, r, z0, z1) = let (k = skew_deg > 0 ? 4 : 1)
  [for (s = [0 : k]) let (u = s / k, a = th + skew_deg * (u - 0.5) * (z1 > z0 ? 1 : -1)) p3(a, r, z0 + (z1 - z0) * u)];
// an end turn between two bars, a point every twelve degrees
function arc(t0, t1, r, z, fwd) = let (d0 = t1 - t0, d = fwd ? mod360(d0) : mod360(d0 + 180) - 180, n = max(3, ceil(abs(d) / 12)))
  [for (s = [1 : n - 1]) p3(t0 + d * s / n, r, z)];
// a tooth coil: a rectangle in the plane tangent to the tooth, between its tip and its root
function tooth_path(c) = let (
    tip = bore_at(c[5]), root = root_at(c[5]), rm = min(outer_at(c[5]) - wire_d, (tip + root) / 2),
    hw = max(wire_d, rm * tan(min(68.75, c[7] / 2))), ca = cos(c[5]), sa = sin(c[5]))
  [for (q = [[-hw, -HZ], [hw, -HZ], [hw, HZ], [-hw, HZ]]) [rm * ca - q[0] * sa, rm * sa + q[0] * ca, q[1]]];
function lap_path(c) = let (ra = bore_at(c[3]) + wire_d * 0.9, rb = bore_at(c[4]) + wire_d * 0.9, ro = max(ra, rb) + wire_d)
  concat(bar(c[3], ra, HZ, -HZ), arc(c[3], c[4], ro, -HZ - wire_d * 1.5, true), bar(c[4], rb, -HZ, HZ), arc(c[4], c[3], ro, HZ + wire_d * 1.5, false));
// a wave winding: down one slot, over, up the next, round the machine; an even count closes on itself
function wave_path(sts) = let (n = len(sts), closes = n % 2 == 0)
  [for (k = [0 : n - 1]) let (s = sts[k], r = bore_at(s[0]) + wire_d * 0.9, down = k % 2 == 0)
    each concat(bar(s[0], r, down ? HZ : -HZ, down ? -HZ : HZ),
                (k < n - 1 || closes) ? let (nx = sts[(k + 1) % n]) arc(s[0], nx[0], max(r, bore_at(nx[0]) + wire_d * 0.9) + wire_d, down ? -HZ - wire_d * 1.5 : HZ + wire_d * 1.5, true) : [])];
// a toroidal belt: one rectangular turn through the yoke per ten turns, side by side
function toroid_legs(s) = let (rin = bore_at(s[0]) + wire_d * 0.9, rout = outer_at(s[0]) + wire_d * 0.9,
    nl = max(2, min(8, round(abs(s[1]) / 10))), dth = wire_d * 1.3 / rin * 180 / PI)
  [for (q = [0 : nl - 1]) let (th = s[0] + (q - (nl - 1) / 2) * dth)
    [p3(th, rin, -HZ), p3(th, rin, HZ), p3(th + dth * 0.5, rout, HZ), p3(th + dth * 0.5, rout, -HZ)]];
function conductor_paths() =
  topology == "sinusoidal" ? let (nb = 48, m = N_PHASES)
    [for (p = [0 : m - 1]) for (b = [0 : nb - 1]) let (th = 360 * (b + 0.5) / nb, v = cos(pole_pairs * th - 360 * p / m))
      if (MASK[round(th / 360 * NT) % NT] == 1 && abs(v) >= 0.08)
        [p, wire_d * sqrt(abs(v)), false, bar(th, bore_at(th) + wire_d * 0.9 + p * wire_d * 1.1, -HZ, HZ)]]
  : topology == "tooth" ? [for (c = COILS) [c[0], wire_d, true, tooth_path(c)]]
  : topology == "lap" ? [for (c = COILS) [c[0], wire_d, true, lap_path(c)]]
  : topology == "wave" ? [for (p = [0 : 1 : N_PHASES - 1]) let (sts = sort_by([for (s = STATIONS) if (s[2] == p) s], 0))
      if (len(sts) >= 2) [p, wire_d, len(sts) % 2 == 0, wave_path(sts)]]
  : topology == "toroidal" ? [for (s = STATIONS) for (leg = toroid_legs(s)) [s[2], wire_d, true, leg]]
  : [for (s = STATIONS) [s[2], wire_d * min(2, sqrt(abs(s[1]) / turns)), false, bar(s[0], bore_at(s[0]) + wire_d * 0.9, -HZ, HZ)]];
PATHS = (phases > 0 || topology == "custom") ? conductor_paths() : [];

// ---- geometry ----------------------------------------------------------------------------------
function polar(rs) = [for (i = [0 : NT - 1]) let (a = i * 360 / NT) [rs[i] * r0 * cos(a), rs[i] * r0 * sin(a)]];
// covered index runs of the mask; a run may pass the last sample and wrap
function runs(i = 0, start = -1, out = []) = i >= NT ? (start >= 0 ? concat(out, [[start, NT - 1]]) : out)
  : MASK[i] == 1 && start < 0 ? runs(i + 1, i, out)
  : MASK[i] == 0 && start >= 0 ? runs(i + 1, -1, concat(out, [[start, i - 1]]))
  : runs(i + 1, start, out);
function joined_runs() = let (r = runs())
  (len(r) > 1 && r[0][0] == 0 && r[len(r) - 1][1] == NT - 1)
    ? concat([[r[len(r) - 1][0], r[0][1] + NT]], [for (k = [1 : 1 : len(r) - 2]) r[k]]) : r;
function pt(rs, i) = let (k = i % NT, a = k * 360 / NT) [rs[k] * r0 * cos(a), rs[k] * r0 * sin(a)];
function segment_poly(seg) = concat([for (i = [seg[0] : seg[1]]) pt(OUTER_R, i)], [for (i = [seg[1] : -1 : seg[0]]) pt(BORE_R, i)]);
full_ring = min(MASK) == 1;

module rotor() {
  rotate([0, 0, phi]) linear_extrude(height = stack, center = true) polygon(polar(ROTOR_R));
}
module stator() {
  linear_extrude(height = stack, center = true)
    if (full_ring) polygon(points = concat(polar(OUTER_R), polar(BORE_R)), paths = [[for (i = [0 : NT - 1]) i], [for (i = [0 : NT - 1]) NT + i]]);
    else for (seg = joined_runs()) polygon(segment_poly(seg));
}
// A bundle swept along its path as one polyhedron: a ring of sweep_sides vertices at every
// point, each ring's frame carried from the last (parallel transport, so the tube does not
// twist), a corner's ring widened by its mitre. One polyhedron per bundle is what keeps a
// render on CGAL in seconds; hulls of spheres (sweep_hulls) are the slow, robust alternative.
function unit(v) = let (l = norm(v)) l < 1e-12 ? [0, 0, 0] : v / l;
function tangents(pts, closed) = let (n = len(pts)) [for (i = [0 : n - 1]) let (
    prev = closed ? pts[(i - 1 + n) % n] : pts[max(i - 1, 0)], next = closed ? pts[(i + 1) % n] : pts[min(i + 1, n - 1)],
    a = unit(pts[i] - prev), b = unit(next - pts[i]), t = unit(a + b))
  norm(t) < 1e-6 ? (norm(b) > 0 ? b : a) : t];
function mitres(pts, closed) = let (n = len(pts)) [for (i = [0 : n - 1]) let (
    prev = closed ? pts[(i - 1 + n) % n] : pts[max(i - 1, 0)], next = closed ? pts[(i + 1) % n] : pts[min(i + 1, n - 1)],
    a = unit(pts[i] - prev), b = unit(next - pts[i]), c = (norm(a) < 1e-6 || norm(b) < 1e-6) ? 1 : clamp(a * b, -1, 1))
  min(1.5, 1 / max(0.5, sqrt((1 + c) / 2)))];
function first_normal(t) = unit(cross(t, abs(t[2]) < 0.9 ? [0, 0, 1] : [1, 0, 0]));
function frames(ts, i = 0, n0 = undef, acc = []) = i >= len(ts) ? acc
  : let (t = ts[i], p = n0 == undef ? first_normal(t) : n0 - (n0 * t) * t, n = norm(p) < 1e-6 ? first_normal(t) : unit(p))
    frames(ts, i + 1, n, concat(acc, [[n, cross(t, n)]]));
function tube_points(pts, d, closed) = let (ts = tangents(pts, closed), fs = frames(ts), ms = mitres(pts, closed), k = sweep_sides)
  [for (i = [0 : len(pts) - 1]) for (j = [0 : k - 1]) let (a = 360 * j / k, f = fs[i])
    pts[i] + (d / 2) * ms[i] * (cos(a) * f[0] + sin(a) * f[1])];
function tube_faces(n, closed) = let (k = sweep_sides, m = closed ? n : n - 1)
  concat(
    [for (i = [0 : m - 1]) for (j = [0 : k - 1]) let (i1 = (i + 1) % n, j1 = (j + 1) % k)
      each [[i * k + j, i1 * k + j, i1 * k + j1], [i * k + j, i1 * k + j1, i * k + j1]]],
    closed ? [] : [[for (j = [0 : k - 1]) j], [for (j = [k - 1 : -1 : 0]) (n - 1) * k + j]]);
module tube(pts, d, closed) {
  polyhedron(points = tube_points(pts, d, closed), faces = tube_faces(len(pts), closed), convexity = 4);
}
module sweep(pts, d, closed) {
  n = len(pts);
  if (sweep_hulls || n < 2) {
    for (i = [0 : n - 2]) hull() { translate(pts[i]) sphere(d = d, $fn = sweep_sides); translate(pts[i + 1]) sphere(d = d, $fn = sweep_sides); }
    if (closed) hull() { translate(pts[n - 1]) sphere(d = d, $fn = sweep_sides); translate(pts[0]) sphere(d = d, $fn = sweep_sides); }
  } else tube(pts, d, closed);
}
module windings() {
  for (c = PATHS) color(phase_colors[c[0] % 6]) sweep(c[3], c[1], c[2]);
}
module airgap() {
  if (show_rotor) color("#2a3240") rotor();
  if (show_stator) color("#3d4958") stator();
  if (show_windings) windings();
}

airgap();

if (echo_surfaces) {
  echo(s0 = S0 * r0, rotor_r = [for (v = ROTOR_R) v * r0], bore_r = [for (v = BORE_R) v * r0], outer_r = [for (v = OUTER_R) v * r0],
       mask = MASK, psi_s = PSI_S, stations = STATIONS, paths = PATHS);
}
