// Calibration Cube - Test shape with axis indicators and dimension markers
// Use this to verify printer calibration and understand coordinate system
//
// Face layout:
//   +X (right):  "X" label
//   -X (left):   dimension value
//   +Y (back):   "Y" label  
//   -Y (front):  dimension value
//   +Z (top):    "Z" label + notch
//   -Z (bottom): flat (print surface)
//
// Parameters:
//   size - Cube dimension (default: 20mm)
//   show_axes - Include XYZ axis indicators for preview only (default: true)
//   show_dimensions - Include dimension markers (default: true)
//   wall_thickness - Shell thickness (default: 2mm)

// Customizer parameters
size = 10;              // [10:1:50] Cube size in mm
show_axes = true;       // Show axis indicators (preview only, not in STL)
show_dimensions = true; // Show dimension markers
wall_thickness = 2;     // [1:0.5:5] Wall thickness

/* [Hidden] */
$fn = 32;
axis_length = size * 0.8;
axis_radius = size * 0.03;
arrow_size = size * 0.1;
font_size = size * 0.15;
label_font_size = size * 0.25;
marker_depth = 0.8;
notch_size = size * 0.15;

// Main calibration cube
module calibration_cube() {
    difference() {
        // Outer cube
        cube([size, size, size]);
        
        // Hollow interior (optional for faster printing)
        if (wall_thickness < size/2) {
            translate([wall_thickness, wall_thickness, wall_thickness])
            cube([size - 2*wall_thickness, size - 2*wall_thickness, size - 2*wall_thickness]);
        }
        
        // Dimension markers - on -X (left) and -Y (front) faces
        if (show_dimensions) {
            // Dimension on -Y face (front, facing you)
            translate([size/2, marker_depth, size/2])
            rotate([90, 0, 0])
            linear_extrude(marker_depth + 0.01)
            text(str(size), size=font_size, halign="center", valign="center");
            
            // Dimension on -X face (left side)
            translate([marker_depth, size/2, size/2])
            rotate([90, 0, -90])
            linear_extrude(marker_depth + 0.01)
            text(str(size), size=font_size, halign="center", valign="center");
        }
        
        // Axis labels - on +X, +Y, +Z faces (opposite from dimensions)
        // X label on +X face (right side)
        translate([size - marker_depth, size/2, size/2])
        rotate([90, 0, 90])
        linear_extrude(marker_depth + 0.01)
        text("X", size=label_font_size, halign="center", valign="center", font="Liberation Sans:style=Bold");
        
        // Y label on +Y face (back side)
        translate([size/2, size - marker_depth, size/2])
        rotate([90, 0, 0])
        linear_extrude(marker_depth + 0.01)
        text("Y", size=label_font_size, halign="center", valign="center", font="Liberation Sans:style=Bold");
        
        // Z label on +Z face (top) - offset from center for notch
        translate([size * 0.65, size * 0.65, size])
        linear_extrude(marker_depth + 0.01, center=true)
        text("Z", size=label_font_size, halign="center", valign="center", font="Liberation Sans:style=Bold");
        
        // Corner notch on TOP at origin corner (0,0,size)
        translate([-0.01, -0.01, size - notch_size + 0.01])
        cube([notch_size, notch_size, notch_size + 0.01]);
    }
}

// Axis indicator arrow (preview only)
module axis_arrow(length, color_name) {
    color(color_name) {
        // Shaft
        cylinder(h=length - arrow_size, r=axis_radius);
        // Arrow head
        translate([0, 0, length - arrow_size])
        cylinder(h=arrow_size, r1=arrow_size/2, r2=0);
    }
}

// XYZ axes at origin (preview only - uses % for ghost rendering)
module axes() {
    // X axis - Red
    rotate([0, 90, 0])
    axis_arrow(axis_length, "red");
    
    // Y axis - Green
    rotate([-90, 0, 0])
    axis_arrow(axis_length, "green");
    
    // Z axis - Blue
    axis_arrow(axis_length, "blue");
}

// Origin marker (corner sphere, preview only)
module origin_marker() {
    color("white")
    sphere(r=axis_radius * 2);
}

// Render the printable cube
color("gray", 0.8)
calibration_cube();

// Axes are preview-only (% modifier makes them not render to STL)
if (show_axes) {
    % origin_marker();
    % axes();
}
