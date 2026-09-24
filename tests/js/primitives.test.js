/* Regression cover for the hands-on primitives' page scripts.
 *
 * Each script under static/primitives/ is an IIFE that registers itself with
 * core.js the moment it loads, so it cannot be require()d. As with
 * number_line_snap.test.js, the pure functions are pulled straight out of the
 * shipped files and run here, so this tests what ships and a rename fails
 * loudly instead of quietly testing a stale copy.
 *
 * What is covered is what a primitive decides: how a state is parsed (and that
 * anything malformed is refused), what each button, tap, drop and key does to
 * it, and how it is described. The keyboard path of every primitive is its
 * buttons, whose actions are read off their data attributes by `actionOf`, plus
 * the keys the ten-frame and the array take on the board itself.
 *
 * tests/test_primitives_js.py runs this, and adds the checks that need both
 * languages: the page parses every state the server draws, shows exactly the
 * pieces the server shows, and describes a state in the same words.
 *
 * Run directly with `node tests/js/primitives.test.js`.
 */

const fs = require("fs");
const path = require("path");

const STATIC = path.join(__dirname, "..", "..", "src", "pensum", "web", "static");

function grab(file, names, vars) {
  const src = fs.readFileSync(path.join(STATIC, file), "utf8");
  const parts = (vars || []).map((name) => {
    const match = new RegExp("var " + name + " = [^;]*;").exec(src);
    if (!match) throw new Error(`${file} no longer defines var ${name}`);
    return match[0];
  });
  for (const name of names) {
    const start = src.indexOf("function " + name + "(");
    if (start < 0) throw new Error(`${file} no longer defines ${name}()`);
    let depth = 0;
    let end = -1;
    for (let j = src.indexOf("{", start); j < src.length; j++) {
      if (src[j] === "{") depth++;
      else if (src[j] === "}" && --depth === 0) {
        end = j + 1;
        break;
      }
    }
    if (end < 0) throw new Error(`unbalanced braces in ${name}()`);
    parts.push(src.slice(start, end));
  }
  return new Function("window", parts.join("\n") + "\nreturn {" + names.join(",") + "};");
}

const core = grab("primitives/core.js", ["fill", "joinNumbers", "plural", "count", "actionOf"])({});
const window = { PensumActivity: core };

const counters = grab("primitives/counters.js", [
  "countersParse", "countersTotal", "countersIn", "countersWith", "countersRoom",
  "countersApply", "countersShown", "countersDescribe",
])(window);
const tenFrame = grab("primitives/ten-frame.js", [
  "tenFrameParse", "tenFrameHas", "tenFrameFrame", "tenFrameSet", "tenFrameValid",
  "tenFrameApply", "tenFrameShown", "tenFrameDescribe", "tenFrameStep",
])(window);
const baseTen = grab(
  "primitives/base-ten.js",
  [
    "baseTenParse", "baseTenPlace", "baseTenWith", "baseTenBundle", "baseTenBreak",
    "baseTenAdd", "baseTenApply", "baseTenShown", "baseTenValue", "baseTenDescribe",
  ],
  ["PLACES"]
)(window);
const array = grab("primitives/array.js", [
  "arrayParse", "arrayClamp", "arraySized", "arrayApply", "arrayShown", "arrayDescribe",
  "arrayLineAt", "arrayCellAt", "arrayKey",
])(window);
const balance = grab("primitives/balance.js", [
  "balancePan", "balanceParse", "balanceTake", "balanceBox", "balanceParts", "balanceApply",
  "balanceShown", "balanceSide", "balanceWeighs", "balanceTilt", "balanceDescribe",
])(window);

/* Exported so the Python side can run the real functions against the server,
 * keyed by the item kind the server uses. */
