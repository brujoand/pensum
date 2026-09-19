/* Regression cover for the snapping on the number-line question.
 *
 * number-line.js is an IIFE that touches `document` the moment it loads, so it
 * cannot be require()d. Rather than restructure shipped code to suit a test,
 * this pulls the pure functions straight out of the file and runs those. It
 * therefore tests what actually ships, and a rename fails loudly here instead
 * of quietly testing a stale copy. Same approach as writing_trace.test.js.
 *
 * What is covered is the one promise that makes this question safe to score: a
 * marker lands on a tick or it does not land. Snapping is what stops a six-year
 * old being marked wrong for a finger that was three pixels short of the number
 * they meant, so a drift here is a drift in what the item measures.
 *
 * The other half of that promise is checked from Python, in
 * tests/test_number_line_js.py: these functions have to agree with
 * `snap_to_tick` on the server, because the server rejects anything that did
 * not come off a tick and a disagreement would mark a correct drag wrong.
 *
 * Run directly with `node tests/js/number_line_snap.test.js`, or through
 * pytest, which shells out to exactly that.
 */

const fs = require("fs");
const path = require("path");

const SOURCE = path.join(__dirname, "..", "..", "src", "pensum", "web", "static", "number-line.js");
const src = fs.readFileSync(SOURCE, "utf8");

/* --- pulling the real code out ------------------------------------------ */

function grabFunction(name) {
  const start = src.indexOf("function " + name + "(");
  if (start < 0) throw new Error(`number-line.js no longer defines ${name}()`);
  let depth = 0;
  for (let j = src.indexOf("{", start); j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}" && --depth === 0) return src.slice(start, j + 1);
  }
  throw new Error(`unbalanced braces in ${name}()`);
}

const NAMES = ["clampTick", "tickAt", "valueAt", "tickOf", "show"];
const loaded = new Function(
  NAMES.map(grabFunction).join("\n") + "\nreturn {" + NAMES.join(",") + "};"
)();
const { clampTick, tickAt, valueAt, tickOf, show } = loaded;

/* Exported so the Python side can run the real snapping against the server's,
 * without a second copy of the extraction above. */
module.exports = loaded;

/* --- the checks --------------------------------------------------------- */

/* Only when run as a script: requiring this file is how the cross-language
 * check gets at the functions, and it has its own assertions. */
if (require.main !== module) {
  return;
}

let failures = 0;

function check(what, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) {
    failures++;
    console.error(`FAIL ${what}: got ${JSON.stringify(got)}, want ${JSON.stringify(want)}`);
  }
}

/* The geometry the server sends for a 0..50 line: PAD and VIEW - PAD. */
const LEFT = 26;
const RIGHT = 174;
const LAST = 10;

/* Dead on a tick, and either side of the midpoint between two. Halfway is the
 * only place the rounding is interesting: anywhere else and a wrong answer
 * would need the pupil to be most of a tick out. */
check("a pointer on the left end", tickAt(LEFT, LEFT, RIGHT, LAST), 0);
check("a pointer on the right end", tickAt(RIGHT, LEFT, RIGHT, LAST), LAST);
check("a pointer on the seventh tick", tickAt(LEFT + 14.8 * 7, LEFT, RIGHT, LAST), 7);
check("just short of halfway rounds back", tickAt(LEFT + 14.8 * 7.49, LEFT, RIGHT, LAST), 7);
check("just past halfway rounds on", tickAt(LEFT + 14.8 * 7.51, LEFT, RIGHT, LAST), 8);

/* A finger dragged off the end of the line is still an answer, and it is the
 * end tick rather than a number the line does not carry. */
check("dragged off the left", tickAt(-500, LEFT, RIGHT, LAST), 0);
check("dragged off the right", tickAt(9000, LEFT, RIGHT, LAST), LAST);
check("clamping is the same both ways", [clampTick(-3, LAST), clampTick(99, LAST)], [0, LAST]);

/* Values are rebuilt from the index, so ten arrow presses on a 0.1 line reach
 * 1 rather than 0.9999999999999999. */
check("a whole step", valueAt(7, 0, 5), 35);
check("a step that is not exact in binary", valueAt(7, 0, 0.1), 0.7);
check(
  "every tick on a 0.1 line",
  Array.from({ length: 11 }, (_, i) => valueAt(i, 0, 0.1)),
  [0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1]
);

/* Typing is the other road to the same answer, and it must not move the marker
 * while a number is still half typed. */
check("a typed tick", tickOf(35, 0, 5, LAST), 7);
check("a typed number between two ticks", tickOf(34, 0, 5, LAST), -1);
check("a typed number off the line", tickOf(75, 0, 5, LAST), -1);
check("a half-typed 35", tickOf(3, 0, 5, LAST), -1);
check("a typed tick on a decimal line", tickOf(0.7, 0, 0.1, 10), 7);

/* Norwegian decimals are written with a comma, including the one the marker
 * writes back into the box. */
check("a whole number keeps no decimal point", show(35), "35");
check("a decimal is written with a comma", show(3.5), "3,5");

if (failures) {
  console.error(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("number-line.js: all checks passed");
