; hand-written ZEIM test fixture (not slicer output)
G21
G90
M83
G28 ; home
G10 ; firmware retract: must NOT be read as G1
G11
G1 Z0.2 F600
;LAYER_CHANGE
;Z:0.2
;TYPE:Skirt/Brim
G1 X0 Y0 F3000
G1 X10 Y0 E0.5
;TYPE:External perimeter
G1 X10 Y10 E0.5
;TYPE:Perimeter
G1 X0 Y10 E0.5
;TYPE:Internal infill
G1 X0 Y0 E0.5
G1 Z0.6 ; z-hop
G0 X5 Y5
G1 Z0.2
;TYPE:Solid infill
G1 X6 Y5 E0.1
G1 E-0.8 ; retract (no move)
G1 Z0.4
G1 E0.8 ; unretract (no move)
;LAYER_CHANGE
;Z:0.4
;TYPE:Support material
G1 X6 Y6 E0.2
;TYPE:External perimeter
G2 X16 Y6 I5 J0 E1.0 ; half circle clockwise, radius 5
G3 X6 Y6 R5 E1.0 ; half circle back, R form
M82
G92 E0
G1 Z0.6
G1 X7 Y6 E0.3
G1 X8 Y6 E0.2 ; absolute E went DOWN: retract, travel only
G91
G1 X1 Y0 E0.1 ; relative move + relative E
G90
M83
N12 G1 X20 Y20 E0.5*77
; estimated printing time (normal mode) = 1m 2s
; filament used [mm] = 12.34
; filament used [g] = 0.04
