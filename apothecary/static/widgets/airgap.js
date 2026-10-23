/* The Airgap panel: a rotor/stator pair explored as a field, torque and dynamics model.
 *
 * The geometry is the airgap part's (parts/airgap/airgap.scad): its top-level assignments,
 * read from the SCAD editor's text while the part is being edited and from the part's own
 * file otherwise, so what the panel analyses is what the editor's check and render see.
 * The panel computes in the browser -- surfaces, winding functions, co-energy and torque
 * tables, a run of the rotor and the stator's modes -- in the same degrees and with the
 * same nudges as the SCAD, and says its figures as one metrics document
 * (airgap/metrics/1), which apothecary.airgap_metrics validates and renders. The rig --
 * excitation, drive, load, bearing, mount, actuation, playback -- is a document of its own
 * in the panel, as the geometry is a text: one box, not forty sliders.
 *
 * Its verbs are cells of the ring (Panels › Airgap): Play, Sweep, To editor (the panel's
 * values written into the part's text), From editor (the text read again), Copy SCAD, Copy
 * metrics, Reset. Nothing here is fetched from outside the page.
 *
 * mountAirgap(slot, { base, say, world, sections }) -> handle { act(verb), textChanged(text),
 *   metrics(), values(), setValues(values), load(), preset(id), redraw() }
 * world: { text(): Promise<string>, editing(): bool, write(values): bool, edit(): bool,
 *   showSection(id) }
 * sections: an element per section of the Airgap's entry in apothecary/systems.py, each
 *   the window the panel fills with that section (each a `data-section` block of the
 *   markup below); the slot holds the machine, its scrub and the verbs.
 */
import { parseAssignments, lastOf, writeValues } from '/static/widgets/assignments.js';

const SCAD_NAMES = { scale: { r0: 'r0', stack: 'stack' },
  side: ['baseForm', 'baseRatio', 'baseExp', 'baseSides', 'baseRound', 'baseWidthK', 'baseWidthA', 'rot', 'offX', 'offY',
    'spiralB', 'spiralK', 'spiralS', 'ribK', 'ribW', 'ribP', 'ribMode', 'teethN', 'teethH', 'teethL', 'teethM', 'teethRho', 'teethShape'],
  stator: { covSegs: 'stator_cov_segs', covArc: 'stator_cov_arc', covRot: 'stator_cov_rot', outerForm: 'stator_outer_form', yoke: 'stator_yoke' },
  wind: { topology: 'topology', phases: 'phases', pattern: 'pattern', layout: 'layout', custom: 'custom_stations', turns: 'turns',
    span: 'span', pitch: 'pitch', coils: 'slots', skew: 'skew_deg', wire: 'wire_d', polePairs: 'pole_pairs' } };
const snake = (k) => k.replace(/[A-Z]/g, (c) => '_' + c.toLowerCase());
// The rig: what the panel runs the geometry under. Keys are DYN_DEFAULT's and the excitation's.
const RIG_EXCITE = ['excite', 'current', 'advance'];
const SWEEP_METRIC = { mean_torque: 'meanT', ripple: 'ripple', peak_b: 'bmax', mean_coenergy: 'meanW', dominant_order: 'dom' };