module.exports = {
  core,
  counters: {
    parse: counters.countersParse, apply: counters.countersApply,
    shown: counters.countersShown, describe: counters.countersDescribe,
  },
  ten_frame: {
    parse: tenFrame.tenFrameParse, apply: tenFrame.tenFrameApply,
    shown: tenFrame.tenFrameShown, describe: tenFrame.tenFrameDescribe,
  },
  base_ten: {
    parse: baseTen.baseTenParse, apply: baseTen.baseTenApply,
    shown: baseTen.baseTenShown, describe: baseTen.baseTenDescribe,
  },
  array: {
    parse: array.arrayParse, apply: array.arrayApply,
    shown: array.arrayShown, describe: array.arrayDescribe,
  },
  balance: {
    parse: balance.balanceParse, apply: balance.balanceApply,
    shown: balance.balanceShown, describe: balance.balanceDescribe,
  },
};

if (require.main !== module) {
  return;
}

let failures = 0;

function check(what, got, want) {
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    failures++;
    console.error(`FAIL ${what}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
  }
}

/* A button, as core.js reads it: the action is its data attributes. */
function button(data) {
  return core.actionOf({ dataset: data });
}

/* Press a sequence of actions, the way the buttons would, stopping at one
 * that does nothing. */
function press(spec, state, actions, limits) {
  for (const action of actions) {
    const next = spec(state, action, limits);
    if (next === null) return null;
    state = next;
  }
  return state;
}

/* --- core -------------------------------------------------------------- */

check("fill", core.fill("{a} og {b}", { a: 1, b: 2 }), "1 og 2");
check("fill leaves an unknown name", core.fill("{a} {zzz}", { a: 1 }), "1 {zzz}");
check("join one", core.joinNumbers([4], "og"), "4");
check("join three", core.joinNumbers([5, 4, 3], "og"), "5, 4 og 3");
check("plural one", core.plural({ made: "{count} brikker", made_one: "1 brikke" }, "made", 1), "1 brikke");
check("plural many", core.plural({ made: "{count} brikker", made_one: "1 brikke" }, "made", 3), "3 brikker");
check("count refuses a string", core.count("3", 10), null);
check("count refuses a fraction", core.count(2.5, 10), null);
check("count refuses past max", core.count(11, 10), null);
check("count accepts 0", core.count(0, 10), 0);
check("a button's action", button({ action: "move", from: "supply", to: "loose" }), {
  type: "move", from: "supply", to: "loose",
});
check("a button's step", button({ action: "rows", by: "-1" }), { type: "rows", by: -1 });

/* --- counters ---------------------------------------------------------- */

{
  const L = { capacity: 20, ring: 8, groups: 3 };
  const P = counters.countersParse;
  const A = counters.countersApply;
  check("parse", P('{"loose":12,"groups":[0,0,0]}', L), { loose: 12, groups: [0, 0, 0] });
  check("parse refuses the wrong number of rings", P('{"loose":1,"groups":[0,0]}', L), null);
  check("parse refuses a string count", P('{"loose":"1","groups":[0,0,0]}', L), null);
  check("parse refuses a full ring past its room", P('{"loose":0,"groups":[9,0,0]}', L), null);
  check("parse refuses nonsense", P("{", L), null);

  let s = { loose: 12, groups: [0, 0, 0] };
  s = A(s, button({ action: "add", zone: "g0" }), L);
  check("a ring's button moves one from the mat", s, { loose: 11, groups: [1, 0, 0] });
  check("take one back", A(s, button({ action: "move", from: "g0", to: "loose" }), L), {
    loose: 12, groups: [0, 0, 0],
  });
  check("the mat's add button draws from the box", A(s, button({ action: "move", from: "supply", to: "loose" }), L), {
    loose: 12, groups: [1, 0, 0],
  });
  check("dragging to the box takes one away", A(s, { type: "move", from: "loose", to: "supply" }, L), {
    loose: 10, groups: [1, 0, 0],
  });
  check("an empty ring gives nothing back", A(s, { type: "move", from: "g2", to: "loose" }, L), null);
  check("a zone that is not there", A(s, { type: "move", from: "loose", to: "g7" }, L), null);
  check("a tap on the mat adds from the box", A({ loose: 0, groups: [0, 0, 0] }, { type: "add", zone: "loose", index: -1 }, L), {
    loose: 1, groups: [0, 0, 0],
  });
  check("tapping the box twice adds", A({ loose: 0, groups: [0, 0, 0] }, { type: "act", zone: "supply", index: 0 }, L), {
    loose: 1, groups: [0, 0, 0],
  });
  check("the board is full", A({ loose: 20, groups: [0, 0, 0] }, { type: "move", from: "supply", to: "loose" }, L), null);
  check("a full ring refuses one more", A({ loose: 4, groups: [8, 0, 0] }, { type: "add", zone: "g0" }, L), null);

  const shared = press(A, { loose: 12, groups: [0, 0, 0] },
    [0, 1, 2, 0, 1, 2, 0, 1, 2, 0, 1, 2].map((g) => button({ action: "add", zone: "g" + g })), L);
  check("sharing twelve out by the buttons", shared, { loose: 0, groups: [4, 4, 4] });
  check("shown: the fourth counter in a ring of four", counters.countersShown(shared, { zone: "g1", index: 3 }), true);
  check("shown: no fifth", counters.countersShown(shared, { zone: "g1", index: 4 }), false);

  const say = { made: "{count} brikker", made_one: "1 brikke", made_groups: "{count} brikker, fordelt {sizes}", made_loose: "{loose} utenfor gruppene", and: "og" };
  check("describe groups", counters.countersDescribe({ loose: 1, groups: [5, 4, 3] }, say), "13 brikker, fordelt 5, 4 og 3, 1 utenfor gruppene");
  check("describe one", counters.countersDescribe({ loose: 1, groups: [] }, say), "1 brikke");
}

/* --- ten_frame --------------------------------------------------------- */

{
  const L = { frames: 2, cells: 10, perRow: 5 };
  const P = tenFrame.tenFrameParse;
  const A = tenFrame.tenFrameApply;
  check("parse sorts", P('{"frames":[[3,1],[]]}', L), { frames: [[1, 3], []] });
  check("parse refuses a repeated cell", P('{"frames":[[1,1],[]]}', L), null);
  check("parse refuses cell 10", P('{"frames":[[10],[]]}', L), null);
  check("parse refuses the wrong number of frames", P('{"frames":[[1]]}', L), null);

  const empty = { frames: [[], []] };
  const thirteen = press(A, empty, Array(13).fill(button({ action: "add" })), L);
  check("the add button fills in reading order, first frame first", thirteen, {
    frames: [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [0, 1, 2]],
  });
  check("the remove button takes the last", A(thirteen, button({ action: "remove" }), L), {
    frames: [[0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [0, 1]],
  });
  check("the remove button on an empty frame", A(empty, button({ action: "remove" }), L), null);
  check("a tap on an empty cell", A(empty, { type: "add", zone: "f1", index: 7 }, L), { frames: [[], [7]] });
  check("a tap on a filled cell adds nothing", A({ frames: [[], [7]] }, { type: "add", zone: "f1", index: 7 }, L), null);
  check("tapping a dot twice takes it away", A({ frames: [[4], []] }, { type: "act", zone: "f0", index: 4 }, L), empty);
  check("a drag to an empty cell", A({ frames: [[4], []] }, { type: "move", from: "f0", fromIndex: 4, to: "f1", toIndex: 0 }, L), {
    frames: [[], [0]],
  });
  check("a drag onto a dot", A({ frames: [[4, 5], []] }, { type: "move", from: "f0", fromIndex: 4, to: "f0", toIndex: 5 }, L), null);
  check("a drag off the frame", A({ frames: [[4], []] }, { type: "move", from: "f0", fromIndex: 4, to: "f2", toIndex: 0 }, L), null);

  /* The keyboard: a cursor over the cells, Space toggles. */
  const step = tenFrame.tenFrameStep;
  check("right", step(4, "ArrowRight", 2, 5), 5);
  check("down a row", step(3, "ArrowDown", 2, 5), 8);
  check("down into the second frame", step(7, "ArrowDown", 2, 5), 12);
  check("up past the top stays", step(2, "ArrowUp", 2, 5), 0);
  check("end", step(0, "End", 2, 5), 19);
  check("one frame ends at 9", step(8, "ArrowDown", 1, 5), 9);
  check("a letter does not move it", step(3, "a", 2, 5), -1);
  const on = A(empty, { type: "toggle", zone: "f1", index: 2 }, L);
  check("space puts a dot down", on, { frames: [[], [2]] });
  check("space again takes it away", A(on, { type: "toggle", zone: "f1", index: 2 }, L), empty);

  check("describe", tenFrame.tenFrameDescribe(thirteen, { made: "{count} prikker", made_one: "1 prikk" }), "13 prikker");
}

/* --- base_ten ---------------------------------------------------------- */

{
  const L = { hundreds: 0, tens: 20, ones: 20 };
  const LF = { hundreds: 9, tens: 20, ones: 20 };
  const P = baseTen.baseTenParse;
  const A = baseTen.baseTenApply;
  const zero = { hundreds: 0, tens: 0, ones: 0 };
  check("parse fills a missing place with 0", P('{"tens":3,"ones":4}', L), { hundreds: 0, tens: 3, ones: 4 });
  check("parse refuses hundreds without flats", P('{"hundreds":1,"tens":0,"ones":0}', L), null);
  check("parse refuses 21 ones", P('{"tens":0,"ones":21}', L), null);
  check("parse refuses 3.5", P('{"tens":3.5,"ones":0}', L), null);

  const built = press(A, zero, [
    ...Array(3).fill(button({ action: "move", from: "supply-tens", to: "tens" })),
    ...Array(4).fill(button({ action: "move", from: "supply-ones", to: "ones" })),
  ], L);
  check("34 by the buttons", built, { hundreds: 0, tens: 3, ones: 4 });
  check("take a one away", A(built, button({ action: "move", from: "ones", to: "supply-ones" }), L), {
    hundreds: 0, tens: 3, ones: 3,
  });
  check("bundle needs ten ones", A(built, button({ action: "bundle", zone: "ones" }), L), null);
  const broken = A(built, button({ action: "break", zone: "tens" }), L);
  check("break a ten", broken, { hundreds: 0, tens: 2, ones: 14 });
  check("bundle them back", A(broken, button({ action: "bundle", zone: "ones" }), L), built);
  check("tapping a rod twice breaks it", A(built, { type: "act", zone: "tens", index: 0 }, L), broken);
  check("tapping a unit twice bundles ten", A(broken, { type: "act", zone: "ones", index: 0 }, L), built);
  check("a rod dropped on the ones breaks", A(built, { type: "move", from: "tens", to: "ones" }, L), broken);
  check("ones dropped on the tens bundle", A(broken, { type: "move", from: "ones", to: "tens" }, L), built);
  check("a unit from the tray goes to the ones wherever it lands", A(zero, { type: "move", from: "supply-ones", to: "tens" }, L), {
    hundreds: 0, tens: 0, ones: 1,
  });
  check("a tap on a column adds one there", A(zero, { type: "add", zone: "tens", index: -1 }, L), {
    hundreds: 0, tens: 1, ones: 0,
  });
  check("no room to break", A({ hundreds: 0, tens: 1, ones: 15 }, button({ action: "break", zone: "tens" }), L), null);
  check("no hundreds without flats", A(zero, { type: "move", from: "supply-hundreds", to: "hundreds" }, L), null);
  check("a hundred with flats", A(zero, { type: "move", from: "supply-hundreds", to: "hundreds" }, LF), {
    hundreds: 1, tens: 0, ones: 0,
  });
  check("break a hundred", A({ hundreds: 1, tens: 0, ones: 0 }, button({ action: "break", zone: "hundreds" }), LF), {
    hundreds: 0, tens: 10, ones: 0,
  });
  check("shown: the fourth unit of four", baseTen.baseTenShown(built, { zone: "ones", index: 3 }), true);
  check("shown: no fifth", baseTen.baseTenShown(built, { zone: "ones", index: 4 }), false);

  const say = {
    made: "{value} ({parts})", tens_count: "{count} tiere", tens_count_one: "1 tier",
    ones_count: "{count} enere", ones_count_one: "1 ener", and: "og",
  };
  check("describe", baseTen.baseTenDescribe(broken, say, L), "34 (2 tiere og 14 enere)");
  check("describe one", baseTen.baseTenDescribe({ hundreds: 0, tens: 1, ones: 1 }, say, L), "11 (1 tier og 1 ener)");
}

/* --- array ------------------------------------------------------------- */

{
  const L = { max: 10, cell: 18, left: 16, top: 26, split: true };
  const P = array.arrayParse;
  const A = array.arrayApply;
  check("parse", P('{"rows":3,"cols":7,"split":5}', L), { rows: 3, cols: 7, split: 5 });
  check("parse refuses a split outside", P('{"rows":3,"cols":5,"split":5}', L), null);
  check("parse refuses zero rows", P('{"rows":0,"cols":5}', L), null);
  check("parse refuses eleven", P('{"rows":11,"cols":5}', L), null);

  /* The keyboard: arrows on the handle, Shift for the split line. */
  const one = { rows: 1, cols: 1, split: 0 };
  const keys = ["ArrowDown", "ArrowDown", ...Array(6).fill("ArrowRight")];
  let s = one;
  for (const key of keys) s = A(s, array.arrayKey(s, key, false), L);
  check("3 × 7 by the arrow keys", s, { rows: 3, cols: 7, split: 0 });
  for (let i = 0; i < 5; i++) s = A(s, array.arrayKey(s, "ArrowRight", true), L);
  check("shift-right five times puts the line after 5", s, { rows: 3, cols: 7, split: 5 });
  check("the line cannot pass the last column", A({ rows: 3, cols: 7, split: 6 }, { type: "split", by: 1 }, L), null);
  check("shrinking past the line drops it", A({ rows: 3, cols: 6, split: 5 }, { type: "cols", by: -1 }, L), {
    rows: 3, cols: 5, split: 0,
  });
  check("up past one row", A(one, array.arrayKey(one, "ArrowUp", false), L), null);
  check("no split on an array that does not ask for one", A(s, { type: "split", by: -1 }, { ...L, split: false }), null);
  check("the buttons", A(one, button({ action: "cols", by: "1" }), L), { rows: 1, cols: 2, split: 0 });
  check("a resize clamps", A(one, { type: "resize", rows: 40, cols: -3 }, L), { rows: 10, cols: 1, split: 0 });

  /* Pointer to grid: a drag snaps the corner to the nearest line; a tap
   * takes the corner to the far side of the square tapped. */
  check("a corner halfway between lines 3 and 4 rounds", array.arrayLineAt(16 + 18 * 3.4, 16, 18, 10), 3);
  check("a corner past the end stays on the grid", array.arrayLineAt(9999, 16, 18, 10), 10);
  check("a corner before the start is one", array.arrayLineAt(-50, 16, 18, 10), 1);
  check("a tap inside the third square", array.arrayCellAt(16 + 18 * 2.1, 16, 18, 10), 3);

  check("shown inside", array.arrayShown({ rows: 3, cols: 7 }, { row: 2, col: 6 }), true);
  check("shown outside", array.arrayShown({ rows: 3, cols: 7 }, { row: 3, col: 0 }), false);
  const say = { made: "{rows} rader med {cols} i hver", made_one: "1 rad med {cols}", made_split: "delt i {left} og {right}" };
  check("describe", array.arrayDescribe({ rows: 3, cols: 7, split: 5 }, say), "3 rader med 7 i hver, delt i 5 og 2");
  check("describe one row", array.arrayDescribe({ rows: 1, cols: 4, split: 0 }, say), "1 rad med 4");
}

/* --- balance ----------------------------------------------------------- */

{
  const closed = { open: false, maxBox: 20, pivot: [150, 128], tilt: 6, drop: 10 };
  const open = { ...closed, open: true };
  const P = balance.balanceParse;
  const A = balance.balanceApply;
  const start = { left: { boxes: 3, weights: 2 }, right: { boxes: 1, weights: 10 }, box: 0 };
  check("parse", P(JSON.stringify(start), closed), start);
  check("parse refuses a box of 21", P('{"left":{"boxes":1,"weights":0},"right":{"boxes":0,"weights":0},"box":21}', closed), null);
  check("parse refuses a pan that is not one", P('{"left":1,"right":{},"box":0}', closed), null);

  let s = press(A, start, [
    button({ action: "take", zone: "boxes" }),
    button({ action: "take", zone: "weights" }),
    button({ action: "take", zone: "weights" }),
  ], closed);
  check("take the same from both sides by the buttons", s, {
    left: { boxes: 2, weights: 0 }, right: { boxes: 0, weights: 8 }, box: 0,
  });
  check("no box left on the right to take", A(s, button({ action: "take", zone: "boxes" }), closed), null);
  check("no weight left on the left to take", A(s, button({ action: "take", zone: "weights" }), closed), null);
  s = press(A, s, Array(4).fill(button({ action: "box", by: "1" })), closed);
  check("the stepper", s.box, 4);
  check("the stepper stops at 0", A({ ...start, box: 0 }, button({ action: "box", by: "-1" }), closed), null);
  check("a weight dragged to take-away", A(start, { type: "move", from: "left-w", to: "away" }, closed), {
    left: { boxes: 3, weights: 1 }, right: { boxes: 1, weights: 9 }, box: 0,
  });
  check("a box tapped, then the other pan", A(start, { type: "move", from: "right-b", to: "left" }, closed), {
    left: { boxes: 2, weights: 2 }, right: { boxes: 0, weights: 10 }, box: 0,
  });
  check("moving within one pan does nothing", A(start, { type: "move", from: "left-w", to: "left" }, closed), null);
  check("an open box cannot be taken from", A(start, button({ action: "take", zone: "weights" }), open), null);

  const early = { left: { boxes: 0, weights: 7 }, right: { boxes: 1, weights: 5 }, box: 0 };
  check("a spare weight dropped on the box fills it", A(early, { type: "move", from: "supply", to: "right-b" }, open).box, 1);
  check("a weight taken out of the box", A({ ...early, box: 2 }, { type: "move", from: "right-b", to: "supply" }, open).box, 1);
  check("a tap on the box adds one", A(early, { type: "add", zone: "right-b", index: 0 }, open).box, 1);

  check("tilts left while the box is light", balance.balanceTilt(early, true), -1);
  check("level at 2", balance.balanceTilt({ ...early, box: 2 }, true), 0);
  check("tilts right when the box is heavy", balance.balanceTilt({ ...early, box: 3 }, true), 1);
  check("a closed box never tilts", balance.balanceTilt(early, false), 0);
  check("the equation", balance.balanceDescribe(start, { status: "{equation}, ☐ = {box}" }), "☐ + ☐ + ☐ + 2 = ☐ + 10, ☐ = 0");
  check("an empty side is 0", balance.balanceSide({ boxes: 0, weights: 0 }), "0");
  check("shown: a box still on the pan", balance.balanceShown(s, { zone: "left-b", index: 1 }), true);
  check("shown: a box taken", balance.balanceShown(s, { zone: "left-b", index: 2 }), false);
}

if (failures) {
  console.error(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("primitives: all checks passed");
