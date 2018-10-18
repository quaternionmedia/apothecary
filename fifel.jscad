//!OpenSCAD
//the above line lets us generate this in jscad (even though we are using a scad syntax!!)

//lines that begin with '//' in javascript mostly (see first line of this file) don't count as far as the computer is concerned, so it's easy to give instructions humans can read like this.

//the next line sets the word  'holes' as the list of numbers outlined below. These lists get sperated by commas, and the semicolon at the end tells the computer that's the end of that statement. These numbers represent the distance from the head of the fife (the part where you blow air) to the center of each hole ( one for mouth, 7 for fingers)
holes = [20,60,70,90,110,130,150,170,190];

//the next line is another list, but this time of how many degrees around the fife the opening gets rotated
holeRotation = [0,180,0,0,0,0,0,0,30];

//another list about how big the opening
holeRadius = [6,3,3,3,3,3,3,3,3];

//tall the darn thing is
height = 200;

//how wide the diameter of the inside resonating chamber is
bore = 20;

//how thick the walls of the fife are
wall = 4;

//a module in openscad is basically a function. Let's you do a whole bunch of code all at once
module fifel(){

	//difference takes the first shape and subtracts all the next shapes from it
	difference() {

	//union combines all the shapes in it to make one larger shape
		union() {

			//this is the outermost shell of the fife. We add the bore and wall variables. R1 is the radius of the head, and r2 is the foot. R1 is a little bigger partly because we want it to taper for comfort, but also to make it print easier. The height is just the height!
			cylinder(r1=(bore+wall+1)/2, r2=(bore+wall)/2, h = height);

			//this next part puts the lip rest on the first opening. Translate moves us out to the edge of the wall (instead of the center like we were) then we rotate to be in line with the opening
			translate([0,-bore/2 +3,holes[0]]) rotate([90,0,0]) {

				//difference because we want the lip rest to have a hole in it so the air goes in!
				difference() {

					//this is the outer cylinder of the lip rest. This is the size of the opening and an additional amount so that it slopes from the bottom to the top. the scale at the begginning makes the thing all squashed and not super circular
					scale([1.1,2,1]) cylinder(r1=holeRadius[0]+2.5, r2 =holeRadius[0]+2, h = 6);

					//this is then the opening, which slopes the opposite way from the lip rest. this let's the chamber resonate better
					translate([0,0,-1])cylinder(r1 = holeRadius[0], r2=holeRadius[0]-2, h = 7);

				//now we close the difference 3 lines up and we return to the translate
				}

			//now we close the translate 5 lines up and return to the union
			}

		//now we close the union and return to the difference
		}

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