export function mountAirgap(slot, { base, say, world, sections }) {
const TAU=Math.PI*2, MU0=4e-7*Math.PI;
const NT=720, NPHI=360, NORD=96, NSHOW=64, MOWN=2880; // polar samples, rotor angles, harmonic orders, orders drawn, own-frame samples
// Where the panel's elements are: its slot, and each section's window.
const roots=[slot];
const $=id=>{for(const r of roots){const e=r.querySelector('[data-airgap="'+id+'"]');if(e)return e;}return null;};
const PH_LETTERS='ABCDEF';
function el(tag,attrs,text){const e=document.createElement(tag);if(attrs)for(const k in attrs)e.setAttribute(k,attrs[k]);if(text!=null)e.textContent=text;return e;}
/* ---------- parameter model ---------- */
const SIDE_DEFAULT={baseForm:'circle',baseRatio:0.8,baseExp:4,baseSides:4,baseRound:0.3,baseWidthK:3,baseWidthA:0.08,rot:0,offX:0,offY:0,
  spiralB:0,spiralK:2,spiralS:0.8,ribK:0,ribW:0.1,ribP:1,ribMode:'envelope',teethN:0,teethH:0.08,teethL:0,teethM:3,teethRho:0.5,teethShape:'trap',
  covSegs:1,covArc:1,covRot:0,outerForm:'concentric',yoke:6};
const WIND_DEFAULT={topology:'tooth',phases:3,pattern:'diametral',layout:'',turns:50,span:0.6,pitch:1,coils:0,skew:0,wire:1.2,
  custom:'A: 30:+50 150:-50\nB: 90:+50 210:-50\nC: 150:+50 270:-50',excite:'auto',current:5,polePairs:4,advance:0};
const SCALE_DEFAULT={r0:30,stack:20};
const BASE_FORMS=[['circle','circle'],['ellipse','ellipse'],['superellipse','superellipse (squircle)'],['polygon','rounded polygon'],['constwidth','constant-width (Reuleaux-like)']];
const BASE_ITEMS=[
  {key:'baseForm',label:'Base form',type:'select',options:BASE_FORMS},
  {key:'baseRatio',label:'Axis ratio b/a',min:0.4,max:1,step:0.01,show:p=>p.baseForm==='ellipse'||p.baseForm==='superellipse'},
  {key:'baseExp',label:'Superellipse exponent',min:1.5,max:8,step:0.1,show:p=>p.baseForm==='superellipse'},
  {key:'baseSides',label:'Sides',min:3,max:12,step:1,show:p=>p.baseForm==='polygon'},
  {key:'baseRound',label:'Corner rounding',min:0,max:1,step:0.01,show:p=>p.baseForm==='polygon'},
  {key:'baseWidthK',label:'Support lobes (odd = constant width)',min:3,max:9,step:1,show:p=>p.baseForm==='constwidth'},
  {key:'baseWidthA',label:'Support amplitude',min:0,max:0.2,step:0.005,show:p=>p.baseForm==='constwidth'}];
const PLACE_ITEMS=[
  {key:'rot',label:'Rotation (°)',min:-180,max:180,step:1},
  {key:'offX',label:'Offset x (×r₀)',min:-0.4,max:0.4,step:0.005},
  {key:'offY',label:'Offset y (×r₀)',min:-0.4,max:0.4,step:0.005}];
const FEATURE_GROUPS=[
  {group:'Nautilus spiral',items:[
    {key:'spiralB',label:'Growth per arm',min:0,max:0.8,step:0.01},
    {key:'spiralK',label:'Arms',min:1,max:8,step:1},
    {key:'spiralS',label:'Step sharpness',min:0,max:1,step:0.01}]},
  {group:'Möbius ribbon',items:[
    {key:'ribK',label:'Half-twists',min:0,max:12,step:1},
    {key:'ribW',label:'Ribbon width (×r₀)',min:0,max:0.3,step:0.005},
    {key:'ribP',label:'Edge power',min:0.5,max:3,step:0.05},
    {key:'ribMode',label:'Interlock',type:'select',options:[['single','single ribbon'],['envelope','two ribbons, interlocked'],['woven','two ribbons, woven']]}]},
  {group:'Fractal gearing',items:[
    {key:'teethN',label:'Teeth',min:0,max:48,step:1},
    {key:'teethH',label:'Tooth depth (×r₀)',min:0,max:0.25,step:0.005},
    {key:'teethL',label:'Fractal levels',min:0,max:4,step:1},
    {key:'teethM',label:'Sub-tooth ratio',min:2,max:5,step:1},
    {key:'teethRho',label:'Level decay',min:0,max:0.9,step:0.01},
    {key:'teethShape',label:'Tooth form',type:'select',options:[['trap','trapezoid'],['sine','sine'],['tri','triangle'],['saw','ratchet']]}]}
];
const ROTOR_SPECS=[{group:'Base form',items:BASE_ITEMS},{group:'Placement (eccentric when offset)',items:PLACE_ITEMS}].concat(FEATURE_GROUPS);
const STATOR_SPECS=[{group:'Base form',items:BASE_ITEMS},{group:'Placement',items:PLACE_ITEMS},
  {group:'Coverage (segmented stator)',items:[
    {key:'covSegs',label:'Segments',min:1,max:12,step:1},
    {key:'covArc',label:'Covered fraction of each segment',min:0.1,max:1,step:0.01},
    {key:'covRot',label:'Segment rotation (°)',min:-180,max:180,step:1}]},
  {group:'Frame',items:[
    {key:'outerForm',label:'Outer form',type:'select',options:[['concentric','concentric with bore'],['round','round'],['square','square frame'],['hex','hexagonal frame']]},
    {key:'yoke',label:'Yoke thickness (mm)',min:1,max:40,step:0.5}]}].concat(FEATURE_GROUPS);
const TOPOLOGIES=[['tooth','tooth coils (one loop per tooth)'],['lap','lap coils spanning slots'],['wave','wave winding (series zigzag)'],['toroidal','toroidal turns around the yoke'],['sinusoidal','ideal sinusoidal sheet'],['custom','custom conductor stations']];
const isSlotTopo=w=>w.topology==='tooth'||w.topology==='lap'||w.topology==='wave'||w.topology==='toroidal';
const WIND_SPECS=[
  {group:'Conductor arrangement',items:[
    {key:'topology',label:'Topology',type:'select',options:TOPOLOGIES},
    {key:'phases',label:'Phases',min:1,max:6,step:1,show:w=>isSlotTopo(w)||w.topology==='sinusoidal'},
    {key:'pattern',label:'Pattern',type:'select',options:[['sequential','sequential  A B C A B C'],['paired','paired  A+ A− B+ B−'],['diametral','diametral  A B C A′ B′ C′'],['custom','custom']],show:isSlotTopo},
    {key:'layout',label:'Slot string (phase, polarity, optional turns ×)',type:'text',show:isSlotTopo},
    {key:'custom',label:'Stations per phase: letter, then angle°:±turns',type:'textarea',show:w=>w.topology==='custom'},
    {key:'turns',label:'Turns per coil / station',min:1,max:300,step:1,show:w=>w.topology!=='custom'},
    {key:'span',label:'Coil span (× tooth pitch)',min:0.2,max:1,step:0.02,show:w=>w.topology==='tooth'},
    {key:'pitch',label:'Coil pitch (slots)',min:1,max:24,step:1,show:w=>w.topology==='lap'},
    {key:'coils',label:'Slots (0 = one per stator tooth)',min:0,max:48,step:1,show:isSlotTopo},
    {key:'skew',label:'Skew (° mechanical)',min:0,max:60,step:1},
    {key:'wire',label:'Wire bundle Ø (mm)',min:0.4,max:6,step:0.1}]},
  {group:'Excitation',items:[
    {key:'excite',label:'Scheme',type:'select',options:[['auto','auto-commutated (rising L)'],['sin','sinusoidal m-phase'],['dc','phase A, DC'],['uniform','uniform MMF (reluctance only)']]},
    {key:'current',label:'Phase current (A)',min:0,max:30,step:0.5},
    {key:'polePairs',label:'Electrical pole pairs (sinusoidal)',min:1,max:24,step:1,show:w=>w.excite==='sin'||w.topology==='sinusoidal'},
    {key:'advance',label:'Advance (° electrical)',min:-180,max:180,step:5,show:w=>w.excite==='sin'}]}
];
const DYN_DEFAULT={mode:'free',rpmRef:600,omega0:300,inertiaScale:1,loadT:2,viscous:5,coulomb:0.5,
  comm:'locked',adv0:0,advSlope:0,fieldRpm:600,stepRate:200,stepsPer:3,
  bearK:300,bearZeta:0.05,clearance:5,unbalance:1,ambMode:'none',ambKp:500,ambKd:50,ambFmax:50,orbitR:50,orbitF:20,
  axialK:200,axialZeta:0.1,axialAct:'none',axialAmp:5,axialFreq:20,axialKp:200,
  statorFree:'free',statorFn:1500,statorZeta:0.03,actPattern:'none',actDof:'0',actAmp:20,actFreq:50,actWave:1,actDir:'1',
  carrierRpm:0,ditherAmp:0,ditherFreq:30,torMode:'compliant',torFn:400,torZeta:0.05,
  duration:300,exaggerate:1000,timeScale:'0.01',playback:'spin',spinRate:24};
const DYN_SPECS=[
  {group:'Rotor drive and load',items:[
    {key:'mode',label:'Speed',type:'select',options:[['free','free run at the commutation'],['regulate','regulate to a target by current scaling']]},
    {key:'rpmRef',label:'Target speed (rpm)',min:10,max:6000,step:10,show:d=>d.mode==='regulate'},
    {key:'omega0',label:'Initial speed (rpm)',min:0,max:6000,step:10},
    {key:'inertiaScale',label:'Inertia (× rotor’s own J)',min:0.1,max:20,step:0.1},
    {key:'loadT',label:'Load torque (mN·m)',min:0,max:500,step:0.5},
    {key:'viscous',label:'Viscous drag (µN·m·s)',min:0,max:500,step:1},
    {key:'coulomb',label:'Coulomb friction (mN·m)',min:0,max:50,step:0.5}]},
  {group:'Windings · commutation (electro, engineered)',items:[
    {key:'comm',label:'Field motion',type:'select',options:[['locked','locked to the rotor (self-commutated)'],['open','open-loop rotating field (synchronous)'],['stepped','stepped field (stepper drive)']]},
    {key:'adv0',label:'Extra advance (° electrical)',min:-180,max:180,step:5},
    {key:'advSlope',label:'Advance per 1000 rpm (° el)',min:-90,max:90,step:1,show:d=>d.comm==='locked'},
    {key:'fieldRpm',label:'Field speed (rpm, mechanical)',min:-6000,max:6000,step:10,show:d=>d.comm==='open'},
    {key:'stepRate',label:'Step rate (steps/s)',min:1,max:3000,step:1,show:d=>d.comm==='stepped'},
    {key:'stepsPer',label:'Steps per commutation period',min:1,max:12,step:1,show:d=>d.comm==='stepped'}]},
  {group:'Rotor radial · bearing (unintentional) and active magnetic bearing (electro)',items:[
    {key:'bearK',label:'Bearing stiffness (kN/m)',min:0,max:5000,step:5},
    {key:'bearZeta',label:'Bearing damping ratio',min:0,max:1,step:0.01},
    {key:'clearance',label:'Bearing clearance (µm)',min:0,max:200,step:1},
    {key:'unbalance',label:'Mass unbalance (g·mm)',min:0,max:50,step:0.5},
    {key:'ambMode',label:'Magnetic bearing',type:'select',options:[['none','off'],['hold','hold the centre (PD)'],['orbit','command a circular orbit']]},
    {key:'ambKp',label:'AMB stiffness Kp (kN/m)',min:0,max:5000,step:10,show:d=>d.ambMode!=='none'},
    {key:'ambKd',label:'AMB damping Kd (N·s/m)',min:0,max:2000,step:5,show:d=>d.ambMode!=='none'},
    {key:'ambFmax',label:'AMB force limit (N)',min:1,max:2000,step:1,show:d=>d.ambMode!=='none'},
    {key:'orbitR',label:'Orbit radius (µm)',min:0,max:500,step:5,show:d=>d.ambMode==='orbit'},
    {key:'orbitF',label:'Orbit frequency (Hz)',min:0.5,max:500,step:0.5,show:d=>d.ambMode==='orbit'}]},
  {group:'Rotor axial · pull-in (unintentional) and axial actuator (electro)',items:[
    {key:'axialK',label:'Axial bearing stiffness (kN/m)',min:0,max:5000,step:5},
    {key:'axialZeta',label:'Axial damping ratio',min:0,max:1,step:0.01},
    {key:'axialAct',label:'Axial actuator',type:'select',options:[['none','off'],['force','sinusoidal force (voice coil)'],['servo','position servo to a sinusoidal target']]},
    {key:'axialAmp',label:'Amplitude (N for force, µm for servo)',min:0,max:500,step:1,show:d=>d.axialAct!=='none'},
    {key:'axialFreq',label:'Axial frequency (Hz)',min:0.5,max:1000,step:0.5,show:d=>d.axialAct!=='none'},
    {key:'axialKp',label:'Servo stiffness (kN/m)',min:1,max:5000,step:5,show:d=>d.axialAct==='servo'}]},
  {group:'Stator carrier (mechanical, engineered) and torsional mount (unintentional)',items:[
    {key:'carrierRpm',label:'Carrier speed (rpm)',min:-3000,max:3000,step:10},
    {key:'ditherAmp',label:'Carrier dither amplitude (°)',min:0,max:30,step:0.5},
    {key:'ditherFreq',label:'Carrier dither frequency (Hz)',min:0.5,max:500,step:0.5,show:d=>d.ditherAmp>0},
    {key:'torMode',label:'Torsional mount',type:'select',options:[['compliant','compliant, rocks under the reaction torque'],['rigid','rigid']]},
    {key:'torFn',label:'Torsional natural frequency (Hz)',min:5,max:3000,step:5,show:d=>d.torMode==='compliant'},
    {key:'torZeta',label:'Torsional damping ratio',min:0.005,max:1,step:0.005,show:d=>d.torMode==='compliant'}]},
  {group:'Stator yoke · modes (unintentional) and actuation (mechanical, engineered)',items:[
    {key:'statorFree',label:'Yoke modes',type:'select',options:[['free','compliant, free to vibrate'],['locked','rigid']]},
    {key:'statorFn',label:'Modal natural frequency (Hz)',min:100,max:8000,step:50,show:d=>d.statorFree==='free'},
    {key:'statorZeta',label:'Modal damping ratio',min:0.005,max:0.5,step:0.005,show:d=>d.statorFree==='free'},
    {key:'actPattern',label:'Actuation',type:'select',options:[['none','none'],['single','drive one mode'],['wave','travelling wave across the yoke']]},
    {key:'actDof',label:'Driven mode',type:'select',options:[['0','—']],show:d=>d.actPattern==='single'},
    {key:'actAmp',label:'Stroke amplitude (µm)',min:0,max:500,step:5,show:d=>d.actPattern!=='none'},
    {key:'actFreq',label:'Stroke frequency (Hz)',min:0.5,max:2000,step:0.5,show:d=>d.actPattern!=='none'},
    {key:'actWave',label:'Wave number (segments per wavelength)',min:1,max:6,step:1,show:d=>d.actPattern==='wave'},
    {key:'actDir',label:'Wave direction',type:'select',options:[['1','with rotation'],['-1','against rotation']],show:d=>d.actPattern==='wave'}]},
  {group:'Simulation and playback',items:[
    {key:'duration',label:'Window (ms)',min:20,max:2000,step:10},
    {key:'exaggerate',label:'Motion exaggeration on screen (×)',min:1,max:5000,step:1},
    {key:'timeScale',label:'Playback speed',type:'select',options:[['1','real time'],['0.1','1/10'],['0.01','1/100'],['0.001','1/1000']]},
    {key:'playback',label:'Scrub and Play move',type:'select',options:[['spin','the rotor angle'],['dyn','time through the run']]},
    {key:'spinRate',label:'Spin rate (°/s)',min:1,max:720,step:1}]}
];
const SCALE_SPECS=[
  {key:'r0',label:'Rotor base radius r₀ (mm)',min:5,max:150,step:0.5,path:'scale.r0'},
  {key:'stack',label:'Stack length ℓ (mm)',min:2,max:200,step:0.5,path:'scale.stack'},
  {key:'gap',label:'Nominal air gap g₀ (mm)',min:0.2,max:10,step:0.1,path:'gap'}
];
const PRESETS=[
  {id:'mobius',name:'Möbius nautilus · fractal stator',rotor:{spiralB:0.35,spiralK:2,spiralS:0.85,ribK:3,ribW:0.12,ribMode:'envelope'},stator:{teethN:12,teethH:0.08,teethL:3,teethM:3,teethRho:0.5,teethShape:'trap'},wind:{phases:3,pattern:'diametral',excite:'auto'},gap:1.5},
  {id:'srm',name:'6/4 switched reluctance',rotor:{teethN:4,teethH:0.15,teethShape:'trap'},stator:{teethN:6,teethH:0.12,teethShape:'trap'},wind:{phases:3,pattern:'diametral',excite:'auto'},gap:0.9},
  {id:'ellipse',name:'Elliptical bore · lap winding',rotor:{teethN:4,teethH:0.15,teethShape:'trap'},stator:{baseForm:'ellipse',baseRatio:0.88,teethN:12,teethH:0.06,teethShape:'trap',outerForm:'round',yoke:7},wind:{topology:'lap',pitch:3,phases:3,pattern:'custom',layout:'A+ A+ C- C- B+ B+ A- A- C+ C+ B- B-',excite:'auto'},gap:1.0},
  {id:'ccore',name:'Two C-cores · toroidal belts',rotor:{teethN:6,teethH:0.14,teethShape:'trap'},stator:{covSegs:2,covArc:0.55,covRot:0,outerForm:'round',yoke:9},wind:{topology:'toroidal',coils:8,phases:2,pattern:'paired',turns:40,excite:'auto'},gap:1.0},
  {id:'wave',name:'Square frame · 12-slot wave',rotor:{teethN:4,teethH:0.14,teethShape:'sine'},stator:{teethN:12,teethH:0.06,teethShape:'trap',outerForm:'square',yoke:7},wind:{topology:'wave',pattern:'custom',layout:'A+ A+ B- B- C+ C+ A- A- B+ B+ C- C-',turns:30,excite:'sin',polePairs:2,advance:0},gap:1.0},
  {id:'reuleaux',name:'Eccentric Reuleaux rotor',rotor:{baseForm:'constwidth',baseWidthK:3,baseWidthA:0.11,offX:0.08},stator:{teethN:9,teethH:0.1,teethShape:'trap'},wind:{phases:3,pattern:'sequential',excite:'auto'},gap:1.2},
  {id:'sheet',name:'Sinusoidal sheet · 10-pole',rotor:{teethN:10,teethH:0.08,teethShape:'sine'},stator:{},wind:{topology:'sinusoidal',phases:3,polePairs:5,turns:60,excite:'sin',advance:90},gap:0.9},
  {id:'fractal',name:'Fractal on fractal',rotor:{teethN:8,teethH:0.14,teethL:3,teethM:2,teethRho:0.6,teethShape:'tri'},stator:{teethN:9,teethH:0.1,teethL:3,teethM:2,teethRho:0.6,teethShape:'tri'},wind:{phases:3,pattern:'sequential',excite:'auto'},gap:0.9},
  {id:'whirl',name:'Soft bearing · whirl to touchdown',rotor:{teethN:4,teethH:0.15,teethShape:'trap'},stator:{teethN:6,teethH:0.12,teethShape:'trap'},wind:{phases:3,pattern:'diametral',excite:'auto'},dyn:{bearK:20,clearance:20,unbalance:5,omega0:600,exaggerate:40},gap:0.4},
  {id:'stepper',name:'Stepped field · 6/4 as a stepper',rotor:{teethN:4,teethH:0.15,teethShape:'trap'},stator:{teethN:6,teethH:0.12,teethShape:'trap'},wind:{phases:3,pattern:'diametral',excite:'auto'},dyn:{comm:'stepped',stepRate:10,stepsPer:3,omega0:0,loadT:1,duration:800,exaggerate:300},gap:0.9},
  {id:'sync',name:'Open-loop synchronous · pull-out',rotor:{teethN:10,teethH:0.08,teethShape:'sine'},stator:{},wind:{topology:'sinusoidal',phases:3,polePairs:5,turns:60,excite:'sin',advance:90},dyn:{comm:'open',fieldRpm:1500,omega0:1500,loadT:300,duration:400,exaggerate:300},gap:0.9},
  {id:'amb',name:'Soft bearing rescued by an AMB',rotor:{teethN:4,teethH:0.15,teethShape:'trap'},stator:{teethN:6,teethH:0.12,teethShape:'trap'},wind:{phases:3,pattern:'diametral',excite:'auto'},dyn:{bearK:20,clearance:20,unbalance:5,omega0:600,ambMode:'hold',ambKp:400,ambKd:80,ambFmax:60,exaggerate:40},gap:0.4},
  {id:'peristaltic',name:'Travelling-wave yoke · peristaltic drive',rotor:{baseForm:'ellipse',baseRatio:0.9,rot:90},stator:{},wind:{excite:'uniform',turns:50,current:8},dyn:{actPattern:'wave',actAmp:150,actFreq:3,actDir:'1',statorFree:'locked',loadT:0,coulomb:0.2,omega0:90,duration:1500,exaggerate:20},gap:1.5},
  {id:'resonance',name:'Yoke resonance at 12× rotation',rotor:{spiralB:0.35,spiralK:2,spiralS:0.85,ribK:3,ribW:0.12,ribMode:'envelope'},stator:{teethN:12,teethH:0.08,teethL:3,teethM:3,teethRho:0.5,teethShape:'trap'},wind:{phases:3,pattern:'diametral',excite:'auto'},dyn:{mode:'regulate',rpmRef:1500,omega0:1500,statorFn:300,statorZeta:0.01,duration:400,exaggerate:3000},gap:1.5}
];
function presetState(p){return {rotor:Object.assign({},SIDE_DEFAULT,p.rotor),stator:Object.assign({},SIDE_DEFAULT,p.stator),wind:Object.assign({},WIND_DEFAULT,p.wind),scale:Object.assign({},SCALE_DEFAULT,p.scale),dyn:Object.assign({},DYN_DEFAULT,p.dyn),gap:p.gap,phi:0};}
let state=presetState(PRESETS[0]);state.phi=0;
let sweepCfg={x:'stator.teethN',xmin:3,xmax:24,y:'rotor.ribK',ymin:0,ymax:12,metric:'meanT'};
let activePreset='mobius';

/* ---------- surface features (own frame, dimensionless) ---------- */
const WAVES={
  sine:x=>0.5+0.5*Math.sin(x),
  trap:x=>{const v=2.5*Math.sin(x);return 0.5+0.5*(v>1?1:v<-1?-1:v);},
  tri:x=>{let u=(x/Math.PI)%2;if(u<0)u+=2;return 1-Math.abs(u-1);},
  saw:x=>{const v=x/TAU+1e-9;return v-Math.floor(v);}
};
const PEAK={sine:Math.PI/2,trap:Math.PI/2,tri:Math.PI,saw:TAU*0.999};
function makeProfile(p){
  const K=p.spiralK|0,b=+p.spiralB,d=Math.max(0.02,0.5*(1-p.spiralS)),eb=Math.exp(-b);
  const k=p.ribK|0,w=+p.ribW,pw=+p.ribP,mode=p.ribMode;
  const wovenNorm=Math.max(1,Math.pow(2,1-pw/2));
  const N=p.teethN|0,h=+p.teethH,L=p.teethL|0,m=p.teethM|0,rho=+p.teethRho,wave=WAVES[p.teethShape]||WAVES.trap;
  let norm=0,aa=1;for(let j=0;j<=L;j++){norm+=aa;aa*=rho;}
  const sp=b>0?th=>{let u=(K*th/TAU)%1;if(u<0)u+=1;if(u<1-d)return Math.exp(b*(u/(1-d)-1));const t=(u-(1-d))/d;return eb+(1-eb)*(1+Math.cos(Math.PI*t))/2;}:()=>1;
  const hasRibbon=k>0&&w>0;
  const rbA=hasRibbon?th=>w*Math.pow(Math.abs(Math.cos(k*th/2)),pw):()=>0;
  const rbB=(hasRibbon&&mode!=='single')?th=>w*Math.pow(Math.abs(Math.sin(k*th/2)),pw):()=>0;
  const rb=mode==='single'?rbA:mode==='envelope'?th=>Math.max(rbA(th),rbB(th)):th=>(rbA(th)+rbB(th))/wovenNorm;
  const te=(N>0&&h>0)?th=>{let acc=0,a=1,f=N;for(let j=0;j<=L;j++){acc+=a*wave(f*th);a*=rho;f*=m;}return h*acc/norm;}:()=>0;
  return {sp,rb,rbA,rbB,te,core:th=>sp(th)*(1+te(th)),noTeeth:th=>sp(th)*(1+rb(th)),full:th=>sp(th)*(1+rb(th))*(1+te(th)),hasRibbon,mode,k,w};
}
function basePoint(p,t){ // base curve in its own frame, unit scale
  const c=Math.cos(t),s=Math.sin(t);
  switch(p.baseForm){
    case 'ellipse':return [c,p.baseRatio*s];
    case 'superellipse':{const n=p.baseExp;return [Math.sign(c)*Math.pow(Math.abs(c),2/n),p.baseRatio*Math.sign(s)*Math.pow(Math.abs(s),2/n)];}
    case 'polygon':{const k=p.baseSides|0,sec=TAU/k;let u=t%sec;if(u<0)u+=sec;const rp=Math.cos(Math.PI/k)/Math.cos(u-Math.PI/k);const r=(1-p.baseRound)*rp+p.baseRound;return [r*c,r*s];}
    case 'constwidth':{const k=p.baseWidthK|0,a=Math.min(p.baseWidthA,0.95/(k*k-1));const h=1+a*Math.cos(k*t),hp=-a*k*Math.sin(k*t);return [h*c-hp*s,h*s+hp*c];}
    default:return [c,s];
  }
}
function covered(p,psi){const n=Math.max(1,p.covSegs|0),half=Math.min(1,p.covArc)*180/n,rot=+p.covRot,pd=psi*180/Math.PI;
  if(p.covArc>=1)return true;for(let k=0;k<n;k++){let d=Math.abs(pd-rot-360*k/n);d-=360*Math.floor(d/360);if(d>180)d=360-d;if(d<=half+1e-9)return true;}return false;}
function ownCurve(p,f,isStator,M){ // own-frame points scaled by the feature stack; psi is the own polar angle
  const x=new Float64Array(M),y=new Float64Array(M),xr=new Float64Array(M),yr=new Float64Array(M),ps=new Float64Array(M);
  for(let i=0;i<M;i++){const t=i*TAU/M;const b=basePoint(p,t);let psi=Math.atan2(b[1],b[0]);if(psi<0)psi+=TAU;
    const fac=isStator?(2-f.full(psi)):f.full(psi),facR=isStator?(2-f.noTeeth(psi)):f.core(psi);
    x[i]=b[0]*fac;y[i]=b[1]*fac;xr[i]=b[0]*facR;yr[i]=b[1]*facR;ps[i]=psi;}
  return {x,y,xr,yr,ps,M};
}
function placed(xs,ys,scale,p){const M=xs.length,X=new Float64Array(M),Y=new Float64Array(M),c=Math.cos(p.rot*Math.PI/180),s=Math.sin(p.rot*Math.PI/180);
  for(let i=0;i<M;i++){const x=xs[i]*scale,y=ys[i]*scale;X[i]=x*c-y*s+p.offX;Y[i]=x*s+y*c+p.offY;}return {X,Y};}
function resample(X,Y,ps,nt){ // polar re-sample about the axis: radius and own angle per axis sample
  const M=X.length,idx=new Array(M),ang=new Float64Array(M),rad=new Float64Array(M);
  for(let i=0;i<M;i++){let a=Math.atan2(Y[i],X[i]);if(a<0)a+=TAU;ang[i]=a;rad[i]=Math.hypot(X[i],Y[i]);idx[i]=i;}
  idx.sort((a,b)=>ang[a]-ang[b]);
  const r=new Float64Array(nt),psi=new Float64Array(nt);let k=0;
  for(let i=0;i<nt;i++){const th=i*TAU/nt;while(k<M-1&&ang[idx[k+1]]<=th)k++;
    let a0=idx[k],a1=idx[(k+1)%M];let t0=ang[a0],t1=ang[a1];if(th<t0){a0=idx[M-1];a1=idx[0];t0=ang[a0]-TAU;t1=ang[a1];}else if(t1<t0)t1+=TAU;
    const u=t1>t0?(th-t0)/(t1-t0):0;r[i]=rad[a0]*(1-u)+rad[a1]*u;
    let dp=ps?ps[a1]-ps[a0]:0;if(dp>Math.PI)dp-=TAU;if(dp<-Math.PI)dp+=TAU;let pv=ps?ps[a0]+dp*u:0;if(pv<0)pv+=TAU;if(pv>=TAU)pv-=TAU;psi[i]=pv;}
  return {r,psi};
}
function outerOwn(p,own,s0,r0){ // stator outer boundary in own frame (dimensionless), from the root (no-teeth) curve
  const M=own.M,X=new Float64Array(M),Y=new Float64Array(M),yk=p.yoke/r0;let rmax=0;
  for(let i=0;i<M;i++)rmax=Math.max(rmax,Math.hypot(own.xr[i],own.yr[i])*s0);
  for(let i=0;i<M;i++){const t=i*TAU/M;
    if(p.outerForm==='concentric'){const rr=Math.hypot(own.xr[i],own.yr[i])*s0;const f=(rr+yk)/rr;X[i]=own.xr[i]*s0*f;Y[i]=own.yr[i]*s0*f;}
    else if(p.outerForm==='round'){X[i]=(rmax+yk)*Math.cos(t);Y[i]=(rmax+yk)*Math.sin(t);}
    else{const k=p.outerForm==='square'?4:6,sec=TAU/k,off=p.outerForm==='square'?Math.PI/4:0;let u=(t-off)%sec;if(u<0)u+=sec;const rr=(rmax+yk)/Math.cos(u-sec/2);X[i]=rr*Math.cos(t);Y[i]=rr*Math.sin(t);}}
  return {X,Y};
}
function buildSurfaces(st,nt){
  const r0=st.scale.r0,g0=st.gap/r0,fR=makeProfile(st.rotor),fS=makeProfile(st.stator);
  const rotOwn=ownCurve(st.rotor,fR,false,MOWN),staOwn=ownCurve(st.stator,fS,true,MOWN);
  const clampOff=p=>{const m=Math.hypot(p.offX,p.offY);if(m>0.4){p.offX*=0.4/m;p.offY*=0.4/m;}};clampOff(st.rotor);clampOff(st.stator);
  const rp=placed(rotOwn.x,rotOwn.y,1,st.rotor),rr=resample(rp.X,rp.Y,rotOwn.ps,nt);const R=rr.r;
  let maxR=-1e9,minR=1e9;for(let i=0;i<nt;i++){if(R[i]>maxR)maxR=R[i];if(R[i]<minR)minR=R[i];}
  const target=maxR+g0;
  const minSof=s0=>{const sp=placed(staOwn.x,staOwn.y,s0,st.stator);const rs=resample(sp.X,sp.Y,null,nt);let m=1e9;for(let i=0;i<nt;i++)if(rs.r[i]<m)m=rs.r[i];return m;};
  let sa=1,ma=minSof(sa),sb=sa+(target-ma),mb=minSof(sb),s0=sb;
  for(let it=0;it<6&&Math.abs(mb-target)>1e-9;it++){const sn=Math.abs(mb-ma)>1e-12?sb+(target-mb)*(sb-sa)/(mb-ma):sb+(target-mb);sa=sb;ma=mb;sb=sn;mb=minSof(sb);s0=sb;}
  const sp=placed(staOwn.x,staOwn.y,s0,st.stator),sr=resample(sp.X,sp.Y,staOwn.ps,nt);const S=sr.r,psiS=sr.psi;
  const mask=new Uint8Array(nt);let covCount=0;for(let i=0;i<nt;i++){mask[i]=covered(st.stator,psiS[i])?1:0;covCount+=mask[i];}
  const oo=outerOwn(st.stator,staOwn,s0,r0),op=placed(oo.X,oo.Y,1,st.stator),orr=resample(op.X,op.Y,null,nt);const outer=orr.r;
  let maxS=-1e9,minS=1e9,maxOut=0;for(let i=0;i<nt;i++){if(S[i]>maxS)maxS=S[i];if(S[i]<minS)minS=S[i];if(outer[i]>maxOut)maxOut=outer[i];}
  // own-angle -> axis-angle map for placing conductors on the stator
  const pairs=[];for(let i=0;i<nt;i++)pairs.push([psiS[i],i*TAU/nt]);pairs.sort((a,b)=>a[0]-b[0]);
  const thetaOfPsi=psi=>{psi=((psi%TAU)+TAU)%TAU;let lo=0,hi=pairs.length-1;while(lo<hi){const mid=(lo+hi)>>1;if(pairs[mid][0]<psi)lo=mid+1;else hi=mid;}
    const a=pairs[(lo-1+pairs.length)%pairs.length],b=pairs[lo%pairs.length];let pa=a[0],pb=b[0],ta=a[1],tb=b[1];if(pb<pa){if(psi>=pa)pb+=TAU;else pa-=TAU;}if(tb<ta)tb+=TAU;
    const u=pb>pa?(psi-pa)/(pb-pa):0;return ((ta+(tb-ta)*u)%TAU+TAU)%TAU;};
  return {R,S,outer,mask,psiS,s0,maxR,minR,maxS,minS,maxOut,covCount,fR,fS,rotOwn,staOwn,outerOwnPts:oo,g0,thetaOfPsi};
}
function spectrum(arr,maxN){
  const n=arr.length;let mean=0;for(let i=0;i<n;i++)mean+=arr[i];mean/=n;
  const out=new Float64Array(maxN+1),lim=Math.min(maxN,(n/2)|0);
  for(let k=1;k<=lim;k++){let re=0,im=0;const wk=TAU*k/n;for(let i=0;i<n;i++){const v=arr[i]-mean;re+=v*Math.cos(wk*i);im-=v*Math.sin(wk*i);}out[k]=2*Math.hypot(re,im)/n;}
  return out;
}
function argmax(sp,floor){let b=0,bv=0;for(let k=1;k<sp.length;k++)if(sp[k]>bv){bv=sp[k];b=k;}return bv>floor?b:0;}

/* ---------- windings: everything becomes conductor stations ---------- */
function parseLayout(str){
  const toks=String(str||'').trim().split(/[\s,;]+/).filter(Boolean),out=[];
  for(const t of toks){const m=/^([A-Fa-f])([+\-−]?)(?:[x×]?(\d+(?:\.\d+)?))?$/.exec(t);if(!m)continue;
    out.push({phase:PH_LETTERS.indexOf(m[1].toUpperCase()),sign:(m[2]==='-'||m[2]==='−')?-1:1,turns:m[3]?+m[3]:1});}
  return out;
}
function layoutFor(wind,n){
  const m=Math.max(1,wind.phases|0),out=[];
  if(wind.pattern==='custom'){const toks=parseLayout(wind.layout);if(!toks.length)return [];for(let i=0;i<n;i++)out.push(toks[i%toks.length]);return out;}
  for(let i=0;i<n;i++){
    if(wind.pattern==='sequential')out.push({phase:i%m,sign:1,turns:1});
    else if(wind.pattern==='paired')out.push({phase:Math.floor(i/2)%m,sign:i%2===0?1:-1,turns:1});
    else out.push({phase:i%m,sign:i<n/2?1:-1,turns:1});}
  return out;
}
function layoutString(lay){return lay.map(c=>PH_LETTERS[c.phase]+(c.sign<0?'-':'+')+(c.turns!==1?'×'+c.turns:'')).join(' ');}
function parseCustom(str){const out=[];for(const line of String(str||'').split(/[\n;]+/)){const m=/^\s*([A-Fa-f])\s*[:]?\s*(.*)$/.exec(line);if(!m)continue;const ph=PH_LETTERS.indexOf(m[1].toUpperCase());
  for(const tok of m[2].split(/[\s,]+/).filter(Boolean)){const t=/^(-?\d+(?:\.\d+)?)\s*:\s*([+\-−]?\d+(?:\.\d+)?)$/.exec(tok);if(!t)continue;out.push({phase:ph,theta:(+t[1])*Math.PI/180,turns:+t[2].replace('−','-')});}}return out;}
function buildWinding(st,sf){ // returns {m, n, stations[], coils[], topology, sinus, note}
  const w=st.wind,topo=w.topology,Ns=st.stator.teethN|0,n=w.coils>0?(w.coils|0):Ns;
  const out={m:0,n:0,stations:[],coils:[],topology:topo,sinus:null,note:''};
  const peak=PEAK[st.stator.teethShape]||Math.PI/2;
  const toothPsi=i=>(Ns>0&&w.coils===0)?(peak+TAU*i)/Ns:TAU*(i+0.5)/n;
  const T=psi=>sf?sf.thetaOfPsi(psi):psi;
  const cov=psi=>covered(st.stator,psi);
  if(topo==='sinusoidal'){const m=Math.max(1,w.phases|0);out.m=m;out.n=m;out.sinus={P:Math.max(1,w.polePairs|0),turns:w.turns};return out;}
  if(topo==='custom'){const sts=parseCustom(w.custom);let m=0;for(const s of sts){if(s.phase+1>m)m=s.phase+1;}out.m=m;out.n=sts.length;
    out.stations=sts.map((s,i)=>({theta:((s.theta%TAU)+TAU)%TAU,turns:s.turns,phase:s.phase,kind:'bar',ref:i}));return out;}
  if(n<=0){out.note='no slots: cut stator teeth or set a slot count';return out;}
  const lay=layoutFor(w,n);if(!lay.length){out.note='slot string is empty';return out;}
  let m=0;for(const c of lay)if(c.phase+1>m)m=c.phase+1;out.m=m;out.n=n;
  const pitch=TAU/n;
  if(topo==='tooth'){const span=Math.min(TAU,w.span*pitch);
    for(let i=0;i<n;i++){const c=lay[i],psi=toothPsi(i);if(!cov(psi))continue;const nT=c.turns*w.turns*c.sign;const thC=T(psi);
      const a=T(psi-span/2),b=T(psi+span/2);
      out.stations.push({theta:a,turns:nT,phase:c.phase,kind:'coil',ref:i});out.stations.push({theta:b,turns:-nT,phase:c.phase,kind:'coil',ref:i});
      out.coils.push({phase:c.phase,sign:c.sign,turns:Math.abs(nT),a,b,center:thC,psi,span,kind:'tooth'});}}
  else if(topo==='lap'){const y=Math.max(1,Math.min(n-1,w.pitch|0));
    for(let i=0;i<n;i++){const c=lay[i],p1=toothPsi(i)+pitch/2,p2=toothPsi((i+y)%n)+pitch/2;if(!cov(p1)||!cov(p2))continue;const nT=c.turns*w.turns*c.sign;const a=T(p1),b=T(p2);
      out.stations.push({theta:a,turns:nT,phase:c.phase,kind:'coil',ref:i});out.stations.push({theta:b,turns:-nT,phase:c.phase,kind:'coil',ref:i});
      out.coils.push({phase:c.phase,sign:c.sign,turns:Math.abs(nT),a,b,center:T(p1+ (y*pitch)/2),psi:p1,span:y*pitch,kind:'lap'});}}
  else{ // wave, toroidal: one station per slot
    for(let i=0;i<n;i++){const c=lay[i],ps=toothPsi(i)+pitch/2;if(!cov(ps))continue;out.stations.push({theta:T(ps),turns:c.turns*w.turns*c.sign,phase:c.phase,kind:topo==='toroidal'?'toroid':'bar',ref:i});}}
  if(!out.stations.length)out.note='no conductors inside the covered stator';
  return out;
}
function windingFunctions(wd,nt,skewRad){ // N_p(θ) in turns, mean-free per conductor
  const NP=[];for(let p=0;p<wd.m;p++)NP.push(new Float64Array(nt));
  if(wd.sinus){for(let p=0;p<wd.m;p++)for(let i=0;i<nt;i++)NP[p][i]=wd.sinus.turns*Math.cos(wd.sinus.P*i*TAU/nt-TAU*p/wd.m);return NP;}
  for(const s of wd.stations){const arr=NP[s.phase];for(let i=0;i<nt;i++){let u=((i*TAU/nt-s.theta)/TAU)%1;if(u<0)u+=1;arr[i]+=s.turns*(0.5-u);}}
  if(skewRad>0){const wn=Math.max(1,Math.round(skewRad/(TAU/nt)));if(wn>1){for(let p=0;p<wd.m;p++){const src=NP[p],dst=new Float64Array(nt);const h=wn>>1;
    for(let i=0;i<nt;i++){let acc=0;for(let k=-h;k<=h;k++)acc+=src[((i+k)%nt+nt)%nt];dst[i]=acc/(2*h+1);}NP[p]=dst;}}}
  return NP;
}

/* ---------- evaluation ---------- */
function evaluate(st,nt,nphi,opts){
  opts=opts||{};
  const r0m=st.scale.r0/1000,lm=st.scale.stack/1000;
  const sf=buildSurfaces(st,nt);const {R,S,mask,g0}=sf;
  const step=nt/nphi,dth=TAU/nt,dphi=TAU/nphi;
  const P=new Float32Array(nphi*nt),G=new Float32Array(nphi*nt);
  for(let j=0;j<nphi;j++){const sh=j*step,base=j*nt;for(let i=0;i<nt;i++){let ii=i-sh;if(ii<0)ii+=nt;const g=(S[i]-R[ii])*r0m;G[base+i]=g;P[base+i]=mask[i]?1/g:0;}}
  // masses from the steel volume (rho 7800): rotor polar region about the axis, stator ring between bore and frame
  const RHO=7800;let aR=0,i4=0,aS=0;for(let i=0;i<nt;i++){aR+=R[i]*R[i];i4+=Math.pow(R[i],4);if(mask[i])aS+=sf.outer[i]*sf.outer[i]-S[i]*S[i];}
  const mRotor=RHO*lm*r0m*r0m*aR*dth/2,J=RHO*lm*Math.pow(r0m,4)*i4*dth/4,mRing=RHO*lm*r0m*r0m*aS*dth/2;
  const wd=buildWinding(st,sf);
  let excite=st.wind.excite;if(wd.m===0||sf.covCount===0)excite='uniform';
  const m=wd.m,NP=windingFunctions(wd,nt,st.wind.skew*Math.PI/180);
  const kW=MU0*r0m*lm*dth;
  const L=[],dL=[];
  for(let p=0;p<m;p++){const Lp=new Float64Array(nphi);const np=NP[p];
    for(let j=0;j<nphi;j++){const base=j*nt;let sP=0,sNP=0;for(let i=0;i<nt;i++){sP+=P[base+i];sNP+=np[i]*P[base+i];}const c=sP>0?sNP/sP:0;let acc=0;for(let i=0;i<nt;i++){const v=np[i]-c;acc+=v*v*P[base+i];}Lp[j]=kW*acc;}
    L.push(Lp);const d=new Float64Array(nphi);for(let j=0;j<nphi;j++)d[j]=(Lp[(j+1)%nphi]-Lp[(j-1+nphi)%nphi])/(2*dphi);dL.push(d);}
  const I=[],cur=+st.wind.current;
  for(let p=0;p<m;p++)I.push(new Float64Array(nphi));
  if(excite==='auto'){let mx=0;for(let p=0;p<m;p++)for(let j=0;j<nphi;j++)if(Math.abs(dL[p][j])>mx)mx=Math.abs(dL[p][j]);const thr=0.02*mx;
    for(let p=0;p<m;p++)for(let j=0;j<nphi;j++)I[p][j]=(mx>0&&dL[p][j]>thr)?cur:0;}
  else if(excite==='sin'){const pe=st.wind.polePairs|0,adv=st.wind.advance*Math.PI/180;for(let p=0;p<m;p++)for(let j=0;j<nphi;j++)I[p][j]=cur*Math.cos(pe*j*dphi+adv-TAU*p/m);}
  else if(excite==='dc'){for(let j=0;j<nphi;j++)I[0][j]=cur;}
  const W=new Float64Array(nphi),T=new Float64Array(nphi),F=new Float64Array(nt);
  let Bmax=0,meanW=0,maxW=-1e9,minW=1e9,meanT=0,maxT=-1e9,minT=1e9;
  const F0=st.wind.turns*cur;
  const Wat=(je)=>{const base=je*nt;if(excite==='uniform'){let sP=0;for(let i=0;i<nt;i++)sP+=P[base+i];return 0.5*kW*F0*F0*sP;}
    let sP=0,sFP=0;for(let i=0;i<nt;i++){sP+=P[base+i];sFP+=F[i]*P[base+i];}const c=sP>0?sFP/sP:0;let acc=0;for(let i=0;i<nt;i++){const v=F[i]-c;acc+=v*v*P[base+i];}return 0.5*kW*acc;};
  for(let j=0;j<nphi;j++){
    if(excite!=='uniform'){F.fill(0);for(let p=0;p<m;p++){const ip=I[p][j];if(ip===0)continue;const np=NP[p];for(let i=0;i<nt;i++)F[i]+=ip*np[i];}}
    const w=Wat(j);W[j]=w;meanW+=w;if(w>maxW)maxW=w;if(w<minW)minW=w;
    const t=(Wat((j+1)%nphi)-Wat((j-1+nphi)%nphi))/(2*dphi);T[j]=t;meanT+=t;if(t>maxT)maxT=t;if(t<minT)minT=t;
    if(opts.spectra||opts.bmax){const base=j*nt;if(excite==='uniform'){for(let i=0;i<nt;i++){const b=MU0*F0*P[base+i];if(b>Bmax)Bmax=b;}}
      else{let sP=0,sFP=0;for(let i=0;i<nt;i++){sP+=P[base+i];sFP+=F[i]*P[base+i];}const c=sP>0?sFP/sP:0;for(let i=0;i<nt;i++){const b=Math.abs(MU0*(F[i]-c)*P[base+i]);if(b>Bmax)Bmax=b;}}}
  }
  meanW/=nphi;meanT/=nphi;
  const torqueMode=excite!=='uniform';
  const ripple=torqueMode?(Math.abs(meanT)>1e-12?(maxT-minT)/Math.abs(meanT)*100:0):(meanW>0?(maxW-minW)/meanW*100:0);
  // ---- dynamics tables: generalized magnetic force Q = dW'/dq and stiffness K = d2W'/dq2 per DOF ----
  let dyn=null;
  if(opts.dyn){
    const dofs=[];const cs=new Float64Array(nt),sn=new Float64Array(nt);for(let i=0;i<nt;i++){cs[i]=-Math.cos(i*dth);sn[i]=-Math.sin(i*dth);}
    dofs.push({name:'rotor x',kind:'rotor',u:cs,mass:mRotor});dofs.push({name:'rotor y',kind:'rotor',u:sn,mass:mRotor});
    if(st.stator.covArc>=1){const u0=new Float64Array(nt).fill(1),u2c=new Float64Array(nt),u2s=new Float64Array(nt);for(let i=0;i<nt;i++){u2c[i]=Math.cos(2*i*dth);u2s[i]=Math.sin(2*i*dth);}
      dofs.push({name:'yoke breathing',kind:'stator',u:u0,mass:mRing,mode:'n0'});dofs.push({name:'yoke oval cos 2θ',kind:'stator',u:u2c,mass:mRing/2,mode:'n2c'});dofs.push({name:'yoke oval sin 2θ',kind:'stator',u:u2s,mass:mRing/2,mode:'n2s'});}
    else{const runs=maskRuns(mask);runs.forEach((r,q)=>{const len=r[1]-r[0]+1,thc=(((r[0]+r[1])/2)%nt)*dth,u=new Float64Array(nt);for(let i=r[0];i<=r[1];i++){const k=i%nt;u[k]=Math.cos(k*dth-thc);}
      dofs.push({name:'segment '+(q+1),kind:'stator',u,mass:mRing*len/Math.max(1,sf.covCount),mode:'seg',theta:thc});});}
    const nd=dofs.length,delta=0.05*g0*r0m,gmin=0.08*g0*r0m,Fd=new Float64Array(nt);
    // commutation period of the current pattern (samples): the field may be shifted against the rotor by any
    // fraction of it, so every table is built for NE shifts and interpolated periodically in the simulation
    let per=nphi;
    if(excite==='sin')per=nphi/Math.max(1,st.wind.polePairs|0);
    else if(excite==='auto'||excite==='dc'){for(let sh=1;sh<=nphi/2;sh++){if(nphi%sh!==0)continue;let ok=true;for(let p=0;p<m&&ok;p++)for(let j=0;j<nphi;j++){if(Math.abs(I[p][j]-I[p][(j+sh)%nphi])>1e-9*Math.max(1,cur)){ok=false;break;}}if(ok){per=sh;break;}}}
    const NE=excite==='uniform'?1:12,Tper=per*dphi;
    const Iat=(p,x)=>{let u=x%nphi;if(u<0)u+=nphi;const i0=u|0,f=u-i0;return I[p][i0]*(1-f)+I[p][(i0+1)%nphi]*f;};
    const W0=[],Tt=[],Q=[],K=[],dQ=[],Kxy=[];
    const Wd=(base,uA,dA,uB,dB)=>{let sP=0,sFP=0;for(let i=0;i<nt;i++){if(!mask[i])continue;let g=G[base+i]+dA*uA[i]+(uB?dB*uB[i]:0);if(g<gmin)g=gmin;const p=1/g;sP+=p;sFP+=Fd[i]*p;}
      if(excite==='uniform')return 0.5*kW*F0*F0*sP;const c=sP>0?sFP/sP:0;let acc=0;for(let i=0;i<nt;i++){if(!mask[i])continue;let g=G[base+i]+dA*uA[i]+(uB?dB*uB[i]:0);if(g<gmin)g=gmin;const v=Fd[i]-c;acc+=v*v/g;}return 0.5*kW*acc;};
    const none=new Float64Array(nt);
    for(let e=0;e<NE;e++){const off=e*per/NE;
      const w0=new Float64Array(nphi),tt=new Float64Array(nphi),q=[],k=[],dq=[],kxy=new Float64Array(nphi),wp=[],wm=[];
      for(let kk=0;kk<nd;kk++){q.push(new Float64Array(nphi));k.push(new Float64Array(nphi));dq.push(new Float64Array(nphi));wp.push(new Float64Array(nphi));wm.push(new Float64Array(nphi));}
      for(let j=0;j<nphi;j++){const base=j*nt;
        if(excite!=='uniform'){Fd.fill(0);for(let p=0;p<m;p++){const ip=Iat(p,j-off);if(ip===0)continue;const np=NP[p];for(let i=0;i<nt;i++)Fd[i]+=ip*np[i];}}
        w0[j]=Wd(base,none,0,null,0);
        tt[j]=(Wd(((j+1)%nphi)*nt,none,0,null,0)-Wd(((j-1+nphi)%nphi)*nt,none,0,null,0))/(2*dphi);
        for(let kk=0;kk<nd;kk++){wp[kk][j]=Wd(base,dofs[kk].u,delta,null,0);wm[kk][j]=Wd(base,dofs[kk].u,-delta,null,0);}
        const wpp=Wd(base,cs,delta,sn,delta),wpm=Wd(base,cs,delta,sn,-delta),wmp=Wd(base,cs,-delta,sn,delta),wmm=Wd(base,cs,-delta,sn,-delta);kxy[j]=(wpp-wpm-wmp+wmm)/(4*delta*delta);}
      for(let kk=0;kk<nd;kk++)for(let j=0;j<nphi;j++){q[kk][j]=(wp[kk][j]-wm[kk][j])/(2*delta);k[kk][j]=(wp[kk][j]-2*w0[j]+wm[kk][j])/(delta*delta);}
      for(let kk=0;kk<nd;kk++)for(let j=0;j<nphi;j++)dq[kk][j]=(q[kk][(j+1)%nphi]-q[kk][(j-1+nphi)%nphi])/(2*dphi);
      W0.push(w0);Tt.push(tt);Q.push(q);K.push(k);dQ.push(dq);Kxy.push(kxy);}
    let Kxx=0;for(let j=0;j<nphi;j++)Kxx+=K[0][0][j];Kxx/=nphi;
    dyn={dofs,NE,Tper,per,W0,T:Tt,Q,K,Kxy,dQ,delta,Kxx};
  }
  const out=Object.assign({},sf,{P,G,W,T,L,I,NP,wd,excite,m,meanW,maxW,minW,meanT,maxT,minT,ripple,torqueMode,Bmax,nt,nphi,r0m,lm,dom:0,mRotor,J,mRing,dyn});
  const ripSrc=torqueMode?T:W;
  if(opts.spectra){out.specR=spectrum(R,NORD);out.specS=spectrum(S,NORD);out.specW=spectrum(ripSrc,NORD);let mx=0;for(let j=0;j<nphi;j++)mx=Math.max(mx,Math.abs(ripSrc[j]));out.dom=argmax(out.specW,1e-9*Math.max(1e-30,mx));}
  else if(opts.dom){const sp=spectrum(ripSrc,NORD);let mx=0;for(let j=0;j<nphi;j++)mx=Math.max(mx,Math.abs(ripSrc[j]));out.dom=argmax(sp,1e-9*Math.max(1e-30,mx));}
  return out;
}

/* ---------- dynamics: rotor spin + rotor whirl + stator modes, RK4 on the magnetic tables ---------- */
function simulate(e,st){
  const d=st.dyn,dy=e.dyn;if(!dy)return null;
  const nphi=e.nphi,dphi=TAU/nphi,dofs=dy.dofs,nS=dofs.length-2,NE=dy.NE,Tper=dy.Tper;
  const J=Math.max(1e-9,d.inertiaScale*e.J),mR=Math.max(1e-6,e.mRotor),lm=e.lm,Rb=e.s0*e.r0m;
  // --- stator yoke modes: free, driven single, or travelling wave ---
  const free=d.statorFree==='free',pattern=d.actPattern;const act=pattern==='single'?Math.max(0,Math.min(nS-1,(+d.actDof)||0)):-1;
  const actA=d.actAmp*1e-6,actW=TAU*d.actFreq,wdir=+d.actDir||1,wNum=Math.max(1,d.actWave|0);
  const driven=new Array(nS).fill(false);if(pattern==='single'&&act>=0)driven[act]=true;
  if(pattern==='wave')for(let k=0;k<nS;k++){const md=dofs[k+2].mode;if(md==='n2c'||md==='n2s'||md==='seg')driven[k]=true;}
  const segIdx=[];for(let k=0;k<nS;k++)if(dofs[k+2].mode==='seg')segIdx.push(k);
  const qDriven=(k,t)=>{if(pattern==='single')return k===act?actA*Math.sin(actW*t):0;
    const md=dofs[k+2].mode;if(md==='n2c')return actA*Math.cos(actW*t);if(md==='n2s')return wdir*actA*Math.sin(actW*t);
    if(md==='seg'){const si=segIdx.indexOf(k),ns=segIdx.length;return actA*Math.sin(actW*t-wdir*TAU*wNum*si/Math.max(1,ns));}return 0;};
  const mS=[],kS=[],cS=[];for(let k=0;k<nS;k++){const ms=Math.max(1e-6,dofs[k+2].mass);mS.push(ms);const ks=ms*Math.pow(TAU*d.statorFn,2);kS.push(ks);cS.push(2*d.statorZeta*Math.sqrt(ks*ms));}
  // --- rotor radial: bearing, unbalance, active magnetic bearing ---
  const kB=d.bearK*1e3,cB=2*d.bearZeta*Math.sqrt(Math.max(kB,1e3)*mR),clr=d.clearance*1e-6,mue=d.unbalance*1e-6;
  const amb=d.ambMode,ambKp=d.ambKp*1e3,ambKd=+d.ambKd,ambF=+d.ambFmax,orbR=d.orbitR*1e-6,orbW=TAU*d.orbitF;
  // --- rotor axial: pull-in, axial bearing, actuator ---
  const kZ=d.axialK*1e3,cZ=2*d.axialZeta*Math.sqrt(Math.max(kZ,1e3)*mR),axAct=d.axialAct,axA=+d.axialAmp,axW=TAU*d.axialFreq,axKp=d.axialKp*1e3,axKd=2*0.7*Math.sqrt(axKp*mR);
  // --- stator carrier: commanded spin + dither, torsional mount under the reaction torque ---
  const wS=d.carrierRpm*TAU/60,dAmp=d.ditherAmp*Math.PI/180,dW=TAU*d.ditherFreq,torFree=d.torMode==='compliant';
  const Js=Math.max(1e-7,e.mRing*Rb*Rb*2.5),kT=Js*Math.pow(TAU*d.torFn,2),cT=2*d.torZeta*Math.sqrt(kT*Js);
  // --- commutation: locked with advance schedule, open-loop field, or stepped field ---
  const comm=d.comm,degEl=Tper/360,adv0=d.adv0*degEl,advSlope=d.advSlope*degEl,wField=d.fieldRpm*TAU/60,stepRate=+d.stepRate,stepAng=Tper/Math.max(1,d.stepsPer|0);
  const T0=d.loadT*1e-3,bV=d.viscous*1e-6,Tc=d.coulomb*1e-3,wRef=d.rpmRef*TAU/60,regulate=d.mode==='regulate';
  const g0m=e.g0*e.r0m,touch=0.9*g0m,kC=200*Math.max(kB,1e5);
  const lut=(tab,ph)=>{let x=(ph/dphi)%nphi;if(x<0)x+=nphi;const i0=x|0,f=x-i0;return tab[i0]*(1-f)+tab[(i0+1)%nphi]*f;};
  const lut2=(tabs,ph,off)=>{if(NE===1)return lut(tabs[0],ph);let u=(off/Tper)%1;if(u<0)u+=1;u*=NE;const e0=u|0,f=u-e0;return lut(tabs[e0%NE],ph)*(1-f)+lut(tabs[(e0+1)%NE],ph)*f;};
  const lut2k=(tabs,k,ph,off)=>{if(NE===1)return lut(tabs[0][k],ph);let u=(off/Tper)%1;if(u<0)u+=1;u*=NE;const e0=u|0,f=u-e0;return lut(tabs[e0%NE][k],ph)*(1-f)+lut(tabs[(e0+1)%NE][k],ph)*f;};
  const fMax=Math.max(free?d.statorFn:0,pattern!=='none'?d.actFreq:0,axAct!=='none'?d.axialFreq:0,amb==='orbit'?d.orbitF:0,dAmp>0?d.ditherFreq:0,torFree?d.torFn:0,
    Math.sqrt(Math.max(kB,1e3)/mR)/TAU,Math.sqrt(Math.max(kZ,1e3)/mR)/TAU,amb!=='none'?Math.sqrt(Math.max(ambKp,1e3)/mR)/TAU:0,Math.max(d.omega0,d.rpmRef,Math.abs(d.fieldRpm))/60*Math.max(1,e.dom||1),comm==='stepped'?stepRate:0,50);
  const dur=d.duration*1e-3;let dt=Math.min(1e-4,1/(fMax*30));let steps=Math.ceil(dur/dt);if(steps>300000){steps=300000;dt=dur/steps;}
  const nFree=free?nS:0,NS=10+2*nFree;const s=new Float64Array(NS),k1=new Float64Array(NS),k2=new Float64Array(NS),k3=new Float64Array(NS),k4=new Float64Array(NS),tmp=new Float64Array(NS);
  s[0]=state.phi;s[1]=d.omega0*TAU/60;
  let touched=false,scurLast=1,offLast=0,psiLast=0,fambLast=0,etaMin=1;const qTmp=new Float64Array(nS);
  const deriv=(t,y,out)=>{
    const phi=y[0],om=y[1],x=y[2],yy=y[3],vx=y[4],vy=y[5],z=y[6],vz=y[7],pt=torFree?y[8]:0,ptd=torFree?y[9]:0;
    const psiS=wS*t+(dAmp>0?dAmp*Math.sin(dW*t):0)+pt;psiLast=psiS;
    let rel=(phi-psiS)%TAU;if(rel<0)rel+=TAU;
    let off;if(comm==='locked')off=-(adv0+advSlope*om*60/TAU/1000);else if(comm==='open')off=rel-(wField*t+adv0);else off=rel-(Math.floor(t*stepRate)*stepAng+adv0);offLast=off;
    const scur=regulate?Math.max(0,Math.min(1,10*(wRef-om)/Math.max(wRef,1))):1;scurLast=scur;
    const eta=Math.max(0,1-Math.abs(z)/lm);if(eta<etaMin)etaMin=eta;const g=scur*scur*eta;
    for(let k=0;k<nS;k++)qTmp[k]=driven[k]?qDriven(k,t):(free?y[10+2*k]:0);
    let Tem=lut2(dy.T,rel,off)+x*lut2k(dy.dQ,0,rel,off)+yy*lut2k(dy.dQ,1,rel,off);for(let k=0;k<nS;k++)if(qTmp[k]!==0)Tem+=qTmp[k]*lut2k(dy.dQ,k+2,rel,off);Tem*=g;
    const kxy=lut2(dy.Kxy,rel,off);
    let Fx=g*(lut2k(dy.Q,0,rel,off)+lut2k(dy.K,0,rel,off)*x+kxy*yy),Fy=g*(lut2k(dy.Q,1,rel,off)+kxy*x+lut2k(dy.K,1,rel,off)*yy);
    Fx+=mue*om*om*Math.cos(phi);Fy+=mue*om*om*Math.sin(phi);
    const r=Math.hypot(x,yy);if(r>clr){const f=kB*(r-clr)/r;Fx-=f*x;Fy-=f*yy;}if(r>touch){touched=true;const f=kC*(r-touch)/r;Fx-=f*x;Fy-=f*yy;}
    Fx-=cB*vx;Fy-=cB*vy;
    if(amb!=='none'){const xr=amb==='orbit'?orbR*Math.cos(orbW*t):0,yr=amb==='orbit'?orbR*Math.sin(orbW*t):0;let ax=-ambKp*(x-xr)-ambKd*vx,ay=-ambKp*(yy-yr)-ambKd*vy;const fm=Math.hypot(ax,ay);if(fm>ambF){ax*=ambF/fm;ay*=ambF/fm;}Fx+=ax;Fy+=ay;fambLast=Math.hypot(ax,ay);}
    let Fz=-(scur*scur*lut2(dy.W0,rel,off)/lm)*Math.sign(z)*(eta>0?1:0)-kZ*z-cZ*vz;
    if(axAct==='force')Fz+=axA*Math.sin(axW*t);else if(axAct==='servo'){const zr=axA*1e-6*Math.sin(axW*t);Fz+=-axKp*(z-zr)-axKd*vz;}
    out[0]=om;out[1]=(Tem-T0-bV*om-Tc*Math.tanh(om/0.5))/J;out[2]=vx;out[3]=vy;out[4]=Fx/mR;out[5]=Fy/mR;out[6]=vz;out[7]=Fz/mR;
    if(torFree){out[8]=ptd;out[9]=(-Tem-kT*pt-cT*ptd)/Js;}else{out[8]=0;out[9]=0;}
    for(let k=0;k<nFree;k++){const q=y[10+2*k],qd=y[11+2*k];const Qm=driven[k]?0:g*(lut2k(dy.Q,k+2,rel,off)+lut2k(dy.K,k+2,rel,off)*q);out[10+2*k]=qd;out[11+2*k]=(Qm-kS[k]*q-cS[k]*qd)/mS[k];}
    return Tem;};
  const rec=Math.max(1,Math.ceil(steps/2400)),nrec=Math.floor(steps/rec)+1;
  const A=()=>new Float64Array(nrec);const Tt=A(),Tphi=A(),Tom=A(),Ttem=A(),Tx=A(),Ty=A(),Tz=A(),Tpsi=A(),Ttor=A(),Toff=A(),Tsc=A(),Tamb=A(),Tq=[];for(let k=0;k<nS;k++)Tq.push(A());
  let n=0,t=0;
  const record=()=>{if(n>=nrec)return;Tt[n]=t;Tphi[n]=s[0];Tom[n]=s[1];Ttem[n]=deriv(t,s,tmp);Tx[n]=s[2];Ty[n]=s[3];Tz[n]=s[6];Tpsi[n]=psiLast;Ttor[n]=torFree?s[8]:0;let o=offLast%Tper;if(o>Tper/2)o-=Tper;if(o<-Tper/2)o+=Tper;Toff[n]=o;Tsc[n]=scurLast;Tamb[n]=fambLast;for(let k=0;k<nS;k++)Tq[k][n]=qTmp[k];n++;};
  record();
  for(let i=1;i<=steps;i++){
    deriv(t,s,k1);for(let q=0;q<NS;q++)tmp[q]=s[q]+0.5*dt*k1[q];
    deriv(t+0.5*dt,tmp,k2);for(let q=0;q<NS;q++)tmp[q]=s[q]+0.5*dt*k2[q];
    deriv(t+0.5*dt,tmp,k3);for(let q=0;q<NS;q++)tmp[q]=s[q]+dt*k3[q];
    deriv(t+dt,tmp,k4);for(let q=0;q<NS;q++)s[q]+=dt/6*(k1[q]+2*k2[q]+2*k3[q]+k4[q]);
    t+=dt;if(i%rec===0)record();}
  const i0=Math.floor(n*0.7);let omM=0,omMx=-1e9,omMn=1e9,rMax=0,tM=0,zMax=0,torMax=0,ambMax=0;const qMax=new Float64Array(nS);
  for(let i=i0;i<n;i++){omM+=Tom[i];tM+=Ttem[i];if(Tom[i]>omMx)omMx=Tom[i];if(Tom[i]<omMn)omMn=Tom[i];const r=Math.hypot(Tx[i],Ty[i]);if(r>rMax)rMax=r;if(Math.abs(Tz[i])>zMax)zMax=Math.abs(Tz[i]);if(Math.abs(Ttor[i])>torMax)torMax=Math.abs(Ttor[i]);if(Tamb[i]>ambMax)ambMax=Tamb[i];for(let k=0;k<nS;k++)if(Math.abs(Tq[k][i])>qMax[k])qMax[k]=Math.abs(Tq[k][i]);}
  omM/=(n-i0);tM/=(n-i0);
  let Kxx=0,Kyy=0;for(let j=0;j<nphi;j++){Kxx+=dy.K[0][0][j];Kyy+=dy.K[0][1][j];}Kxx/=nphi;Kyy/=nphi;
  const fieldW=comm==='open'?wField:comm==='stepped'?stepRate*stepAng:null;
  return {t:Tt,phi:Tphi,om:Tom,tem:Ttem,x:Tx,y:Ty,z:Tz,psi:Tpsi,tor:Ttor,off:Toff,sc:Tsc,amb:Tamb,q:Tq,n,dt:rec*dt,dur,nS,dofs,act,driven,free,comm,Tper,rpm:omM*60/TAU,rpmRipple:Math.abs(omM)>1e-9?(omMx-omMn)/Math.abs(omM)*100:0,meanTem:tM,whirl:rMax,zMax,torMax,ambMax,etaMin,qMax,touched,Kxx,Kyy,kB,fBear:Math.sqrt(Math.max(kB-Kxx,0)/mR)/TAU,fRot:omM/TAU,slipRpm:fieldW==null?null:(omM-fieldW)*60/TAU,clr,touch,mR,J,Js,Rb,mS,steps,dtInt:dt};
}
function sampleSim(sim,t){const n=sim.n;let x=t/sim.dt;if(x<0)x=0;if(x>n-1)x=n-1;const i0=x|0,f=x-i0,i1=Math.min(n-1,i0+1);const L=(a)=>a[i0]*(1-f)+a[i1]*f;
  return {t,phi:L(sim.phi),om:L(sim.om),x:L(sim.x),y:L(sim.y),z:L(sim.z),psi:L(sim.psi),off:L(sim.off),q:sim.q.map(L),tem:L(sim.tem)};}

function interpArr(arr,idx){const n=arr.length;let x=idx%n;if(x<0)x+=n;const i0=Math.floor(x),f=x-i0;return arr[i0]*(1-f)+arr[(i0+1)%n]*f;}
/* ---------- colour ---------- */
const HEAT_STOPS=[[0,[26,34,48]],[0.35,[91,58,38]],[0.7,[201,131,63]],[1,[255,228,187]]];
const DIV_STOPS=[[0,[63,160,150]],[0.5,[42,51,64]],[1,[224,154,82]]];
function makeLut(stops){const lut=new Array(256);for(let i=0;i<256;i++){const t=i/255;let a=stops[0],b=stops[stops.length-1];
  for(let s=0;s<stops.length-1;s++){if(t>=stops[s][0]&&t<=stops[s+1][0]){a=stops[s];b=stops[s+1];break;}}
  const u=(t-a[0])/((b[0]-a[0])||1);lut[i]=[Math.round(a[1][0]+(b[1][0]-a[1][0])*u),Math.round(a[1][1]+(b[1][1]-a[1][1])*u),Math.round(a[1][2]+(b[1][2]-a[1][2])*u)];}return lut;}
const LUT=makeLut(HEAT_STOPS),DLUT=makeLut(DIV_STOPS);
const heat=t=>LUT[Math.max(0,Math.min(255,Math.round(t*255)))];
const heatCss=t=>{const c=heat(t);return 'rgb('+c[0]+','+c[1]+','+c[2]+')';};
const divCss=t=>{const c=DLUT[Math.max(0,Math.min(255,Math.round((t+1)*127.5)))];return 'rgb('+c[0]+','+c[1]+','+c[2]+')';};
function tokens(){const cs=getComputedStyle(roots.find(r=>r.isConnected)||slot);const g=n=>cs.getPropertyValue(n).trim();
  return {paper:g('--paper'),card:g('--card'),ink:g('--ink'),ink2:g('--ink-2'),line:g('--line'),line2:g('--line-2'),steel:g('--steel'),copper:g('--copper'),copper2:g('--copper-2'),verd:g('--verdigris'),verd2:g('--verdigris-2'),stage:g('--stage'),stageInk:g('--stage-ink'),stageDim:g('--stage-dim'),stageLine:g('--stage-line'),ironS:g('--iron-s'),ironR:g('--iron-r'),mono:g('--font-mono')||'monospace',
    ph:[1,2,3,4,5,6].map(i=>g('--ph'+i)),sph:[1,2,3,4,5,6].map(i=>g('--sph'+i))};}

/* ---------- canvas helpers ---------- */
function fit(cv){const dpr=window.devicePixelRatio||1,w=cv.clientWidth,h=cv.clientHeight;if(!w||!h)return {ctx:null,w:0,h:0};
  const W=Math.round(w*dpr),H=Math.round(h*dpr);if(cv.width!==W||cv.height!==H){cv.width=W;cv.height=H;}
  const ctx=cv.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);return {ctx,w,h};}
