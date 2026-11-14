# Roadmap

What apothecary claims is built, in the order to take it. A ticked line is a claim;
what shows it is the journey or the walkthrough pages the line names, and the
[tour](tour.md) takes the lines in this order, asking a person about each. A person's
answers are kept beside this page and never written into it
(`uv run apothecary tour`).

A line names a journey as `journey:<id>` and a page by its link. A line that names
neither is shown by nothing, and the tour says so.

## Starting

- [x] A fresh clone is installed, checked and served, and a person finds their way in. [00](../walkthrough/00-getting-started.md), [10](../walkthrough/10-serving-it.md)

## Designing a part

- [x] A part is a folder the registry reads, with numbers that are its own or fitted to another's. [07](../walkthrough/07-a-part.md), [08](../walkthrough/08-fitting.md), [11](../walkthrough/11-contested-numbers.md)
- [x] A part's numbers are staged, checked and applied in the page. [04](../walkthrough/04-designing-a-part.md)
- [x] A part's SCAD is edited in the page. [06](../walkthrough/06-editing-a-parts-scad.md)
- [x] A part computes itself, and an assembly is navigated by its pieces. [17](../walkthrough/17-a-part-that-computes-itself.md), [09](../walkthrough/09-an-assembly.md)
- [x] A part says whether it is ready to build, where it stands, and what is wrong with it. [12](../walkthrough/12-ready-to-build.md), [13](../walkthrough/13-status-and-progress.md), [14](../walkthrough/14-problems-and-solutions.md)

## Making a thing

- [x] A part is chosen, shaped, sliced, seen and printed on a machine. `journey:make`
- [x] A board is flashed and heard from the page. [05](../walkthrough/05-firmware.md)
- [x] A part goes through the router: its toolpath made, previewed and cut from the card. [19](../walkthrough/19-the-router.md), [20](../walkthrough/20-a-part-through-the-router.md), [21](../walkthrough/21-a-toolpath-previewed.md), [24](../walkthrough/24-a-cut-from-the-card.md)
- [x] The router says what it needs before it moves. [31](../walkthrough/31-what-the-router-needs.md)
- [x] The Stream Deck shows the machines and jogs them. [26](../walkthrough/26-the-stream-deck.md), [27](../walkthrough/27-the-deck-jogging-the-machines.md)
- [x] A procedure is written, and walked through its window. [23](../walkthrough/23-a-procedure.md), [25](../walkthrough/25-a-procedure-through-the-window.md)

## The site and the page

- [x] The working space says what is pinned, heard and quiet. [18](../walkthrough/18-the-working-space.md), [32](../walkthrough/32-a-quiet-board-and-a-router-s-pins.md)
- [x] Windows are kept over a reload. [33](../walkthrough/33-windows-kept-over-a-reload.md)
- [x] apothecary is the irl family's hub, and is depended on. [22](../walkthrough/22-the-irl-hub.md), [16](../walkthrough/16-being-depended-on.md)
- [x] The checks run here before a push. [15](../walkthrough/15-preflight.md)
- [x] The tour puts the page on a stage and keeps a person's word on it. [34](../walkthrough/34-the-tour.md)

## Photographs

- [x] Photographs become pieces a person could print. [01](../walkthrough/01-photographs-into-pieces.md), [03](../walkthrough/03-a-picture-to-a-print.md)
- [x] The bench is seen by a camera looking at it. [02](../walkthrough/02-the-bench-as-it-is.md)
- [x] Pictures become models, in the Models window. [35](../walkthrough/35-the-models-window.md), [36](../walkthrough/36-the-models-window-narrow-and-wide.md)
- [x] A whiteboard becomes a model, round twice, its marks worn in the world. [28](../walkthrough/28-a-whiteboard-to-a-model.md), [29](../walkthrough/29-a-whiteboard-round-twice.md), [30](../walkthrough/30-a-whiteboard-round-twice-through-the-page.md), [37](../walkthrough/37-marks-worn-in-the-world.md), [38](../walkthrough/38-a-whiteboard-s-corners.md)
