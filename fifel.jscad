//!OpenSCAD
//the above line lets us generate this in jscad (even though we are using a scad syntax!!)

//lines that begin with '//' in javascript mostly (see first line of this file) don't count as far as the computer is concerned, so it's easy to give instructions humans can read like this.

//the next line sets the word  'holes' as the list of numbers outlined below. These lists get sperated by commas, and the semicolon at the end tells the computer that's the end of that statement. These numbers represent the distance from the head of the fife (the part where you blow air) to the center of each hole ( one for mouth, 7 for fingers)
holes = [30,70,90,110,130,150,170,190,210];

//the next line is another list, but this time of how many degrees around the fife the opening gets rotated
holeRotation = [0,180,0,0,0,0,0,0,30];

//another list about how big the opening
holeRadius = [6,3,3,3,3,3,3,3,3];

//tall the darn thing is
height = 215;

//how wide the diameter of the inside resonating chamber is
bore = 20;

//how thick the walls of the fife are
wall = 4;

//a module in openscad is basically a function. Let's you do a whole bunch of code all at once
module fifel(){

				//difference takes the first shape and subtracts all the next shapes from it
				difference() {

								//this is the outermost shell of the fife. We add the bore and wall variables. R1 is the radius of the head, and r2 is the foot. R1 is a little bigger partly because we want it to taper for comfort, but also to make it print easier. The height is just the height!
								cylinder(r1=(bore+wall+1)/2, r2=(bore+wall)/2, h = height);

								//this is the main part of the fife that isnt there. the main resonating chamber
								translate([0,0,2]) cylinder(r=bore/2, h = height);

								//now we are going to go through and make openings (9 in total). The for part tells the word "i" to go from 0 to 9 each time through the next part of the code
								for ( i = [0:len(holes)-1] ){

										//we now adjust the height of the hole with the translate, then the rotation with rotate, and then the cylinder which is at a defined radius, and high enough so it goes all the way out of the wall.
										translate([0,0,holes[i]]) rotate([90,0,holeRotation[i]]) cylinder(r=holeRadius[i], h=bore);

								//now we close the for and return to the union
								}

				//now we close the difference and return to the fifel
				}

//now we close the fifel module
}

//now we call the fifel module to generate the code
fifel();

//end of fifel!