function quad(ctx,cx,cy,a0,a1,ri0,ri1,ro0,ro1){const c0=Math.cos(a0),s0=Math.sin(a0),c1=Math.cos(a1),s1=Math.sin(a1);
  ctx.beginPath();ctx.moveTo(cx+ri0*c0,cy-ri0*s0);ctx.lineTo(cx+ri1*c1,cy-ri1*s1);ctx.lineTo(cx+ro1*c1,cy-ro1*s1);ctx.lineTo(cx+ro0*c0,cy-ro0*s0);ctx.closePath();}
function fmtStep(v,step){const dec=(String(step).split('.')[1]||'').length;return (+v).toFixed(dec);}
function fmtSI(v,unit,dec){const a=Math.abs(v);if(a===0)return '0 '+unit;const pre=a>=1?['',1]:a>=1e-3?['m',1e3]:a>=1e-6?['µ',1e6]:['n',1e9];return (v*pre[1]).toFixed(dec==null?2:dec)+' '+pre[0]+unit;}
function fmtSig(v){const a=Math.abs(v);return (v>=0?'+':'−')+(a>=100?a.toFixed(0):a>=10?a.toFixed(1):a>=1?a.toFixed(2):a.toFixed(3));}

/* ---------- state access ---------- */
function getP(st,id){const s=id.split('.');return s.length===1?st[s[0]]:st[s[0]][s[1]];}
function setP(st,id,v){const s=id.split('.');if(s.length===1)st[s[0]]=v;else st[s[0]][s[1]]=v;}
const AXES=[];
for(const g of ROTOR_SPECS)for(const it of g.items)if(!it.type)AXES.push({id:'rotor.'+it.key,label:'Rotor · '+it.label,min:it.min,max:it.max,step:it.step});
for(const g of STATOR_SPECS)for(const it of g.items)if(!it.type)AXES.push({id:'stator.'+it.key,label:'Stator · '+it.label,min:it.min,max:it.max,step:it.step});
for(const g of WIND_SPECS)for(const it of g.items)if(!it.type)AXES.push({id:'wind.'+it.key,label:'Winding · '+it.label,min:it.min,max:it.max,step:it.step});
for(const it of SCALE_SPECS)AXES.push({id:it.path,label:it.label,min:it.min,max:it.max,step:it.step});
const axisById=id=>AXES.find(a=>a.id===id);
const METRICS={
  meanT:{label:'mean torque T̄',get:e=>e.meanT,fmt:v=>fmtSI(v,'N·m')},
  ripple:{label:'ripple, peak-to-peak / mean (%)',get:e=>e.ripple,fmt:v=>v.toFixed(1)+' %'},
  bmax:{label:'peak gap flux density',get:e=>e.Bmax,fmt:v=>v.toFixed(2)+' T',bmax:true},
  meanW:{label:'mean co-energy W̄′',get:e=>e.meanW,fmt:v=>fmtSI(v,'J')},
  dom:{label:'dominant ripple order n*',get:e=>e.dom,fmt:v=>'n = '+Math.round(v),dom:true}
};

