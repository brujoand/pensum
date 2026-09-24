/* The reading screen's weekly rhythm, and the move away from a daily streak.
 *
 * Two things are defended. The count must never punish a missed day: reading
 * on Monday and Wednesday is two, not a streak broken on Tuesday. And a pupil
 * with an old streak in their browser must not see this week's readings vanish
 * the day the new code ships.
 *
 * reading.js is an IIFE that touches `document` on load, so, like the other
 * harnesses here, this pulls the pure functions straight out of the shipped
 * file and runs those.
 *
 * Run directly with `node tests/js/reading_week.test.js`, or through pytest.
 */

const fs = require("fs");
const path = require("path");

const SOURCE = path.join(__dirname, "..", "..", "src", "pensum", "web", "static", "reading.js");
const src = fs.readFileSync(SOURCE, "utf8");

function grabFunction(name) {
  const start = src.indexOf("function " + name + "(");
  if (start < 0) throw new Error(`reading.js no longer defines ${name}()`);
  let depth = 0;
  for (let j = src.indexOf("{", start); j < src.length; j++) {
    if (src[j] === "{") depth++;
    else if (src[j] === "}" && --depth === 0) return src.slice(start, j + 1);
  }
  throw new Error(`unbalanced braces in ${name}()`);
}

const { dayKey, isoWeekKey, recordWeek } = new Function(
  [
    grabFunction("dayKey"),
    grabFunction("isoWeekKey"),
    grabFunction("recordWeek"),
    "return { dayKey, isoWeekKey, recordWeek };",
  ].join("\n")
)();

let failures = 0;

function check(what, condition) {
  if (condition) return;
  failures++;
  console.error(`FAIL: ${what}`);
}

/* Local dates, as the page uses them. Month is 1-based here for readability. */
function on(y, m, d) {
  return new Date(y, m - 1, d, 12, 0, 0);
}

/* --- ISO weeks ----------------------------------------------------------- */

check("a Thursday is in its own ISO week", isoWeekKey(on(2026, 9, 24)) === "2026-W39");
check("Monday starts the week", isoWeekKey(on(2026, 9, 21)) === "2026-W39");
check("Sunday ends it", isoWeekKey(on(2026, 9, 27)) === "2026-W39");
check("the next Monday is a new week", isoWeekKey(on(2026, 9, 28)) === "2026-W40");
/* 1 January 2027 is a Friday, so it belongs to the last week of 2026. */
check("New Year's Day can belong to the old year", isoWeekKey(on(2027, 1, 1)) === "2026-W53");
/* 29 December 2025 is a Monday in the week holding 1 January 2026, a Thursday. */
check("late December can belong to the new year", isoWeekKey(on(2025, 12, 29)) === "2026-W01");
check("days are zero-padded", dayKey(on(2026, 3, 5)) === "2026-03-05");

/* --- counting days ------------------------------------------------------- */

{
  const state = {};
  check("the first reading is one day", recordWeek(state, on(2026, 9, 21)) === 1);
  check("a second reading the same day is still one", recordWeek(state, on(2026, 9, 21)) === 1);
  /* Tuesday skipped. A streak would say 1 here; the week says 2. */
  check("a missed day resets nothing", recordWeek(state, on(2026, 9, 23)) === 2);
  check("a third day is three", recordWeek(state, on(2026, 9, 27)) === 3);
  check("the new week starts from its own readings", recordWeek(state, on(2026, 9, 29)) === 1);
  check("and forgets the old week's days", state.week.days.length === 1);
}

{
  const state = { week: { id: "2026-W39", days: "not a list" } };
  check("a damaged week is started fresh", recordWeek(state, on(2026, 9, 24)) === 1);
}

/* --- migrating an old streak --------------------------------------------- */

{
  /* The old format: unpadded, and "days in a row ending on `last`". Monday to
   * Thursday of this week, plus Sunday of the last. */
  const state = { streak: { days: 5, last: "2026-9-24" }, texts: { a: { best: 90, runs: 2 } } };
  const count = recordWeek(state, on(2026, 9, 24));
  check("this week's streak days are carried over", count === 4);
  check("last week's streak days are not", state.week.days[0] === "2026-09-21");
  check("the old streak is removed", !("streak" in state));
  check("personal bests are untouched", state.texts.a.best === 90);
}

{
  const state = { streak: { days: 12, last: "2026-9-10" } };
  check("a streak from an earlier week carries nothing", recordWeek(state, on(2026, 9, 24)) === 1);
  check("and is still removed", !("streak" in state));
}

{
  const state = { streak: { days: "lots", last: "yesterday" } };
  check("a garbage streak is dropped, not trusted", recordWeek(state, on(2026, 9, 24)) === 1);
  check("and removed", !("streak" in state));
}

{
  const state = { streak: { days: 0, last: null } };
  check("the old empty default migrates to today", recordWeek(state, on(2026, 9, 24)) === 1);
}

/* --- the shipped page no longer says "in a row" -------------------------- */

check("reading.js no longer reads the streak label", src.indexOf("labelStreak") < 0);

if (failures) {
  console.error(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("reading.js weekly rhythm: all checks passed");