/* ---------- compute + update ---------- */
let EV=null,DYNE=null,SIM=null,DYNV=null,pending=null,dirty=false,playback='spin',tSim=0;
const off=document.createElement('canvas');off.width=360;off.height=360;const offCtx=off.getContext('2d');
function requestUpdate(kind){kind=kind||'full';const rank={sim:0,light:1,full:2};if(!pending||rank[kind]>rank[pending])pending=kind;if(dirty)return;dirty=true;requestAnimationFrame(()=>{dirty=false;const k=pending;pending=null;recompute(k);});}
function recompute(kind){
  if(kind==='sim'&&DYNE){SIM=simulate(DYNE,state);updateReadouts();if(playback==='dyn')setSimTime(tSim);drawDyn();drawFrame();return;}
  const full=kind!=='light';
  EV=evaluate(state,NT,NPHI,{spectra:true});
  if(full){DYNE=evaluate(state,360,120,{dyn:true});EV.dyn=DYNE.dyn;SIM=simulate(DYNE,state);if(playback==='dyn')setSimTime(tSim);}else{DYNE=null;SIM=null;DYNV=null;EV.dyn=null;}
  buildGapImage();updateReadouts();updateLegend();drawAll();}

function drawDyn(){drawDynSpeed();drawDynOrbit();drawDynSpec();}
function buildGapImage(){const w=360,h=360,img=offCtx.createImageData(w,h),d=img.data,S=EV.S,R=EV.R,g0=EV.g0,mask=EV.mask;
  for(let y=0;y<h;y++){const sh=(h-1-y)*2;for(let x=0;x<w;x++){const i=x*2;let ii=i-sh;if(ii<0)ii+=NT;const o=(y*w+x)*4;
    if(!mask[i]){d[o]=60;d[o+1]=66;d[o+2]=76;d[o+3]=255;continue;}const c=heat(Math.pow(g0/(S[i]-R[ii]),0.75));d[o]=c[0];d[o+1]=c[1];d[o+2]=c[2];d[o+3]=255;}}
  offCtx.putImageData(img,0,0);}
function gcd(a,b){while(b){const t=a%b;a=b;b=t;}return a;}
function metricsDocument(){ // the metrics document: a view reads this, nothing else computes figures
  const e=EV,r0=state.scale.r0,s=SIM;if(!e)return null;
  const nr=state.rotor.teethN|0,ns=state.stator.teethN|0;const lcm=(nr>0&&ns>0)?nr*ns/gcd(nr,ns):null;
  const M=(key,label,value,unit,note)=>({key,label,value:(typeof value==='number'&&!isFinite(value))?null:value,unit:unit||'',note:note||''});
  const nSt=e.wd.sinus?'sheet':e.wd.stations.length;
  const groups=[
    {id:'geometry',title:'Geometry',metrics:[M('bore_s0','bore s₀',+(e.s0*r0).toFixed(3),'mm'),M('outer_diameter','outer Ø',+(2*e.maxOut*r0).toFixed(2),'mm'),M('max_gap','max gap',+((e.maxS-e.minR)*r0).toFixed(3),'mm'),M('min_gap','min gap g₀',+state.gap,'mm'),M('stator_cover','stator cover',+(100*e.covCount/e.nt).toFixed(1),'%'),M('rotor_mass','rotor mass',+(e.mRotor*1e3).toFixed(1),'g'),M('rotor_inertia','rotor J',e.J,'kg·m²'),M('yoke_mass','yoke mass',+(e.mRing*1e3).toFixed(1),'g')]},
    {id:'windings',title:'Windings',metrics:[M('topology','topology',e.wd.topology,''),M('conductors','conductors',e.m?nSt:0,'',e.m?(e.m+' phases'):(e.wd.note||'uniform MMF')),M('phases','phases',e.m,''),M('excitation','excitation',e.excite,''),M('turns','turns per coil',state.wind.turns|0,''),M('phase_current','phase current',+state.wind.current,'A')]},
    {id:'field',title:'Field and torque (static)',metrics:[M('mean_torque','mean torque',e.meanT,'N·m','static tables at the commutation'),M('ripple','ripple',+e.ripple.toFixed(2),'%',e.torqueMode?'of mean torque':'of mean co-energy'),M('peak_b','peak B',+e.Bmax.toFixed(3),'T',e.Bmax>1.8?'saturating':''),M('dominant_order','dominant ripple order',e.dom||null,'',''),M('lcm','lcm(Nr, Ns)',lcm,'',lcm!=null?'orders':'no teeth'),M('mean_coenergy','mean W′',e.meanW,'J')]}];
  if(s){const qm=s.nS?Math.max.apply(null,Array.from(s.qMax)):0;
    groups.push({id:'dynamics',title:'Dynamics (last 30 % of the window)',metrics:[M('speed','speed',+s.rpm.toFixed(1),'rpm'),M('speed_ripple','speed ripple',+s.rpmRipple.toFixed(2),'%'),M('torque_run','torque in run',s.meanTem,'N·m'),M('whirl','whirl radius',+(s.whirl*1e6).toFixed(2),'µm',s.touched?'touchdown':''),M('yoke_displacement','yoke / segment',+(qm*1e6).toFixed(3),'µm','peak'),M('magnetic_stiffness','magnetic stiffness',-s.Kxx,'N/m','negative; bearing +'+s.kB.toFixed(0)),M('bearing_fn','rotor on bearing',s.kB-s.Kxx>0?+s.fBear.toFixed(1):null,'Hz',s.kB-s.Kxx>0?'natural frequency':'unstable'),M('axial','axial excursion',+(s.zMax*1e6).toFixed(2),'µm','overlap ≥ '+(s.etaMin*100).toFixed(0)+' %'),M('torsion','carrier torsion',+(s.torMax*1e3).toFixed(4),'mrad','peak'),M('slip','slip vs field',s.slipRpm==null?null:+s.slipRpm.toFixed(1),'rpm',s.slipRpm==null?(state.dyn.comm==='locked'?'self-commutated':''):(Math.abs(s.slipRpm)>30?'out of sync':'in sync')),M('amb_force','AMB force',state.dyn.ambMode==='none'?null:+s.ambMax.toFixed(2),'N',state.dyn.ambMode==='none'?'off':'peak'),M('touchdown','touchdown',s.touched,'')]});}
  else if(!e.dyn)groups.push({id:'dynamics',title:'Dynamics',metrics:[M('status','status','updating','','release the slider')]});
  return {schema:'airgap/metrics/1',generated_at:new Date().toISOString(),units:'SI unless stated; lengths in mm where labelled',preset:activePreset,groups};}
function fmtMetric(m){const v=m.value;if(v==null)return '—';if(typeof v==='boolean')return v?'yes':'no';if(typeof v==='string')return v;
  if(m.unit==='N·m')return fmtSI(v,'N·m');if(m.unit==='J')return fmtSI(v,'J');if(m.unit==='kg·m²')return (v*1e7).toFixed(0)+' g·cm²';if(m.unit==='N/m')return fmtSI(v,'N/m',1);
  return (Number.isInteger(v)?String(v):Math.abs(v)>=100?v.toFixed(0):Math.abs(v)>=10?v.toFixed(1):v.toFixed(3))+(m.unit?' '+m.unit:'');}
let LAST_METRICS={};
function updateReadouts(){const doc=metricsDocument();METRICS_DOC=doc;const root=$('readouts');if(!root||!doc)return;root.textContent='';const changed=[];
  for(const g of doc.groups){const sec=el('section',{class:'mgroup'});sec.append(el('h4',null,g.title));const grid=el('dl',{class:'mgrid'});
    for(const m of g.metrics){const d=el('div',{class:'metric','data-key':g.id+'.'+m.key});d.append(el('dt',null,m.label));const dd=el('dd',null,fmtMetric(m));if(m.note)dd.append(el('small',null,m.note));d.append(dd);grid.append(d);
      const key=g.id+'.'+m.key,prev=LAST_METRICS[key];if(prev!==undefined&&JSON.stringify(prev)!==JSON.stringify(m.value))changed.push(d);LAST_METRICS[key]=m.value;}
    sec.append(grid);root.append(sec);}
  for(const d of changed){d.classList.add('changed');setTimeout(()=>d.classList.remove('changed'),700);}}
let METRICS_DOC=null;
function updateLegend(){const lg=$('phaseLegend'),tk=tokens();lg.textContent='';if(!EV||!EV.m)return;
  for(let p=0;p<EV.m;p++){const s=el('span',null,'phase '+PH_LETTERS[p]);s.style.setProperty('--c',tk.sph[p%6]);lg.append(s);}
  const ramp=$('rampField');if(EV.torqueMode){ramp.innerHTML='B −'+EV.Bmax.toFixed(1)+' <i class="div"></i> +'+EV.Bmax.toFixed(1)+' T';}else{ramp.innerHTML='g₀/g 0 <i></i> 1';}}
function interpR(idx){return interpArr(EV.R,idx);}
function fieldAt(j,offRad){const e=EV;if(!e.torqueMode)return null;const nt=e.nt,base=j*nt,F=new Float64Array(nt);
  const jc=offRad?(((j-offRad/(TAU/e.nphi))%e.nphi)+e.nphi)%e.nphi:j;const jc0=Math.floor(jc),jf=jc-jc0,jc1=(jc0+1)%e.nphi;
  for(let p=0;p<e.m;p++){const ip=e.I[p][jc0]*(1-jf)+e.I[p][jc1]*jf;if(ip===0)continue;const np=e.NP[p];for(let i=0;i<nt;i++)F[i]+=ip*np[i];}
  let sP=0,sFP=0;for(let i=0;i<nt;i++){sP+=e.P[base+i];sFP+=F[i]*e.P[base+i];}const c=sP>0?sFP/sP:0;
  const B=new Float64Array(nt);for(let i=0;i<nt;i++)B[i]=MU0*(F[i]-c)*e.P[base+i];return B;}
function coveredRuns(own,p){ // index runs of the own-frame curve inside the coverage
  const M=own.M,runs=[];let start=-1;for(let i=0;i<M;i++){const c=covered(p,own.ps[i]);if(c&&start<0)start=i;if(!c&&start>=0){runs.push([start,i-1]);start=-1;}}
  if(start>=0)runs.push([start,M-1]);if(runs.length>1&&runs[0][0]===0&&runs[runs.length-1][1]===M-1){const last=runs.pop();runs[0]=[last[0],runs[0][1]+M];}return runs;}

/* ---------- section view ---------- */
const ND=360,DTH=TAU/ND,COS=new Float64Array(ND+1),SIN=new Float64Array(ND+1);
for(let a=0;a<=ND;a++){COS[a]=Math.cos(a*DTH);SIN[a]=Math.sin(a*DTH);}
function drawMachine(){
  const cv=$('machine');if(cv.hidden)return;const {ctx,w,h}=fit(cv);if(!ctx||!EV)return;const tk=tokens(),e=EV,phi=state.phi,r0=state.scale.r0;
  const Rout=e.maxOut,scale=(Math.min(w,h)/2-18)/Rout,cx=w/2,cy=h/2;
  ctx.fillStyle=tk.stage;ctx.fillRect(0,0,w,h);
  const shift=phi*NT/TAU,Rrot=new Float64Array(ND+1);
  for(let a=0;a<=ND;a++)Rrot[a]=interpR((a%ND)*2-shift);
  const dv=(DYNV&&e.dyn)?DYNV:null,ex=dv?state.dyn.exaggerate/e.r0m:0,rsh=dv?[dv.x*ex,dv.y*ex]:[0,0];
  const psiS=dv?dv.psi:0,offR=dv?dv.off:0,rel=((phi-psiS)%TAU+TAU)%TAU,jRel=Math.round(rel/TAU*NPHI)%NPHI;
  const sIdx=a=>{let k=Math.round((a*DTH-psiS)/TAU*NT)%NT;if(k<0)k+=NT;return k;};
  const curAt=p=>{if(!e.I[p])return 0;const jc=(((jRel-offR/(TAU/NPHI))%NPHI)+NPHI)%NPHI,j0=Math.floor(jc),f=jc-j0;return e.I[p][j0]*(1-f)+e.I[p][(j0+1)%NPHI]*f;};
  const own=(p,extra,shift)=>{ctx.setTransform(window.devicePixelRatio||1,0,0,window.devicePixelRatio||1,0,0);ctx.translate(cx,cy);ctx.scale(scale,-scale);if(shift)ctx.translate(shift[0],shift[1]);if(extra)ctx.rotate(extra);ctx.translate(p.offX,p.offY);ctx.rotate(p.rot*Math.PI/180);};
  const reset=()=>ctx.setTransform(window.devicePixelRatio||1,0,0,window.devicePixelRatio||1,0,0);
  const sd=dv?statorDispOwn:null;
  // stator iron, own frame, by covered run (displaced by the stator modes during dynamic playback)
  own(state.stator,psiS);const so=e.staOwn,oo=e.outerOwnPts,s0=e.s0,runs=coveredRuns(so,state.stator);
  const PO=(i)=>{const k=i%so.M;const d=sd?sd(so.ps[k]):null;return [oo.X[k]+(d?d[0]:0),oo.Y[k]+(d?d[1]:0)];};
  const PB=(i)=>{const k=i%so.M;const d=sd?sd(so.ps[k]):null;return [so.x[k]*s0+(d?d[0]:0),so.y[k]*s0+(d?d[1]:0)];};
  ctx.fillStyle=tk.ironS;
  if(state.stator.covArc>=1){ctx.beginPath();for(let i=0;i<so.M;i++){const p=PO(i);if(i===0)ctx.moveTo(p[0],p[1]);else ctx.lineTo(p[0],p[1]);}ctx.closePath();
    for(let i=0;i<so.M;i++){const p=PB(i);if(i===0)ctx.moveTo(p[0],p[1]);else ctx.lineTo(p[0],p[1]);}ctx.closePath();ctx.fill('evenodd');}
  else for(const r of runs){ctx.beginPath();for(let i=r[0];i<=r[1];i++){const p=PO(i);if(i===r[0])ctx.moveTo(p[0],p[1]);else ctx.lineTo(p[0],p[1]);}
    for(let i=r[1];i>=r[0];i--){const p=PB(i);ctx.lineTo(p[0],p[1]);}ctx.closePath();ctx.fill();}
  reset();
  // field wedges, axis frame
  {ctx.lineWidth=0.8;const B=fieldAt(jRel,offR),bs=e.Bmax>0?1/e.Bmax:0;
    for(let a=0;a<ND;a++){const i=sIdx(a),i1=sIdx(a+1);if(!e.mask[i])continue;let col;
      if(B){col=divCss(B[i]*bs);}else{const g=e.S[i]-Rrot[a];col=heatCss(Math.pow(e.g0/g,0.75));}
      quad(ctx,cx,cy,a*DTH,(a+1)*DTH,Rrot[a]*scale,Rrot[a+1]*scale,e.S[i]*scale,e.S[i1]*scale);ctx.fillStyle=col;ctx.strokeStyle=col;ctx.fill();ctx.stroke();}}
  // rotor, own frame rotated by phi (and shifted by the whirl during dynamic playback)
  own(state.rotor,phi,rsh);const ro=e.rotOwn;
  ctx.beginPath();for(let i=0;i<ro.M;i++){if(i===0)ctx.moveTo(ro.x[i],ro.y[i]);else ctx.lineTo(ro.x[i],ro.y[i]);}ctx.closePath();ctx.fillStyle=tk.ironR;ctx.fill();
  const fR=e.fR;
  if(fR.hasRibbon){const k=fR.k;ctx.globalAlpha=0.92;const M=ro.M,st=8;
    const band=(i0,i1,fn,light,dark,sign)=>{const g0=1+fn(ro.ps[i0]),g1=1+fn(ro.ps[i1%M]);ctx.beginPath();ctx.moveTo(ro.xr[i0],ro.yr[i0]);ctx.lineTo(ro.xr[i1%M],ro.yr[i1%M]);ctx.lineTo(ro.xr[i1%M]*g1,ro.yr[i1%M]*g1);ctx.lineTo(ro.xr[i0]*g0,ro.yr[i0]*g0);ctx.closePath();ctx.fillStyle=sign>=0?light:dark;ctx.fill();};
    for(let i=0;i<M;i+=st){const ps=ro.ps[Math.min(M-1,i+st/2)];
      if(fR.mode==='single')band(i,i+st,fR.rbA,tk.copper2,tk.copper,Math.cos(k*ps/2));
      else if(fR.mode==='envelope'){const aTop=Math.floor(k*ps/Math.PI)%2===0;
        if(aTop){band(i,i+st,fR.rbB,tk.verd2,tk.verd,Math.sin(k*ps/2));band(i,i+st,fR.rbA,tk.copper2,tk.copper,Math.cos(k*ps/2));}
        else{band(i,i+st,fR.rbA,tk.copper2,tk.copper,Math.cos(k*ps/2));band(i,i+st,fR.rbB,tk.verd2,tk.verd,Math.sin(k*ps/2));}}
      else band(i,i+st,fR.rb,tk.copper2,tk.verd,Math.cos(k*ps));}
    ctx.globalAlpha=1;}
  reset();
  const rcx=cx+rsh[0]*scale,rcy=cy-rsh[1]*scale;
  ctx.beginPath();for(let a=0;a<=ND;a++){const r=Rrot[a]*scale;if(a===0)ctx.moveTo(rcx+r*COS[a],rcy-r*SIN[a]);else ctx.lineTo(rcx+r*COS[a],rcy-r*SIN[a]);}ctx.closePath();ctx.strokeStyle='rgba(255,255,255,0.28)';ctx.lineWidth=1;ctx.stroke();
  // conductors, axis frame
  if(e.m){const Imax=Math.max(1e-9,+state.wind.current);
    ctx.font='bold 10px '+tk.mono;ctx.textAlign='center';ctx.textBaseline='middle';
    const Sat=th=>interpArr(e.S,th/TAU*NT),Oat=th=>interpArr(e.outer,th/TAU*NT);
    const bundle=(th0,r,turns,phase,kind)=>{const cur=curAt(phase),act=Math.abs(cur)/Imax,col=tk.sph[phase%6],dir=Math.sign(turns)*Math.sign(cur||0),th=th0+psiS;
      const wr=Math.max(2.5,Math.min(9,2+2.2*Math.sqrt(Math.abs(turns)/Math.max(1,state.wind.turns))*3));const x=cx+r*scale*Math.cos(th),y=cy-r*scale*Math.sin(th);
      ctx.globalAlpha=0.35+0.65*act;ctx.strokeStyle=col;ctx.lineWidth=1.6;
      if(kind==='toroid'){ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(cx+(Oat(th0)+0.03)*scale*Math.cos(th),cy-(Oat(th0)+0.03)*scale*Math.sin(th));ctx.stroke();}
      ctx.beginPath();ctx.arc(x,y,wr,0,TAU);ctx.fillStyle=tk.stage;ctx.fill();ctx.stroke();ctx.fillStyle=col;
      if(dir>0){ctx.beginPath();ctx.arc(x,y,Math.max(1.5,wr*0.3),0,TAU);ctx.fill();}else if(dir<0){ctx.beginPath();ctx.moveTo(x-wr*0.5,y-wr*0.5);ctx.lineTo(x+wr*0.5,y+wr*0.5);ctx.moveTo(x+wr*0.5,y-wr*0.5);ctx.lineTo(x-wr*0.5,y+wr*0.5);ctx.stroke();}
      ctx.globalAlpha=1;};
    if(e.wd.sinus){const nb=48;for(let p=0;p<e.m;p++)for(let b=0;b<nb;b++){const th=TAU*(b+0.5)/nb;if(!e.mask[Math.round(th/TAU*NT)%NT])continue;const v=Math.cos(e.wd.sinus.P*th-TAU*p/e.m);if(Math.abs(v)<0.08)continue;bundle(th,Sat(th)+0.025+p*0.035,v*e.wd.sinus.turns*0.5,p,'bar');}}
    else{for(const c of e.wd.coils){const cur=curAt(c.phase);ctx.globalAlpha=0.3+0.6*Math.abs(cur)/Imax;ctx.strokeStyle=tk.sph[c.phase%6];ctx.lineWidth=1.5;const rr=Math.min(Oat(c.center)-0.02,Sat(c.center)+(Oat(c.center)-Sat(c.center))*(c.kind==='lap'?0.75:0.55));
        ctx.beginPath();let d=c.b-c.a;d=((d%TAU)+TAU)%TAU;const n=Math.max(4,Math.ceil(d/0.1));for(let s=0;s<=n;s++){const th=c.a+d*s/n+psiS,r=rr;const x=cx+r*scale*Math.cos(th),y=cy-r*scale*Math.sin(th);if(s===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.stroke();ctx.globalAlpha=1;
        const lx=cx+(rr+0.03)*scale*Math.cos(c.center+psiS),ly=cy-(rr+0.03)*scale*Math.sin(c.center+psiS);ctx.fillStyle=tk.sph[c.phase%6];ctx.fillText(PH_LETTERS[c.phase]+(c.sign<0?'′':''),lx,ly);}
      for(const s of e.wd.stations){bundle(s.theta,Sat(s.theta)+0.03,s.turns,s.phase,s.kind);if(!e.wd.coils.length){const lx=cx+(Sat(s.theta)+0.11)*scale*Math.cos(s.theta+psiS),ly=cy-(Sat(s.theta)+0.11)*scale*Math.sin(s.theta+psiS);ctx.fillStyle=tk.sph[s.phase%6];ctx.fillText(PH_LETTERS[s.phase],lx,ly);}}}}
  const hub=0.2*scale;ctx.beginPath();ctx.arc(rcx,rcy,hub,0,TAU);ctx.fillStyle=tk.stage;ctx.fill();ctx.strokeStyle=tk.stageLine;ctx.lineWidth=1;ctx.stroke();
  const rm=interpR(0)*scale;ctx.beginPath();ctx.moveTo(rcx,rcy);ctx.lineTo(rcx+rm*Math.cos(phi),rcy-rm*Math.sin(phi));ctx.strokeStyle=tk.copper2;ctx.lineWidth=1.5;ctx.stroke();
  ctx.beginPath();ctx.arc(rcx+rm*Math.cos(phi),rcy-rm*Math.sin(phi),3.5,0,TAU);ctx.fillStyle=tk.copper2;ctx.fill();
  if(dv){ctx.strokeStyle=tk.stageDim;ctx.setLineDash([2,3]);ctx.beginPath();ctx.moveTo(cx-6,cy);ctx.lineTo(cx+6,cy);ctx.moveTo(cx,cy-6);ctx.lineTo(cx,cy+6);ctx.stroke();ctx.setLineDash([]);}
  ctx.font='10px '+tk.mono;ctx.fillStyle=tk.stageDim;ctx.strokeStyle=tk.stageLine;ctx.textAlign='center';ctx.textBaseline='middle';
  for(let q=0;q<4;q++){const a=q*Math.PI/2,r0s=Rout*scale,r1=r0s+6,rl=r0s+14;ctx.beginPath();ctx.moveTo(cx+r0s*Math.cos(a),cy-r0s*Math.sin(a));ctx.lineTo(cx+r1*Math.cos(a),cy-r1*Math.sin(a));ctx.stroke();ctx.fillText((q*90)+'°',cx+rl*Math.cos(a),cy-rl*Math.sin(a));}
  ctx.textAlign='left';ctx.fillText('Ø '+(2*Rout*r0).toFixed(0)+' mm · ℓ '+state.scale.stack+' mm · '+e.wd.topology+(dv?('  ·  t '+(dv.t*1e3).toFixed(1)+' ms · '+(dv.om*60/TAU).toFixed(0)+' rpm · z '+(dv.z*1e6).toFixed(0)+' µm · field '+(dv.off*180/Math.PI).toFixed(1)+'° · motion ×'+state.dyn.exaggerate+(SIM&&SIM.touched?' · touchdown':'')):''),10,h-12);
}
function statorDispOwn(psi){ // own-frame displacement (×r0) of a stator vertex at own angle psi, from the current dynamic state
  const dv=DYNV,dy=EV.dyn;if(!dv||!dy)return null;const ex=state.dyn.exaggerate/EV.r0m,rot=state.stator.rot*Math.PI/180,th=psi+rot;let dx=0,dy2=0;
  let segBest=-1,segD=1e9;
  for(let k=2;k<dy.dofs.length;k++){const df=dy.dofs[k],q=dv.q[k-2]||0;
    if(df.mode==='seg'){let d=Math.abs(((th-df.theta)%TAU+TAU)%TAU);if(d>Math.PI)d=TAU-d;if(d<segD){segD=d;segBest=k;}continue;}
    if(!q)continue;const u=df.mode==='n0'?1:df.mode==='n2c'?Math.cos(2*th):Math.sin(2*th);const dr=q*ex*u;dx+=dr*Math.cos(psi);dy2+=dr*Math.sin(psi);}
  if(segBest>=0){const df=dy.dofs[segBest],q=dv.q[segBest-2]||0;if(q){const ax=q*ex*Math.cos(df.theta),ay=q*ex*Math.sin(df.theta);dx+=ax*Math.cos(rot)+ay*Math.sin(rot);dy2+=-ax*Math.sin(rot)+ay*Math.cos(rot);}}
  return [dx,dy2];}

/* ---------- gap map ---------- */
const GM={l:34,r:8,t:8,b:22};
function drawGapMap(){
  const cv=$('gapmap'),{ctx,w,h}=fit(cv);if(!ctx||!EV)return;const tk=tokens();
  ctx.fillStyle=tk.card;ctx.fillRect(0,0,w,h);
  const pw=w-GM.l-GM.r,ph=h-GM.t-GM.b;ctx.imageSmoothingEnabled=true;ctx.drawImage(off,GM.l,GM.t,pw,ph);
  ctx.font='10px '+tk.mono;ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='top';
  for(let q=0;q<=4;q++){const x=GM.l+pw*q/4;ctx.fillText((q*90)+'°',x,GM.t+ph+6);}
  ctx.textAlign='right';ctx.textBaseline='middle';
  for(let q=0;q<=4;q+=2){const y=GM.t+ph*(1-q/4);ctx.fillText((q*90)+'°',GM.l-5,y);}
  ctx.save();ctx.translate(9,GM.t+ph/2);ctx.rotate(-Math.PI/2);ctx.textAlign='center';ctx.fillText('rotor φ',0,0);ctx.restore();
  const y=GM.t+ph*(1-state.phi/TAU);ctx.strokeStyle=tk.ink;ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(GM.l,y+0.5);ctx.lineTo(GM.l+pw,y+0.5);ctx.stroke();ctx.setLineDash([]);
}
function gapAt(x,y,w,h){const pw=w-GM.l-GM.r,ph=h-GM.t-GM.b;const u=(x-GM.l)/pw,v=1-(y-GM.t)/ph;if(u<0||u>1||v<0||v>1)return null;
  const th=u*TAU,ph2=v*TAU;const i=Math.round(th/TAU*NT)%NT;const g=EV.S[i]-interpR(i-ph2*NT/TAU);return {th,ph:ph2,g,covered:!!EV.mask[i]};}

/* ---------- line-chart helpers ---------- */
function xTicks(ctx,tk,x0,pw,y0,hh){ctx.strokeStyle=tk.line2;ctx.lineWidth=1;for(let q=0;q<=4;q++){const x=x0+pw*q/4;ctx.beginPath();ctx.moveTo(x+0.5,y0);ctx.lineTo(x+0.5,y0+hh);ctx.stroke();}}
function xLabels(ctx,tk,x0,pw,y){ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='top';for(let q=0;q<=4;q++)ctx.fillText((q*90)+'°',x0+pw*q/4,y);}

/* ---------- winding functions + gap field ---------- */
const MM={l:50,r:28,t:16,b:20,gap:14};
function drawMMF(){
  const cv=$('mmf'),{ctx,w,h}=fit(cv);if(!ctx||!EV)return;const tk=tokens(),e=EV;
  ctx.fillStyle=tk.card;ctx.fillRect(0,0,w,h);ctx.font='10px '+tk.mono;
  const pw=w-MM.l-MM.r,hN=(h-MM.t-MM.b-MM.gap)*0.55,hB=(h-MM.t-MM.b-MM.gap)*0.45,yN=MM.t,yB=MM.t+hN+MM.gap;
  const X=i=>MM.l+pw*i/NT;
  // uncovered shading
  ctx.fillStyle=tk.line2;for(let i=0;i<NT;i++)if(!e.mask[i])ctx.fillRect(X(i),yN,Math.max(1,pw/NT+0.5),yB+hB-yN);
  if(!e.m){ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(e.wd.note||'no winding',w/2,yN+hN/2);}
  else{let Nmax=0;for(let p=0;p<e.m;p++)for(let i=0;i<NT;i++)Nmax=Math.max(Nmax,Math.abs(e.NP[p][i]));if(Nmax<=0)Nmax=1;
    const Y=v=>yN+hN*(0.5-v/Nmax*0.46);xTicks(ctx,tk,MM.l,pw,yN,hN);ctx.strokeStyle=tk.line;ctx.beginPath();ctx.moveTo(MM.l,Y(0)+0.5);ctx.lineTo(MM.l+pw,Y(0)+0.5);ctx.stroke();
    for(let p=0;p<e.m;p++){ctx.beginPath();for(let i=0;i<=NT;i++){const v=e.NP[p][i%NT];if(i===0)ctx.moveTo(X(i),Y(v));else ctx.lineTo(X(i),Y(v));}ctx.strokeStyle=tk.ph[p%6];ctx.lineWidth=1.6;ctx.lineJoin='round';ctx.stroke();
      let ib=0;for(let i=0;i<NT;i++)if(e.NP[p][i]>e.NP[p][ib])ib=i;ctx.fillStyle=tk.ph[p%6];ctx.textAlign='center';ctx.textBaseline='bottom';ctx.fillText(PH_LETTERS[p],Math.min(Math.max(X(ib),MM.l+6),MM.l+pw-6),Y(e.NP[p][ib])-2);}
    ctx.fillStyle=tk.ink2;ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText('+'+Nmax.toFixed(0)+' t',MM.l-5,yN);ctx.textBaseline='bottom';ctx.fillText('−'+Nmax.toFixed(0)+' t',MM.l-5,yN+hN);}
  ctx.textAlign='left';ctx.textBaseline='bottom';ctx.fillStyle=tk.ink;ctx.fillText('N(θ) winding function per phase · turns',MM.l+4,yN-2);
  // B strip
  const dv0=(DYNV&&e.dyn)?DYNV:null,relM=dv0?(((state.phi-dv0.psi)%TAU+TAU)%TAU):state.phi;const j=Math.round(relM/TAU*NPHI)%NPHI,B=fieldAt(j,dv0?dv0.off:0);const Bs=e.Bmax>0?e.Bmax:1;const YB=v=>yB+hB*(0.5-v/Bs*0.46);
  xTicks(ctx,tk,MM.l,pw,yB,hB);ctx.strokeStyle=tk.line;ctx.beginPath();ctx.moveTo(MM.l,YB(0)+0.5);ctx.lineTo(MM.l+pw,YB(0)+0.5);ctx.stroke();
  if(B){ctx.beginPath();let pen=false;for(let i=0;i<=NT;i++){const k=i%NT;if(!e.mask[k]){pen=false;continue;}const v=B[k];if(!pen){ctx.moveTo(X(i),YB(v));pen=true;}else ctx.lineTo(X(i),YB(v));}ctx.strokeStyle=tk.copper;ctx.lineWidth=1.6;ctx.stroke();}
  else{const base=j*NT;ctx.beginPath();let pen=false;for(let i=0;i<=NT;i++){const k=i%NT;if(!e.mask[k]){pen=false;continue;}const v=MU0*state.wind.turns*state.wind.current*e.P[base+k];if(!pen){ctx.moveTo(X(i),YB(v));pen=true;}else ctx.lineTo(X(i),YB(v));}ctx.strokeStyle=tk.copper;ctx.lineWidth=1.6;ctx.stroke();}
  ctx.fillStyle=tk.ink2;ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText('+'+Bs.toFixed(2)+' T',MM.l-5,yB);ctx.textBaseline='bottom';ctx.fillText('−'+Bs.toFixed(2)+' T',MM.l-5,yB+hB);
  ctx.textAlign='left';ctx.fillStyle=tk.ink;ctx.fillText('B(θ) at φ = '+(state.phi*180/Math.PI).toFixed(0)+'°',MM.l+4,yB-2);
  ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='top';for(let q=0;q<=4;q++)ctx.fillText((q*90)+'°',MM.l+pw*q/4,h-MM.b+6);ctx.textAlign='right';ctx.fillText('stator θ',MM.l+pw,h-MM.b+6);
}

/* ---------- inductance + commutation ---------- */
const IN={l:50,r:28,t:16,b:20,gap:14};
function drawInduct(){
  const cv=$('induct'),{ctx,w,h}=fit(cv);if(!ctx||!EV)return;const tk=tokens(),e=EV;
  ctx.fillStyle=tk.card;ctx.fillRect(0,0,w,h);ctx.font='10px '+tk.mono;
  const pw=w-IN.l-IN.r,hL=(h-IN.t-IN.b-IN.gap)*0.62,hI=(h-IN.t-IN.b-IN.gap)*0.38,yL=IN.t,yI=IN.t+hL+IN.gap;
  if(!e.m){ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(e.wd.note||'no winding',w/2,h/2);return;}
  let Lmax=0;for(let p=0;p<e.m;p++)for(let j=0;j<NPHI;j++)if(e.L[p][j]>Lmax)Lmax=e.L[p][j];if(Lmax<=0)Lmax=1e-9;
  const X=j=>IN.l+pw*j/NPHI,YL=v=>yL+hL*(1-v/Lmax*0.92);
  xTicks(ctx,tk,IN.l,pw,yL,hL);ctx.strokeStyle=tk.line;ctx.beginPath();ctx.moveTo(IN.l,yL+hL+0.5);ctx.lineTo(IN.l+pw,yL+hL+0.5);ctx.stroke();
  for(let p=0;p<e.m;p++){ctx.beginPath();for(let j=0;j<=NPHI;j++){const v=e.L[p][j%NPHI];if(j===0)ctx.moveTo(X(j),YL(v));else ctx.lineTo(X(j),YL(v));}ctx.strokeStyle=tk.ph[p%6];ctx.lineWidth=2;ctx.lineJoin='round';ctx.stroke();
    let jb=0;for(let j=0;j<NPHI;j++)if(e.L[p][j]>e.L[p][jb])jb=j;ctx.fillStyle=tk.ph[p%6];ctx.textAlign='center';ctx.textBaseline='bottom';ctx.fillText(PH_LETTERS[p],Math.min(Math.max(X(jb),IN.l+6),IN.l+pw-6),YL(e.L[p][jb])-3);}
  ctx.fillStyle=tk.ink2;ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText(fmtSI(Lmax,'H',1),IN.l-5,yL);ctx.textBaseline='bottom';ctx.fillText('0',IN.l-5,yL+hL);
  ctx.textAlign='left';ctx.fillStyle=tk.ink;ctx.fillText('L (phase self-inductance)',IN.l+4,yL-2);
  const Imax=Math.max(1e-9,+state.wind.current),YI=v=>yI+hI*(0.5-v/Imax*0.42);
  xTicks(ctx,tk,IN.l,pw,yI,hI);ctx.strokeStyle=tk.line;ctx.beginPath();ctx.moveTo(IN.l,YI(0)+0.5);ctx.lineTo(IN.l+pw,YI(0)+0.5);ctx.stroke();
  for(let p=0;p<e.m;p++){ctx.beginPath();for(let j=0;j<=NPHI;j++){const v=e.I[p][j%NPHI];if(j===0)ctx.moveTo(X(j),YI(v));else ctx.lineTo(X(j),YI(v));}ctx.strokeStyle=tk.ph[p%6];ctx.lineWidth=1.5;ctx.stroke();}
  ctx.fillStyle=tk.ink2;ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText('+'+Imax+' A',IN.l-5,yI);ctx.textBaseline='bottom';ctx.fillText('−'+Imax+' A',IN.l-5,yI+hI);
  ctx.textAlign='left';ctx.fillStyle=tk.ink;ctx.fillText('i (phase currents · '+(RIG_SPEC.excite.options.find(o=>o[0]===state.wind.excite)||[0,state.wind.excite])[1]+')',IN.l+4,yI-2);
  const xc=IN.l+pw*state.phi/TAU;ctx.strokeStyle=tk.ink;ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(xc+0.5,yL);ctx.lineTo(xc+0.5,yI+hI);ctx.stroke();ctx.setLineDash([]);
  xLabels(ctx,tk,IN.l,pw,h-IN.b+6);
}

/* ---------- energy / torque ---------- */
const EN={l:50,r:10,t:16,b:20,gap:14};
function drawEnergy(){
  const cv=$('energy'),{ctx,w,h}=fit(cv);if(!ctx||!EV)return;const tk=tokens(),e=EV;
  ctx.fillStyle=tk.card;ctx.fillRect(0,0,w,h);
  const pw=w-EN.l-EN.r,sh=(h-EN.t-EN.b-EN.gap)/2;
  const strips=[{data:e.W,color:tk.copper,label:'W′ co-energy at the applied currents',y0:EN.t,area:true,unit:'J',zero:false},{data:e.T,color:tk.verd,label:'T = ∂W′/∂φ at fixed currents',y0:EN.t+sh+EN.gap,area:false,unit:'N·m',zero:true}];
  ctx.font='10px '+tk.mono;
  for(const s of strips){let mn=1e9,mx=-1e9;for(let j=0;j<NPHI;j++){if(s.data[j]<mn)mn=s.data[j];if(s.data[j]>mx)mx=s.data[j];}
    if(s.zero){const amp=Math.max(Math.abs(mn),Math.abs(mx))*1.12||1;mn=-amp;mx=amp;}else{const pad=(mx-mn)*0.12||Math.abs(mx)*0.05||1;mn-=pad;mx+=pad;}
    const Y=v=>s.y0+sh*(1-(v-mn)/(mx-mn)),X=j=>EN.l+pw*j/NPHI;
    xTicks(ctx,tk,EN.l,pw,s.y0,sh);
    const yz=s.zero?Y(0):s.y0+sh;ctx.strokeStyle=tk.line;ctx.beginPath();ctx.moveTo(EN.l,yz+0.5);ctx.lineTo(EN.l+pw,yz+0.5);ctx.stroke();
    ctx.beginPath();for(let j=0;j<=NPHI;j++){const v=s.data[j%NPHI];if(j===0)ctx.moveTo(X(j),Y(v));else ctx.lineTo(X(j),Y(v));}
    if(s.area){ctx.save();ctx.lineTo(X(NPHI),yz);ctx.lineTo(X(0),yz);ctx.closePath();ctx.globalAlpha=0.14;ctx.fillStyle=s.color;ctx.fill();ctx.restore();
      ctx.beginPath();for(let j=0;j<=NPHI;j++){const v=s.data[j%NPHI];if(j===0)ctx.moveTo(X(j),Y(v));else ctx.lineTo(X(j),Y(v));}}
    ctx.strokeStyle=s.color;ctx.lineWidth=2;ctx.lineJoin='round';ctx.stroke();
    ctx.fillStyle=tk.ink2;ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText(fmtSI(mx,s.unit,1),EN.l-5,s.y0);ctx.textBaseline='bottom';ctx.fillText(fmtSI(mn,s.unit,1),EN.l-5,s.y0+sh);
    ctx.textAlign='left';ctx.textBaseline='bottom';ctx.fillStyle=tk.ink;ctx.fillText(s.label,EN.l+4,s.y0-2);
    const jc=Math.round(state.phi/TAU*NPHI)%NPHI,xc=EN.l+pw*state.phi/TAU,vc=s.data[jc];
    ctx.strokeStyle=tk.ink;ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(xc+0.5,s.y0);ctx.lineTo(xc+0.5,s.y0+sh);ctx.stroke();ctx.setLineDash([]);
    ctx.beginPath();ctx.arc(xc,Y(vc),4,0,TAU);ctx.fillStyle=s.color;ctx.fill();ctx.strokeStyle=tk.card;ctx.lineWidth=2;ctx.stroke();
    ctx.fillStyle=tk.ink;ctx.textAlign='right';ctx.textBaseline='bottom';ctx.fillText(fmtSI(vc,s.unit),EN.l+pw,s.y0-2);
  }
  xLabels(ctx,tk,EN.l,pw,h-EN.b+6);
}

/* ---------- spectra ---------- */
const SP={l:66,r:10,t:10,b:22};
function drawSpectra(){
  const cv=$('spectra'),{ctx,w,h}=fit(cv);if(!ctx||!EV)return;const tk=tokens(),e=EV;
  ctx.fillStyle=tk.card;ctx.fillRect(0,0,w,h);
  const pw=w-SP.l-SP.r,ph=h-SP.t-SP.b,rowH=ph/3,bw=pw/NSHOW;
  const mx=sp=>{let m=0;for(let n=1;n<=NSHOW;n++)if(sp[n]>m)m=sp[n];return m;};
  const mR=mx(e.specR),mS=mx(e.specS),mW=mx(e.specW);
  const shared=[];for(let n=1;n<=NSHOW;n++)if(mR>0&&mS>0&&e.specR[n]/mR>0.03&&e.specS[n]/mS>0.03)shared.push(n);
  const sharedSet=new Set(shared);
  const rows=[{label:'rotor R(θ)',spec:e.specR,max:mR,color:tk.steel},{label:'stator S(θ)',spec:e.specS,max:mS,color:tk.ink2},{label:e.torqueMode?'torque T(φ)':'W′(φ)',spec:e.specW,max:mW,color:tk.copper}];
  ctx.font='10px '+tk.mono;
  rows.forEach((r,ri)=>{const y0=SP.t+ri*rowH,base=y0+rowH-6;
    ctx.strokeStyle=tk.line2;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(SP.l,base+0.5);ctx.lineTo(SP.l+pw,base+0.5);ctx.stroke();
    ctx.fillStyle=tk.ink;ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText(r.label,SP.l-8,y0+2);
    ctx.fillStyle=tk.ink2;ctx.fillText(r.max>0?('max '+r.max.toExponential(1)):'flat',SP.l-8,y0+14);
    if(r.max<=0)return;
    for(let n=1;n<=NSHOW;n++){const v=r.spec[n]/r.max;if(v<=0.002)continue;const x=SP.l+(n-1)*bw+1,bh=Math.max(1.5,v*(rowH-14));
      ctx.globalAlpha=(ri===2&&!sharedSet.has(n))?0.35:1;ctx.fillStyle=r.color;ctx.fillRect(x,base-bh,Math.max(1,bw-2),bh);}
    ctx.globalAlpha=1;
    if(ri===2&&e.dom&&e.dom<=NSHOW){const x=SP.l+(e.dom-0.5)*bw;ctx.fillStyle=tk.copper;ctx.textAlign='center';ctx.textBaseline='bottom';ctx.fillText('n* = '+e.dom,Math.min(Math.max(x,SP.l+22),SP.l+pw-22),y0+rowH-6-(rowH-14)-1);}
    else if(ri===2&&e.dom>NSHOW){ctx.fillStyle=tk.copper;ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText('n* = '+e.dom+' (off scale)',SP.l+pw,y0+2);}
  });
  const axY=SP.t+ph;ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='top';
  for(let n=8;n<=NSHOW;n+=8)ctx.fillText(String(n),SP.l+(n-0.5)*bw,axY+4);ctx.fillText('1',SP.l+0.5*bw,axY+4);
  ctx.fillStyle=tk.copper;for(const n of shared){const x=SP.l+(n-0.5)*bw;ctx.fillRect(x-1.5,axY-1,3,3);}
  ctx.textAlign='right';ctx.fillStyle=tk.ink2;ctx.fillText('order n',SP.l+pw,axY+14);
  ctx.textAlign='left';ctx.fillText(shared.length?('shared: '+shared.slice(0,10).join(', ')+(shared.length>10?' …':'')):'no shared orders',SP.l,axY+14);
}

/* ---------- dynamics panels ---------- */
const DY={l:64,r:76,t:16,b:20,gap:14};
function noSim(ctx,tk,w,h){ctx.fillStyle=tk.ink2;ctx.font='10px '+tk.mono;ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(EV&&!EV.dyn?'updating… release the slider':'no simulation',w/2,h/2);}
function timeAxis(ctx,tk,x0,pw,y,dur){ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='top';for(let q=0;q<=4;q++)ctx.fillText((dur*q/4*1e3).toFixed(0)+' ms',x0+pw*q/4,y);}
function drawDynSpeed(){
  const cv=$('dynSpeed'),{ctx,w,h}=fit(cv);if(!ctx)return;const tk=tokens();ctx.fillStyle=tk.card;ctx.fillRect(0,0,w,h);if(!SIM){noSim(ctx,tk,w,h);return;}
  const s=SIM,pw=w-DY.l-DY.r,sh=(h-DY.t-DY.b-2*DY.gap)/3,X=t=>DY.l+pw*t/s.dur;ctx.font='10px '+tk.mono;
  const commLabel=s.comm==='open'?'field lead over rotor (open-loop)':s.comm==='stepped'?'field lead over rotor (stepped)':'commutation advance';
  const strips=[{get:i=>s.om[i]*60/TAU,color:tk.copper,label:'ω rotor speed',unit:'rpm',area:true,zero:false},{get:i=>s.tem[i],color:tk.verd,label:'T electromagnetic torque',unit:'N·m',area:false,zero:true},{get:i=>-s.off[i]*180/Math.PI,color:tk.steel,label:commLabel+' (° mech)',unit:'°',area:false,zero:true}];
  strips.forEach((st,si)=>{const y0=DY.t+si*(sh+DY.gap);let mn=1e9,mx=-1e9;for(let i=0;i<s.n;i++){const v=st.get(i);if(v<mn)mn=v;if(v>mx)mx=v;}
    if(st.zero){const amp=Math.max(Math.abs(mn),Math.abs(mx))*1.12||1;mn=-amp;mx=amp;}else{if(mx-mn<1e-9){mx=mn+1;}const pad=(mx-mn)*0.1;mn=Math.min(0,mn-pad);mx+=pad;}
    const Y=v=>y0+sh*(1-(v-mn)/(mx-mn));xTicks(ctx,tk,DY.l,pw,y0,sh);const yz=Y(0);ctx.strokeStyle=tk.line;ctx.beginPath();ctx.moveTo(DY.l,yz+0.5);ctx.lineTo(DY.l+pw,yz+0.5);ctx.stroke();
    ctx.beginPath();for(let i=0;i<s.n;i++){const x=X(s.t[i]),y=Y(st.get(i));if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}
    if(st.area){ctx.save();ctx.lineTo(X(s.t[s.n-1]),yz);ctx.lineTo(X(0),yz);ctx.closePath();ctx.globalAlpha=0.14;ctx.fillStyle=st.color;ctx.fill();ctx.restore();ctx.beginPath();for(let i=0;i<s.n;i++){const x=X(s.t[i]),y=Y(st.get(i));if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}}
    ctx.strokeStyle=st.color;ctx.lineWidth=1.8;ctx.lineJoin='round';ctx.stroke();
    if(si===0&&state.dyn.mode==='regulate'){ctx.beginPath();for(let i=0;i<s.n;i++){const x=X(s.t[i]),y=y0+sh*(1-s.sc[i]*0.95);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.strokeStyle=tk.ink2;ctx.lineWidth=1;ctx.setLineDash([2,3]);ctx.stroke();ctx.setLineDash([]);
      ctx.fillStyle=tk.ink2;ctx.textAlign='left';ctx.textBaseline='top';ctx.fillText('current ×',DY.l+pw+4,y0);
      const yr=Y(state.dyn.rpmRef);if(yr>y0&&yr<y0+sh){ctx.strokeStyle=tk.ink2;ctx.setLineDash([4,3]);ctx.beginPath();ctx.moveTo(DY.l,yr+0.5);ctx.lineTo(DY.l+pw,yr+0.5);ctx.stroke();ctx.setLineDash([]);}}
    const fv=v=>st.unit==='rpm'?v.toFixed(0):st.unit==='°'?v.toFixed(1)+'°':fmtSI(v,st.unit,1);
    ctx.fillStyle=tk.ink2;ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText(fv(mx),DY.l-5,y0);ctx.textBaseline='bottom';ctx.fillText(fv(mn),DY.l-5,y0+sh);
    ctx.textAlign='left';ctx.fillStyle=tk.ink;ctx.fillText(st.label+(st.unit==='rpm'?' (rpm)':''),DY.l+4,y0-2);
    if(DYNV){const xc=X(DYNV.t);ctx.strokeStyle=tk.ink;ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(xc+0.5,y0);ctx.lineTo(xc+0.5,y0+sh);ctx.stroke();ctx.setLineDash([]);}
  });
  timeAxis(ctx,tk,DY.l,pw,h-DY.b+6,s.dur);
}
function drawDynOrbit(){
  const cv=$('dynOrbit'),{ctx,w,h}=fit(cv);if(!ctx)return;const tk=tokens();ctx.fillStyle=tk.card;ctx.fillRect(0,0,w,h);if(!SIM){noSim(ctx,tk,w,h);return;}
  const s=SIM;ctx.font='10px '+tk.mono;
  const side=Math.min(h-DY.t-DY.b,w*0.42),ox=DY.l-12,oy=DY.t,cx=ox+side/2,cy=oy+side/2;
  let rmax=s.touch;for(let i=0;i<s.n;i++)rmax=Math.max(rmax,Math.hypot(s.x[i],s.y[i]));const sc=(side/2-6)/rmax;
  ctx.strokeStyle=tk.line2;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(cx-side/2,cy+0.5);ctx.lineTo(cx+side/2,cy+0.5);ctx.moveTo(cx+0.5,cy-side/2);ctx.lineTo(cx+0.5,cy+side/2);ctx.stroke();
  ctx.setLineDash([3,3]);ctx.strokeStyle=tk.ink2;if(s.clr>0){ctx.beginPath();ctx.arc(cx,cy,s.clr*sc,0,TAU);ctx.stroke();}ctx.strokeStyle=s.touched?tk.copper:tk.line;ctx.beginPath();ctx.arc(cx,cy,s.touch*sc,0,TAU);ctx.stroke();ctx.setLineDash([]);
  ctx.beginPath();for(let i=0;i<s.n;i++){const x=cx+s.x[i]*sc,y=cy-s.y[i]*sc;if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.strokeStyle=tk.copper;ctx.lineWidth=1.2;ctx.globalAlpha=0.85;ctx.stroke();ctx.globalAlpha=1;
  const iN=DYNV?Math.min(s.n-1,Math.round(DYNV.t/s.dt)):s.n-1;ctx.beginPath();ctx.arc(cx+s.x[iN]*sc,cy-s.y[iN]*sc,3.5,0,TAU);ctx.fillStyle=tk.copper;ctx.fill();
  ctx.fillStyle=tk.ink;ctx.textAlign='left';ctx.textBaseline='bottom';ctx.fillText('rotor centre · '+(rmax*1e6).toFixed(0)+' µm box',ox,oy-3);
  ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='top';ctx.fillText('x',cx+side/2-6,cy+3);ctx.fillText(s.touched?'touchdown radius':'touchdown',cx,cy+side/2-12);
  // mode traces
  const tx=ox+side+30,tw=w-tx-DY.r,ty=DY.t,th=h-DY.t-DY.b;if(tw<60)return;
  xTicks(ctx,tk,tx,tw,ty,th);let qm=1e-9;for(let k=0;k<s.nS;k++)for(let i=0;i<s.n;i++)qm=Math.max(qm,Math.abs(s.q[k][i]));for(let i=0;i<s.n;i++)qm=Math.max(qm,Math.abs(s.z[i]),Math.abs(s.tor[i]*s.Rb));
  const Y=v=>ty+th*(0.5-v/qm*0.46),X=t=>tx+tw*t/s.dur;ctx.strokeStyle=tk.line;ctx.beginPath();ctx.moveTo(tx,Y(0)+0.5);ctx.lineTo(tx+tw,Y(0)+0.5);ctx.stroke();
  const cols=[tk.verd,tk.ph[2],tk.ph[3],tk.ph[4],tk.ph[5],tk.steel,tk.ph[0],tk.ph[1],tk.verd2,tk.copper2,tk.ink2,tk.line];
  for(let k=0;k<s.nS;k++){ctx.beginPath();for(let i=0;i<s.n;i++){const x=X(s.t[i]),y=Y(s.q[k][i]);if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.strokeStyle=cols[k%cols.length];ctx.lineWidth=s.driven[k]?2.2:1.3;ctx.stroke();
    ctx.fillStyle=cols[k%cols.length];ctx.textAlign='left';ctx.textBaseline='middle';ctx.fillText(s.dofs[k+2].name.replace('yoke ','')+(s.driven[k]?' (driven)':''),tx+tw+4,Y(s.q[k][s.n-1]));}
  // axial excursion and torsional rocking (as bore tangential displacement), dashed, on the same µm scale
  const extra=[{get:i=>s.z[i],name:'rotor axial z',color:tk.copper2},{get:i=>s.tor[i]*s.Rb,name:'carrier torsion ×R',color:tk.ink2}];
  ctx.setLineDash([3,3]);for(const ex of extra){let mxv=0;for(let i=0;i<s.n;i++)mxv=Math.max(mxv,Math.abs(ex.get(i)));if(mxv<1e-12)continue;ctx.beginPath();for(let i=0;i<s.n;i++){const x=X(s.t[i]),y=Y(ex.get(i));if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.strokeStyle=ex.color;ctx.lineWidth=1.2;ctx.stroke();
    ctx.fillStyle=ex.color;ctx.textAlign='left';ctx.textBaseline='middle';ctx.fillText(ex.name,tx+tw+4,Y(ex.get(s.n-1)));}ctx.setLineDash([]);
  ctx.fillStyle=tk.ink2;ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText('+'+(qm*1e6).toFixed(2)+' µm',tx-5,ty);ctx.textBaseline='bottom';ctx.fillText('−'+(qm*1e6).toFixed(2)+' µm',tx-5,ty+th);
  ctx.textAlign='left';ctx.fillStyle=tk.ink;ctx.fillText((s.free?'yoke modes':'yoke rigid')+(s.driven.some(x=>x)?' · driven':'')+' · axial · torsion',tx+4,ty-2);
  if(DYNV){const xc=X(DYNV.t);ctx.strokeStyle=tk.ink;ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(xc+0.5,ty);ctx.lineTo(xc+0.5,ty+th);ctx.stroke();ctx.setLineDash([]);}
  timeAxis(ctx,tk,tx,tw,h-DY.b+6,s.dur);
}
function dft(arr,n0,N){const out=new Float64Array(N/2);let mean=0;for(let i=0;i<N;i++)mean+=arr[n0+i];mean/=N;
  for(let k=1;k<N/2;k++){let re=0,im=0;const wk=TAU*k/N;for(let i=0;i<N;i++){const v=arr[n0+i]-mean;re+=v*Math.cos(wk*i);im-=v*Math.sin(wk*i);}out[k]=2*Math.hypot(re,im)/N;}return out;}
function drawDynSpec(){
  const cv=$('dynSpec'),{ctx,w,h}=fit(cv);if(!ctx)return;const tk=tokens();ctx.fillStyle=tk.card;ctx.fillRect(0,0,w,h);if(!SIM){noSim(ctx,tk,w,h);return;}
  const s=SIM,pw=w-DY.l-DY.r,ph=h-DY.t-DY.b;ctx.font='10px '+tk.mono;
  let N=1;while(N*2<=Math.floor(s.n*0.6))N*=2;N=Math.min(N,2048);const n0=s.n-N;if(N<16){noSim(ctx,tk,w,h);return;}
  const df=1/(N*s.dt),fNy=0.5/s.dt;const series=[];
  const rr=new Float64Array(s.n);for(let i=0;i<s.n;i++)rr[i]=Math.hypot(s.x[i],s.y[i]);series.push({name:'rotor radial',spec:dft(rr,n0,N),color:tk.copper});
  const cols=[tk.verd,tk.ph[2],tk.ph[3],tk.ph[4],tk.ph[5],tk.steel,tk.ph[0],tk.ph[1],tk.verd2,tk.copper2,tk.ink2,tk.line];
  for(let k=0;k<s.nS;k++)series.push({name:s.dofs[k+2].name.replace('yoke ',''),spec:dft(s.q[k],n0,N),color:cols[k%cols.length]});
  series.push({name:'rotor axial',spec:dft(s.z,n0,N),color:tk.copper2});const torR=new Float64Array(s.n);for(let i=0;i<s.n;i++)torR[i]=s.tor[i]*s.Rb;series.push({name:'torsion ×R',spec:dft(torR,n0,N),color:tk.ink2});
  let mx=0;for(const se of series)for(let k=1;k<N/2;k++)mx=Math.max(mx,se.spec[k]);if(mx<=0)mx=1;
  const X=f=>DY.l+pw*f/fNy,Y=v=>DY.t+ph*(1-Math.log10(1+99*v/mx)/2);
  ctx.strokeStyle=tk.line2;ctx.lineWidth=1;for(let q=0;q<=4;q++){const x=DY.l+pw*q/4;ctx.beginPath();ctx.moveTo(x+0.5,DY.t);ctx.lineTo(x+0.5,DY.t+ph);ctx.stroke();}
  ctx.strokeStyle=tk.line;ctx.beginPath();ctx.moveTo(DY.l,DY.t+ph+0.5);ctx.lineTo(DY.l+pw,DY.t+ph+0.5);ctx.stroke();
  // markers: rotation frequency, its dominant ripple order, the yoke natural frequency
  const marks=[[s.fRot,'1×'],[s.fRot*Math.max(1,EV.dom||1),(EV.dom||1)+'×']];if(s.free)marks.push([state.dyn.statorFn,'f_n']);if(state.dyn.actPattern!=='none')marks.push([state.dyn.actFreq,'stroke']);if(state.dyn.torMode==='compliant')marks.push([state.dyn.torFn,'f_tor']);if(state.dyn.axialAct!=='none')marks.push([state.dyn.axialFreq,'axial']);
  ctx.setLineDash([2,3]);for(const [f,lab] of marks){if(!(f>0)||f>fNy)continue;const x=X(f);ctx.strokeStyle=tk.ink2;ctx.beginPath();ctx.moveTo(x+0.5,DY.t);ctx.lineTo(x+0.5,DY.t+ph);ctx.stroke();ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='bottom';ctx.fillText(lab,x,DY.t-2);}ctx.setLineDash([]);
  series.forEach((se,si)=>{ctx.beginPath();for(let k=1;k<N/2;k++){const x=X(k*df),y=Y(se.spec[k]);if(k===1)ctx.moveTo(x,y);else ctx.lineTo(x,y);}ctx.strokeStyle=se.color;ctx.lineWidth=si===0?1.6:1.2;ctx.stroke();
    ctx.fillStyle=se.color;ctx.textAlign='left';ctx.textBaseline='top';ctx.fillText(se.name,DY.l+pw+4,DY.t+si*12);});
  ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='top';for(let q=0;q<=4;q++)ctx.fillText((fNy*q/4>=1000?(fNy*q/4/1000).toFixed(1)+' kHz':(fNy*q/4).toFixed(0)+' Hz'),DY.l+pw*q/4,h-DY.b+6);
  ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText((mx*1e6).toFixed(2)+' µm',DY.l-5,DY.t);ctx.textBaseline='bottom';ctx.fillText('log',DY.l-5,DY.t+ph);
  ctx.textAlign='left';ctx.fillStyle=tk.ink;ctx.fillText('|displacement|(f), last '+(N*s.dt*1e3).toFixed(0)+' ms',DY.l+4,DY.t-2);
}

/* ---------- sweep ---------- */
let SW=null;
const SWM={l:46,r:12,t:10,b:36};
function axisValues(ax,min,max){const n=Math.max(1,Math.min(20,Math.round((max-min)/ax.step)+1));const vals=[];
  for(let i=0;i<n;i++){let v=min+(max-min)*(n===1?0:i/(n-1));v=+(Math.round(v/ax.step)*ax.step).toFixed(4);if(!vals.length||vals[vals.length-1]!==v)vals.push(v);}return vals;}
function runSweep(){
  const ax=axisById(sweepCfg.x),ay=axisById(sweepCfg.y);if(!ax||!ay)return;
  const xs=axisValues(ax,sweepCfg.xmin,sweepCfg.xmax),ys=axisValues(ay,sweepCfg.ymin,sweepCfg.ymax),metric=METRICS[sweepCfg.metric];
  const res=new Float64Array(xs.length*ys.length).fill(NaN);
  SW={xs,ys,res,ax,ay,metricId:sweepCfg.metric,row:0,done:false};const my=SW;
  $('swMsg').textContent='computing…';
  const base=JSON.stringify({rotor:state.rotor,stator:state.stator,wind:state.wind,scale:state.scale,gap:state.gap,phi:0});
  function stepRow(){if(SW!==my)return;const yi=my.row;
    for(let xi=0;xi<xs.length;xi++){const st=JSON.parse(base);setP(st,ax.id,xs[xi]);setP(st,ay.id,ys[yi]);
      try{const ev=evaluate(st,360,120,{dom:!!metric.dom,bmax:!!metric.bmax});res[yi*xs.length+xi]=metric.get(ev);}catch(err){res[yi*xs.length+xi]=NaN;}}
    my.row++;$('swMsg').textContent='row '+my.row+' / '+ys.length;drawSweep();
    if(my.row<ys.length)setTimeout(stepRow,0);else{my.done=true;$('swMsg').textContent=xs.length+'×'+ys.length+' cells';drawSweep();}}
  setTimeout(stepRow,0);
}
function drawSweep(){
  const cv=$('sweep'),{ctx,w,h}=fit(cv);if(!ctx)return;const tk=tokens();
  ctx.fillStyle=tk.card;ctx.fillRect(0,0,w,h);if(!SW)return;
  const {xs,ys,res,ax,ay}=SW,pw=w-SWM.l-SWM.r,ph=h-SWM.t-SWM.b,cw=pw/xs.length,ch=ph/ys.length;
  let mn=Infinity,mx=-Infinity;for(let i=0;i<res.length;i++){const v=res[i];if(v===v){if(v<mn)mn=v;if(v>mx)mx=v;}}
  if(mn===Infinity){mn=0;mx=1;}if(mx-mn<1e-18)mx=mn+1e-18;
  for(let yi=0;yi<ys.length;yi++)for(let xi=0;xi<xs.length;xi++){const v=res[yi*xs.length+xi];if(v!==v)continue;
    const x=SWM.l+xi*cw,y=SWM.t+(ys.length-1-yi)*ch;ctx.fillStyle=heatCss((v-mn)/(mx-mn));ctx.fillRect(x,y,Math.ceil(cw)-1,Math.ceil(ch)-1);}
  const cxv=getP(state,ax.id),cyv=getP(state,ay.id);const near=(arr,v,stp)=>{let b=-1,bd=Infinity;arr.forEach((a,i)=>{const d=Math.abs(a-v);if(d<bd){bd=d;b=i;}});return bd<=stp*0.51?b:-1;};
  const xi=near(xs,cxv,ax.step),yi=near(ys,cyv,ay.step);
  if(xi>=0&&yi>=0){ctx.strokeStyle=tk.ink;ctx.lineWidth=2;ctx.strokeRect(SWM.l+xi*cw+1,SWM.t+(ys.length-1-yi)*ch+1,Math.ceil(cw)-3,Math.ceil(ch)-3);}
  ctx.font='10px '+tk.mono;ctx.fillStyle=tk.ink2;ctx.textAlign='center';ctx.textBaseline='top';
  const fx=v=>fmtStep(v,ax.step),fy=v=>fmtStep(v,ay.step);
  ctx.fillText(fx(xs[0]),SWM.l+cw/2,SWM.t+ph+4);ctx.fillText(fx(xs[xs.length-1]),SWM.l+pw-cw/2,SWM.t+ph+4);if(xs.length>2)ctx.fillText(fx(xs[xs.length>>1]),SWM.l+((xs.length>>1)+0.5)*cw,SWM.t+ph+4);
  ctx.fillStyle=tk.ink;ctx.fillText(ax.label,SWM.l+pw/2,SWM.t+ph+18);
  ctx.fillStyle=tk.ink2;ctx.textAlign='right';ctx.textBaseline='middle';
  ctx.fillText(fy(ys[0]),SWM.l-5,SWM.t+ph-ch/2);ctx.fillText(fy(ys[ys.length-1]),SWM.l-5,SWM.t+ch/2);
  ctx.save();ctx.translate(10,SWM.t+ph/2);ctx.rotate(-Math.PI/2);ctx.textAlign='center';ctx.fillStyle=tk.ink;ctx.fillText(ay.label,0,0);ctx.restore();
  ctx.textAlign='left';ctx.textBaseline='bottom';ctx.fillStyle=tk.ink2;ctx.fillText(METRICS[SW.metricId].label+'  ·  '+METRICS[SW.metricId].fmt(mn)+' → '+METRICS[SW.metricId].fmt(mx),SWM.l,SWM.t-1);
}
function sweepCell(x,y,w,h){if(!SW)return null;const pw=w-SWM.l-SWM.r,ph=h-SWM.t-SWM.b;const xi=Math.floor((x-SWM.l)/pw*SW.xs.length),yi=SW.ys.length-1-Math.floor((y-SWM.t)/ph*SW.ys.length);
  if(xi<0||yi<0||xi>=SW.xs.length||yi>=SW.ys.length)return null;return {xi,yi,v:SW.res[yi*SW.xs.length+xi]};}

/* ---------- the geometry as the SCAD's assignments, and back ---------- */
function assignmentsOf(st){
  const out={r0:+st.scale.r0,stack:+st.scale.stack,gap:+st.gap,phi:+(st.phi*180/Math.PI).toFixed(2)};
  for(const side of ['rotor','stator'])for(const k of SCAD_NAMES.side)out[side+'_'+snake(k)]=st[side][k];
  for(const k in SCAD_NAMES.stator)out[SCAD_NAMES.stator[k]]=st.stator[k];
  for(const k in SCAD_NAMES.wind)out[SCAD_NAMES.wind[k]]=st.wind[k];
  out.phases=out.phases|0;out.turns=out.turns|0;out.pitch=out.pitch|0;out.slots=out.slots|0;out.pole_pairs=out.pole_pairs|0;
  return out;}
function stateFrom(values,st){ // the panel's state from a text's assignments; names the text lacks keep their value
  const has=(k)=>values[k]!==undefined&&values[k]!==null;
  const num=(k,cur)=>has(k)&&typeof values[k]==='number'&&isFinite(values[k])?values[k]:cur;
  const str=(k,cur)=>has(k)&&typeof values[k]==='string'?values[k]:cur;
  st.scale.r0=num('r0',st.scale.r0);st.scale.stack=num('stack',st.scale.stack);st.gap=num('gap',st.gap);
  if(has('phi'))st.phi=((num('phi',0)*Math.PI/180)%TAU+TAU)%TAU;
  for(const side of ['rotor','stator'])for(const k of SCAD_NAMES.side){const n=side+'_'+snake(k);st[side][k]=typeof st[side][k]==='string'?str(n,st[side][k]):num(n,st[side][k]);}
  for(const k in SCAD_NAMES.stator){const n=SCAD_NAMES.stator[k];st.stator[k]=typeof st.stator[k]==='string'?str(n,st.stator[k]):num(n,st.stator[k]);}
  for(const k in SCAD_NAMES.wind){const n=SCAD_NAMES.wind[k];st.wind[k]=typeof st.wind[k]==='string'?str(n,st.wind[k]):num(n,st.wind[k]);}
  return st;}
function valuesOfText(text){const at=lastOf(parseAssignments(text||''));const out={};for(const name in at){const a=at[name];if(!a.computed)out[name]=a.value;}return out;}

/* ---------- the rig document ---------- */
function rigOf(st){const r={};for(const k of RIG_EXCITE)r[k]=st.wind[k];for(const k in DYN_DEFAULT)r[k]=st.dyn[k];return r;}
function rigText(st){return JSON.stringify(rigOf(st),null,1).replace(/\n\s*/g,(m)=>m.length>2?'\n ':m);}
const RIG_SPEC={};for(const g of DYN_SPECS)for(const it of g.items)RIG_SPEC[it.key]=it;
for(const g of WIND_SPECS)for(const it of g.items)if(RIG_EXCITE.includes(it.key))RIG_SPEC[it.key]=it;
function readRig(text){ // {rig, errors[]}: a value outside its range is clamped and said; an unknown key refused
  let doc;try{doc=JSON.parse(text);}catch(err){return {rig:null,errors:['not JSON: '+err.message]};}
  if(!doc||typeof doc!=='object'||Array.isArray(doc))return {rig:null,errors:['the rig is an object of settings']};
  const rig={},errors=[];
  for(const k in doc){const spec=RIG_SPEC[k];if(!spec){errors.push('unknown setting '+k);continue;}let v=doc[k];
    if(spec.type==='select'){v=String(v);if(!spec.options.some(o=>o[0]===v)){errors.push(k+': one of '+spec.options.map(o=>o[0]).join(', '));continue;}}
    else{v=+v;if(!isFinite(v)){errors.push(k+': a number');continue;}if(v<spec.min||v>spec.max){errors.push(k+': '+spec.min+' to '+spec.max+', so '+Math.min(spec.max,Math.max(spec.min,v)));v=Math.min(spec.max,Math.max(spec.min,v));}}
    rig[k]=v;}
  return {rig,errors};}
function applyRig(rig){let excitation=false;for(const k in rig){if(RIG_EXCITE.includes(k)){if(state.wind[k]!==rig[k])excitation=true;state.wind[k]=rig[k];}else state.dyn[k]=rig[k];}
  if((state.dyn.playback==='dyn')!==(playback==='dyn'))setPlayback(state.dyn.playback);return excitation;}

/* ---------- the sweep spec: "stator_teeth_n 3..24 × rotor_rib_k 0..12 → mean_torque" ---------- */
function axisOfName(name){ // a SCAD name -> the panel's axis
  for(const a of AXES){const [grp,key]=a.id.split('.');const scad=grp==='scale'?key:grp==='gap'?'gap':grp==='wind'?SCAD_NAMES.wind[key]:grp==='stator'&&SCAD_NAMES.stator[key]?SCAD_NAMES.stator[key]:grp+'_'+snake(key);if(scad===name)return a;}
  return null;}
function nameOfAxis(id){const [grp,key]=id.split('.');return grp==='scale'?key:grp==='gap'?'gap':grp==='wind'?SCAD_NAMES.wind[key]:grp==='stator'&&SCAD_NAMES.stator[key]?SCAD_NAMES.stator[key]:grp+'_'+snake(key);}
function readSweep(text){
  const m=/^\s*(\w+)\s+(-?[\d.]+)\s*\.\.\s*(-?[\d.]+)\s*[x×,]\s*(\w+)\s+(-?[\d.]+)\s*\.\.\s*(-?[\d.]+)\s*(?:→|->|:)\s*(\w+)\s*$/.exec(text||'');
  if(!m)return {error:'x from..to × y from..to → metric'};
  const ax=axisOfName(m[1]),ay=axisOfName(m[4]);if(!ax)return {error:'no axis '+m[1]};if(!ay)return {error:'no axis '+m[4]};
  const metric=SWEEP_METRIC[m[7]];if(!metric)return {error:'metric: '+Object.keys(SWEEP_METRIC).join(', ')};
  const c=(v,a)=>Math.min(a.max,Math.max(a.min,+v));
  return {cfg:{x:ax.id,xmin:c(m[2],ax),xmax:c(m[3],ax),y:ay.id,ymin:c(m[5],ay),ymax:c(m[6],ay),metric}};}
function sweepText(cfg){const ax=axisById(cfg.x),ay=axisById(cfg.y);const m=Object.keys(SWEEP_METRIC).find(k=>SWEEP_METRIC[k]===cfg.metric);
  return nameOfAxis(cfg.x)+' '+fmtStep(cfg.xmin,ax.step)+'..'+fmtStep(cfg.xmax,ax.step)+' × '+nameOfAxis(cfg.y)+' '+fmtStep(cfg.ymin,ay.step)+'..'+fmtStep(cfg.ymax,ay.step)+' → '+m;}

/* ---------- draw all / playback ---------- */
function drawAll(){drawMachine();drawMMF();drawGapMap();drawInduct();drawEnergy();drawSpectra();drawDyn();drawSweep();}
function drawFrame(){drawMachine();drawMMF();drawGapMap();drawInduct();drawEnergy();if(playback==='dyn'){drawDynSpeed();drawDynOrbit();}}
function syncPhi(){if(playback==='dyn'&&SIM){$('phi').value=(tSim/SIM.dur*360).toFixed(1);$('phiOut').textContent='t '+(tSim*1e3).toFixed(1)+' ms';}
  else{$('phi').value=(state.phi*180/Math.PI).toFixed(1);$('phiOut').textContent='φ '+(state.phi*180/Math.PI).toFixed(1)+'°';}}
function setSimTime(t){if(!SIM){DYNV=null;return;}tSim=Math.max(0,Math.min(SIM.dur,t));DYNV=sampleSim(SIM,tSim);state.phi=((DYNV.phi%TAU)+TAU)%TAU;}
function setPlayback(mode){ // 'spin' | 'dyn', the rig's playback
  const dyn=mode==='dyn';playback=dyn?'dyn':'spin';state.dyn.playback=playback;
  if(dyn){if(!SIM&&EV)requestUpdate('full');setSimTime(tSim);}else DYNV=null;syncPhi();drawFrame();}
let playing=false,last=0;
function loop(t){if(!playing)return;const dt=Math.min(0.1,(t-last)/1000);last=t;
  if(playback==='dyn'&&SIM){let tn=tSim+dt*(+state.dyn.timeScale);if(tn>SIM.dur)tn=0;setSimTime(tn);}
  else state.phi=(state.phi+(+state.dyn.spinRate||24)*Math.PI/180*dt)%TAU;
  syncPhi();drawFrame();requestAnimationFrame(loop);}
function setPlaying(p){playing=p;const b=$('play');b.textContent=p?'❚❚':'▶';b.setAttribute('aria-label',p?'Pause':'Play');b.title=p?'Pause the rotor (Panels › Airgap › Play)':'Spin the rotor, or play the run (Panels › Airgap › Play)';if(p){last=performance.now();requestAnimationFrame(loop);}}
function pos(ev,cv){const r=cv.getBoundingClientRect();return {x:ev.clientX-r.left,y:ev.clientY-r.top,w:r.width,h:r.height};}
function copyText(txt,msg){const done=()=>say(msg,'success');
  const fallback=()=>{const ta=document.createElement('textarea');ta.value=txt;ta.style.position='fixed';ta.style.left='-9999px';document.body.append(ta);ta.select();let ok=false;try{ok=document.execCommand('copy');}catch(e){}ta.remove();if(ok)done();else say('the browser refused the copy','error');};
  if(navigator.clipboard&&navigator.clipboard.writeText)navigator.clipboard.writeText(txt).then(done).catch(fallback);else fallback();}

/* ---------- following the text ---------- */
let ownText=null,following=false,lastValues=null;
function markSource(){const el=$('source');if(!el)return;el.textContent=following?'following the editor':'the panel\'s own values';el.classList.toggle('following',following);}
function takeValues(values,{silent}={}){lastValues=values;stateFrom(values,state);activePreset=null;syncPreset();requestUpdate('full');if(!silent)markSource();}
function syncPreset(){const sel=$('preset');if(sel)sel.value=activePreset||'';}
function applyPreset(p){
  const st=presetState(p);st.phi=state.phi;const geometry=assignmentsOf(st);
  if(world.editing&&world.editing()&&world.write(geometry)){ // the text is the truth: the editor's text changes, and the panel follows it
    applyRig(rigOf(st));$('rig').value=rigText(st);activePreset=p.id;syncPreset();say('Airgap: '+p.name+' written into the editor; the rig set','success');return;}
  state=st;activePreset=p.id;syncPreset();$('rig').value=rigText(state);following=false;markSource();requestUpdate('full');}

/* ---------- the panel ---------- */
slot.classList.add('airgap-ui');
slot.innerHTML=`<div class="airgap-head">
  <select class="airgap-preset" data-airgap="preset" aria-label="Preset" title="An arrangement to start from: written into the editor while the airgap part is being edited, else the panel's own"><option value="">— preset —</option>${PRESETS.map(p=>`<option value="${p.id}">${p.name}</option>`).join('')}</select>
  <span class="airgap-source" data-airgap="source"></span>
</div>
<div class="airgap-verbs">
  <button type="button" class="airgap-to-editor" data-airgap="toEditor" title="The panel's values written into the airgap part's text in the SCAD editor (Panels › Airgap › To editor)">To editor</button>
  <button type="button" class="airgap-from-editor" data-airgap="fromEditor" title="The part's text read again: the editor's while the part is edited, its own file otherwise (Panels › Airgap › From editor)">From editor</button>
  <button type="button" class="airgap-copy-scad" data-airgap="copyScad" title="The part's text with the panel's values written in, copied (Panels › Airgap › Copy SCAD)">Copy SCAD</button>
  <button type="button" class="airgap-copy-metrics" data-airgap="copyMetrics" title="The metrics document copied (Panels › Airgap › Copy metrics)">Copy metrics</button>
  <button type="button" class="airgap-reset" data-airgap="reset" title="The panel back on the part's own text, its rig and sweep as they start (Panels › Airgap › Reset)">Reset</button>
</div>
<div class="airgap-stage">
  <div class="stage-head"><span class="ramp" data-airgap="rampField">g₀/g 0 <i></i> 1</span></div>
  <div class="legend" data-airgap="phaseLegend"></div>
  <div class="view"><canvas data-airgap="machine"></canvas></div>
  <div class="scrub">
    <button type="button" class="airgap-play" data-airgap="play" aria-label="Play" title="Spin the rotor, or play the run (Panels › Airgap › Play)">▶</button>
    <input type="range" class="airgap-phi" data-airgap="phi" min="0" max="360" step="0.5" value="0" aria-label="Rotor angle, or the run's time">
    <output data-airgap="phiOut" for="phi">φ 0.0°</output>
  </div>
</div>
<div data-section="metrics"><div class="readouts" data-airgap="readouts"></div>
  <p class="cap">One document, <code>airgap/metrics/1</code>: geometry, windings, the static field and torque, the run. Panels › Airgap › Copy metrics copies it; <code>apothecary airgap metrics validate</code> reads it back.</p></div>
<div data-section="field"><canvas data-airgap="mmf"></canvas>
  <p class="cap">Top: each phase's winding function N(θ), the MMF one ampere in that phase puts across the gap at stator angle θ. Bottom: the signed gap flux density at the rotor angle; grey where the stator has no iron.</p></div>
<div data-section="gap-map"><canvas data-airgap="gapmap"></canvas><div class="hover" data-airgap="gapHover">hover for g at (θ, φ) · click to set φ</div>
  <p class="cap">Stator angle θ across, rotor angle φ up. Rotor features sweep as diagonals, stator features stand as verticals; where they cross the gap closes.</p></div>
<div data-section="inductance"><canvas data-airgap="induct"></canvas>
  <p class="cap">Each phase's self-inductance against rotor angle, and the currents the rig's excitation applies. Torque comes from the rising flank of L.</p></div>
<div data-section="torque"><canvas data-airgap="energy"></canvas><div class="hover" data-airgap="energyHover">hover for W′ and T at φ · click to set φ</div></div>
<div data-section="harmonics"><canvas data-airgap="spectra"></canvas>
  <p class="cap">Ripple at order n needs both surfaces to carry order n. Copper ticks mark the shared orders; the dominant ripple order is labelled.</p></div>
<div data-section="run-up"><canvas data-airgap="dynSpeed"></canvas><div class="hover" data-airgap="dynHover">hover for t · click to scrub the playback</div></div>
<div data-section="orbit"><canvas data-airgap="dynOrbit"></canvas>
  <p class="cap">Left: the rotor centre's path in µm; dashed rings are the bearing clearance and the touchdown radius. Right: stator mode displacements, axial excursion and carrier torsion.</p></div>
<div data-section="vibration"><canvas data-airgap="dynSpec"></canvas></div>
<div data-section="rig">
  <textarea class="airgap-rig" data-airgap="rig" spellcheck="false" aria-label="The rig: excitation, drive, load, bearing, mount, actuation and playback settings, as JSON" title="Excitation, drive, load, bearing, mount, actuation and playback, as one JSON document; a preset sets it"></textarea>
  <div class="msg" data-airgap="rigMsg"></div>
  <p class="cap">The settings the geometry runs under, one document: a value outside its range is clamped and said, an unknown name refused. Excitation: <code>excite</code> auto · sin · dc · uniform, <code>current</code> A, <code>advance</code> ° el. The rest are the drive, bearing, axial, carrier, yoke and playback settings the presets show.</p></div>
<div data-section="sweep">
  <div class="sweep-row"><input type="text" class="airgap-sweep" data-airgap="sweepSpec" spellcheck="false" aria-label="Sweep: x from..to × y from..to → metric" title="Two of the SCAD's names with their ranges, and the metric to map"><button type="button" class="airgap-run" data-airgap="swRun" title="Map the metric over the two ranges (Panels › Airgap › Sweep)">Run</button><span class="msg" data-airgap="swMsg"></span></div>
  <canvas data-airgap="sweep"></canvas><div class="hover" data-airgap="sweepHover">hover a cell · click to load that geometry</div></div>
<p class="cap">The geometry is the airgap part's text: Part › Edit on it, and the panel follows every edit. Panels › Airgap holds the verbs.</p>`;

// Each section's content moves to its window, and the slot keeps the machine.
slot.classList.add('airgap-panel');
for(const part of [...slot.querySelectorAll('[data-section]')]){
  const host=sections[part.dataset.section];
  host.classList.add('airgap-ui','airgap-section');host.append(...part.childNodes);
  part.remove();roots.push(host);}
$('rig').value=rigText(state);$('sweepSpec').value=sweepText(sweepCfg);
// The panel's own controls, each listened to once; the verb buttons are the ring's cells
// (Panels › Airgap), so each does what its cell does.
const toEditorEl=$('toEditor'),fromEditorEl=$('fromEditor'),copyScadEl=$('copyScad'),copyMetricsEl=$('copyMetrics'),resetEl=$('reset');
toEditorEl.addEventListener('click',()=>handle.act('to-editor'));
fromEditorEl.addEventListener('click',()=>handle.act('from-editor'));
copyScadEl.addEventListener('click',()=>handle.act('copy-scad'));
copyMetricsEl.addEventListener('click',()=>handle.act('copy-metrics'));
resetEl.addEventListener('click',()=>handle.act('reset'));
const phiEl=$('phi'),playEl=$('play'),presetEl=$('preset'),rigEl=$('rig'),sweepEl=$('sweepSpec'),runEl=$('swRun');
phiEl.addEventListener('input',()=>scrubTo(+phiEl.value));
playEl.addEventListener('click',()=>setPlaying(!playing));
presetEl.addEventListener('change',()=>choosePreset(presetEl.value));
rigEl.addEventListener('change',()=>rigChanged(rigEl.value));
sweepEl.addEventListener('change',()=>sweepChanged(sweepEl.value));
runEl.addEventListener('click',()=>handle.act('sweep'));
function scrubTo(v){if(playback==='dyn'&&SIM)setSimTime(v/360*SIM.dur);else state.phi=v*Math.PI/180;syncPhi();drawFrame();}
function choosePreset(id){const p=PRESETS.find(q=>q.id===id);if(p)applyPreset(p);}
function rigChanged(text){const {rig,errors}=readRig(text);$('rigMsg').textContent=errors.join(' · ');$('rigMsg').classList.toggle('bad',!rig);if(!rig)return;const excitation=applyRig(rig);rigEl.value=rigText(state);activePreset=null;syncPreset();requestUpdate(excitation?'full':'sim');}
function sweepChanged(text){const r=readSweep(text);$('swMsg').textContent=r.error||'';if(r.cfg){sweepCfg=r.cfg;sweepEl.value=sweepText(sweepCfg);}}
// The pictures: hovered for a reading, clicked to set the rotor angle or the run's time.
const dynSpeedEl=$('dynSpeed'),gapmapEl=$('gapmap'),energyEl=$('energy'),inductEl=$('induct'),sweepMapEl=$('sweep');
const dsT=ev=>{if(!SIM)return null;const p=pos(ev,dynSpeedEl);const u=(p.x-DY.l)/(p.w-DY.l-DY.r);return (u<0||u>1)?null:u*SIM.dur;};
dynSpeedEl.addEventListener('mousemove',ev=>sayRunAt(dsT(ev)));
dynSpeedEl.addEventListener('click',ev=>scrubRunTo(dsT(ev)));
function sayRunAt(t){if(t==null){$('dynHover').textContent='hover for t · click to scrub the playback';return;}const v=sampleSim(SIM,t);$('dynHover').textContent='t '+(t*1e3).toFixed(1)+' ms  ·  '+(v.om*60/TAU).toFixed(0)+' rpm  ·  T '+fmtSI(v.tem,'N·m')+'  ·  r '+(Math.hypot(v.x,v.y)*1e6).toFixed(1)+' µm';}
function scrubRunTo(t){if(t==null)return;if(playback!=='dyn')setPlayback('dyn');setSimTime(t);syncPhi();drawFrame();}
gapmapEl.addEventListener('mousemove',ev=>sayGapAt(ev));
gapmapEl.addEventListener('click',ev=>setPhiFromGap(ev));
function sayGapAt(ev){if(!EV)return;const p=pos(ev,gapmapEl),r=gapAt(p.x,p.y,p.w,p.h);$('gapHover').textContent=r?('θ '+(r.th*180/Math.PI).toFixed(0)+'°  φ '+(r.ph*180/Math.PI).toFixed(0)+'°  ·  g = '+(r.g*state.scale.r0).toFixed(3)+' mm  ·  g₀/g = '+(EV.g0/r.g).toFixed(3)+(r.covered?'':'  ·  no stator here')):'hover for g at (θ, φ) · click to set φ';}
function setPhiFromGap(ev){if(!EV)return;const p=pos(ev,gapmapEl),r=gapAt(p.x,p.y,p.w,p.h);if(r){state.phi=r.ph;syncPhi();drawFrame();}}
const enPhi=(ev)=>{const p=pos(ev,energyEl);const u=(p.x-EN.l)/(p.w-EN.l-EN.r);return (u<0||u>1)?null:u*TAU;};
energyEl.addEventListener('mousemove',ev=>sayEnergyAt(enPhi(ev)));
energyEl.addEventListener('click',ev=>setPhiTo(enPhi(ev)));
function sayEnergyAt(ph){if(!EV)return;if(ph==null){$('energyHover').textContent='hover for W′ and T at φ · click to set φ';return;}const j=Math.round(ph/TAU*NPHI)%NPHI;$('energyHover').textContent='φ '+(ph*180/Math.PI).toFixed(1)+'°  ·  W′ '+fmtSI(EV.W[j],'J')+'  ·  T '+fmtSI(EV.T[j],'N·m');}
function setPhiTo(ph){if(ph!=null){state.phi=ph;syncPhi();drawFrame();}}
inductEl.addEventListener('click',ev=>setPhiFromInductance(ev));
function setPhiFromInductance(ev){const p=pos(ev,inductEl);const u=(p.x-IN.l)/(p.w-IN.l-IN.r);if(u>=0&&u<=1)setPhiTo(u*TAU);}
sweepMapEl.addEventListener('mousemove',ev=>saySweepCell(ev));
sweepMapEl.addEventListener('click',ev=>loadSweepCell(ev));
function saySweepCell(ev){const p=pos(ev,sweepMapEl),c=sweepCell(p.x,p.y,p.w,p.h);$('sweepHover').textContent=c?(SW.ax.label+' = '+fmtStep(SW.xs[c.xi],SW.ax.step)+'  ·  '+SW.ay.label+' = '+fmtStep(SW.ys[c.yi],SW.ay.step)+'  →  '+(c.v===c.v?METRICS[SW.metricId].fmt(c.v):'…')):'hover a cell · click to load that geometry';}
function loadSweepCell(ev){const p=pos(ev,sweepMapEl),c=sweepCell(p.x,p.y,p.w,p.h);if(!c)return;
  const values={[nameOfAxis(SW.ax.id)]:SW.xs[c.xi],[nameOfAxis(SW.ay.id)]:SW.ys[c.yi]};
  if(following&&world.editing()&&world.write(values))return; // the text changes; the panel follows
  setP(state,SW.ax.id,SW.xs[c.xi]);setP(state,SW.ay.id,SW.ys[c.yi]);activePreset=null;syncPreset();following=false;markSource();requestUpdate();}
// A fold opened draws the pictures in it; a resize draws them all again.
const foldsEl=slot;
foldsEl.addEventListener('toggle',()=>requestAnimationFrame(drawAll),true);
let rsz=false;const ro=new ResizeObserver(()=>{if(rsz)return;rsz=true;requestAnimationFrame(()=>{rsz=false;drawAll();});});
for(const id of ['machine','mmf','gapmap','induct','energy','spectra','dynSpeed','dynOrbit','dynSpec','sweep'])ro.observe($(id));

const handle={
  // The part's text as the editor has it now (or its own file): the panel follows it.
  textChanged(text){following=true;takeValues(valuesOfText(text));},
  async load(){try{const text=await world.text();if(text)takeValues(valuesOfText(text));following=!!(world.editing&&world.editing());markSource();}catch(err){say('Airgap: '+(err&&err.message||err),'error');}
    // The verb buttons wear their ring addresses once the ring knows the panel is on screen.
    if(window.apothecaryRing&&window.apothecaryRing.refreshAddresses)window.apothecaryRing.refreshAddresses();},
  // A section's window in front again: its pictures drawn at the size it has now.
  redraw(){requestAnimationFrame(drawAll);},
  metrics(){return METRICS_DOC;},
  values(){return assignmentsOf(state);},
  setValues(values){takeValues(Object.assign({},assignmentsOf(state),values));},
  preset(id){const p=PRESETS.find(q=>q.id===id);if(p)applyPreset(p);return !!p;},
  text(){return ownText;},
  state:()=>state,
  // A verb of Panels › Airgap: what its cell does. A refusal is said and returns false.
  async act(verb){
    if(verb==='play'){setPlaying(!playing);return true;}
    if(verb==='sweep'){const r=readSweep($('sweepSpec').value);if(r.error){say('Airgap: sweep: '+r.error,'error');return false;}sweepCfg=r.cfg;if(world.showSection)world.showSection('sweep');runSweep();return true;}
    if(verb==='to-editor'){const values=assignmentsOf(state);
      if(!(world.editing&&world.editing())){if(!(world.edit&&await world.edit())){say('Airgap: select the airgap part and open Part › Edit first; its text is where the values go','error');return false;}}
      if(world.write(values)){say('Airgap: the panel\'s values written into the editor\'s text','success');following=true;markSource();return true;}
      say('Airgap: the editor is not on the airgap part','error');return false;}
    if(verb==='from-editor'){await handle.load();say(following?'Airgap: following the editor\'s text':'Airgap: read the part\'s own SCAD','success');return true;}
    if(verb==='copy-scad'){try{const text=await world.text();copyText(writeValues(text,assignmentsOf(state)),'Airgap: the SCAD with the panel\'s values copied');return true;}catch(err){say('Airgap: '+(err&&err.message||err),'error');return false;}}
    if(verb==='copy-metrics'){if(!METRICS_DOC){say('Airgap: nothing computed yet','error');return false;}copyText(JSON.stringify(METRICS_DOC,null,2),'Airgap: the metrics document copied');return true;}
    if(verb==='reset'){state=presetState(PRESETS[0]);state.phi=0;activePreset=null;syncPreset();$('rig').value=rigText(state);$('rigMsg').textContent='';sweepCfg={x:'stator.teethN',xmin:3,xmax:24,y:'rotor.ribK',ymin:0,ymax:12,metric:'meanT'};$('sweepSpec').value=sweepText(sweepCfg);SW=null;setPlaying(false);setPlayback('spin');await handle.load();say('Airgap: the panel reset to the part\'s own text','success');return true;}
    return false;},
};
syncPhi();markSource();recompute('full');handle.load();
return handle;
}
