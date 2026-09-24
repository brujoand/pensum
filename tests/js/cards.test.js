/* Regression cover for the card primitives' page scripts: sort, sequence,
 * match, label and highlight.
 *
 * Pulled straight out of the shipped files, as primitives.test.js does for the
 * number boards, so this tests what ships and a rename fails loudly. Covered:
 * how a state is parsed (and that anything malformed is refused), what a drag,
 * a tap-tap, a button and a menu each do to it, and how it is described.
 *
 * tests/test_cards_js.py runs this, and adds the checks that need both
 * languages: the page parses every state the server draws, shows exactly the
 * cards the server shows, and describes a state in the same words.
 *
 * Run directly with `node tests/js/cards.test.js`.
 */

const fs = require("fs");
const path = require("path");

const STATIC = path.join(__dirname, "..", "..", "src", "pensum", "web", "static");

function grab(file, names) {
  const src = fs.readFileSync(path.join(STATIC, file), "utf8");
  const parts = [];
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

const sort = grab("primitives/sort.js", [
  "sortParse", "sortRegion", "sortApply", "sortShown", "sortDescribe",
])(window);
const sequence = grab("primitives/sequence.js", [
  "sequenceParse", "sequenceAt", "sequenceApply", "sequenceShown", "sequenceDescribe",
])(window);
const match = grab("primitives/match.js", [
  "matchParse", "matchRow", "matchLink", "matchApply", "matchShown", "matchDescribe",
])(window);
const label = grab("primitives/label.js", [
  "labelParse", "labelSlot", "labelPut", "labelApply", "labelShown", "labelDescribe",
])(window);
const highlight = grab("primitives/highlight.js", [
  "highlightParse", "highlightApply", "highlightShown", "highlightDescribe",
])(window);

module.exports = {
  core,
  sort: {
    parse: sort.sortParse, apply: sort.sortApply,
    shown: sort.sortShown, describe: sort.sortDescribe,
  },
  sequence: {
    parse: sequence.sequenceParse, apply: sequence.sequenceApply,
    shown: sequence.sequenceShown, describe: sequence.sequenceDescribe,
  },
  match: {
    parse: match.matchParse, apply: match.matchApply,
    shown: match.matchShown, describe: match.matchDescribe,
  },
  label: {
    parse: label.labelParse, apply: label.labelApply,
    shown: label.labelShown, describe: label.labelDescribe,
  },
  highlight: {
    parse: highlight.highlightParse, apply: highlight.highlightApply,
    shown: highlight.highlightShown, describe: highlight.highlightDescribe,
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

/* A button or a card, as core.js reads it: the action is its data attributes. */
function button(data) {
  return core.actionOf({ dataset: data });
}

/* A drag or a tap-tap, as core.js dispatches it. */
function move(from, fromIndex, to, toIndex) {
  return { type: "move", from, fromIndex, to, toIndex: toIndex === undefined ? -1 : toIndex };
}

const MALFORMED = [
  "", "{", "null", "3", "[]", '"x"', "{}",
  '{"place": 1}', '{"order": "0123"}', '{"pairs": {}}', '{"slots": null}', '{"marked": [0.5]}',
];

/* --- core -------------------------------------------------------------- */

check("a button's index is read as a number", button({ action: "place", index: "3" }), {
  type: "place", index: 3,
});
check("join words", core.joinNumbers(["kork", "blad", "pinne"], "og"), "kork, blad og pinne");

/* --- sort -------------------------------------------------------------- */
{
  const L = { cards: 4, regions: 2 };
  const start = sort.sortParse('{"place":[-1,-1,-1,-1]}', L);
  check("sort parses its opening", start, { place: [-1, -1, -1, -1] });
  for (const bad of [...MALFORMED, '{"place":[0,1,0]}', '{"place":[0,1,0,2]}', '{"place":[0,1,0,-2]}',
    '{"place":[0,1,0,"1"]}', '{"place":[0,1,0,1.5]}']) {
    check(`sort refuses ${bad}`, sort.sortParse(bad, L), null);
  }

  let s = sort.sortApply(start, move("tray", 0, "r0"), L);
  check("a drag puts a card in a bin", s, { place: [0, -1, -1, -1] });
  s = sort.sortApply(s, move("r0", 0, "r1"), L);
  check("and moves it to another", s, { place: [1, -1, -1, -1] });
  check("dropping in the bin it is in does nothing", sort.sortApply(s, move("r1", 0, "r1"), L), null);
  check("a bin that is not there is refused", sort.sortApply(s, move("r1", 0, "r2"), L), null);
  check("a card that is not there is refused", sort.sortApply(s, move("tray", 7, "r0"), L), null);
  s = sort.sortApply(s, { type: "place", index: 0, zone: "tray" }, L);
  check("the menu takes it back out", s, { place: [-1, -1, -1, -1] });
  check("the menu's own action", sort.sortApply(start, { type: "place", index: 2, zone: "r1" }, L), {
    place: [-1, -1, 1, -1],
  });
  check("anything else does nothing", sort.sortApply(start, { type: "add", zone: "r0" }, L), null);

  const on = { place: [0, 1, -1, 0] };
  check("a card shows only in its own place", [
    sort.sortShown(on, { zone: "r0", index: 0 }, L),
    sort.sortShown(on, { zone: "r1", index: 0 }, L),
    sort.sortShown(on, { zone: "tray", index: 2 }, L),
    sort.sortShown(on, { zone: "tray", index: 1 }, L),
    sort.sortShown(on, { zone: "r9", index: 1 }, L),
  ], [true, false, true, false, false]);

  const say = {
    and: "og", none: "ingen", tray: "Ikke plassert ennå",
    titles: ["Flyter", "Synker"], cards: ["kork", "stein", "blad", "spiker"],
  };
  check("sort describes every bin, then what is left", sort.sortDescribe(on, say),
    "Flyter: kork og spiker; Synker: stein; Ikke plassert ennå: blad");
  check("an empty bin says so", sort.sortDescribe({ place: [0, 0, 0, 0] }, say),
    "Flyter: kork, stein, blad og spiker; Synker: ingen");
}

/* --- sequence ---------------------------------------------------------- */
{
  const L = { cards: 4 };
  const start = sequence.sequenceParse('{"order":[2,0,3,1]}', L);
  check("sequence parses an order", start, { order: [2, 0, 3, 1] });
  for (const bad of [...MALFORMED, '{"order":[0,1,2]}', '{"order":[0,0,1,2]}', '{"order":[0,1,2,4]}',
    '{"order":[0,1,2,-1]}']) {
    check(`sequence refuses ${bad}`, sequence.sequenceParse(bad, L), null);
  }

  check("up swaps with the card above", sequence.sequenceApply(start, button({ action: "up", zone: "p1" }), L),
    { order: [0, 2, 3, 1] });
  check("down swaps with the card below",
    sequence.sequenceApply(start, button({ action: "down", zone: "p1" }), L), { order: [2, 3, 0, 1] });
  check("the first card cannot go up", sequence.sequenceApply(start, button({ action: "up", zone: "p0" }), L), null);
  check("the last card cannot go down",
    sequence.sequenceApply(start, button({ action: "down", zone: "p3" }), L), null);
  check("a drag takes a card out and puts it in", sequence.sequenceApply(start, move("p0", 2, "p3"), L),
    { order: [0, 3, 1, 2] });
  check("and back up", sequence.sequenceApply(start, move("p3", 1, "p0", 2), L), { order: [1, 2, 0, 3] });
  check("to its own place does nothing", sequence.sequenceApply(start, move("p2", 3, "p2"), L), null);
  check("off the line does nothing", sequence.sequenceApply(start, move("p2", 3, "p9"), L), null);

  /* Pressed the way a keyboard user would: the buttons alone reach the answer. */
  let s = start;
  for (const [action, zone] of [["up", "p1"], ["up", "p3"], ["up", "p2"]]) {
    s = sequence.sequenceApply(s, { type: action, zone }, L);
  }
  check("the buttons alone put it in order", s, { order: [0, 1, 2, 3] });

  check("a card shows only at its place", [
    sequence.sequenceShown(start, { zone: "p0", index: 2 }, L),
    sequence.sequenceShown(start, { zone: "p0", index: 0 }, L),
  ], [true, false]);
  check("sequence describes the line", sequence.sequenceDescribe(start, { cards: ["a", "b", "c", "d"] }),
    "c → a → d → b");
}

/* --- match ------------------------------------------------------------- */
{
  const L = { cards: 3 };
  const start = match.matchParse('{"pairs":[-1,-1,-1]}', L);
  check("match parses its opening", start, { pairs: [-1, -1, -1] });
  for (const bad of [...MALFORMED, '{"pairs":[0,0,1]}', '{"pairs":[0,1]}', '{"pairs":[0,1,3]}',
    '{"pairs":[0,1,-2]}']) {
    check(`match refuses ${bad}`, match.matchParse(bad, L), null);
  }

  check("a card, then a row", match.matchApply(start, move("supply", 2, "l0"), L), { pairs: [2, -1, -1] });
  check("a card, then a term", match.matchApply(start, move("supply", 2, "supply-left", 1), L),
    { pairs: [-1, 2, -1] });
  check("a term, then a card", match.matchApply(start, move("supply-left", 0, "supply", 1), L),
    { pairs: [1, -1, -1] });
  const linked = { pairs: [1, -1, -1] };
  check("linking a card elsewhere moves it", match.matchApply(linked, move("supply", 1, "l2"), L),
    { pairs: [-1, -1, 1] });
  check("a linked card dragged to another row", match.matchApply(linked, move("l0", 1, "l1"), L),
    { pairs: [-1, 1, -1] });
  check("a linked card dropped on the column is unlinked", match.matchApply(linked, move("l0", 1, "supply"), L),
    { pairs: [-1, -1, -1] });
  check("a term, then a card linked in another row", match.matchApply(linked, move("supply-left", 2, "l0", 1), L),
    { pairs: [-1, -1, 1] });
  check("a term, then an empty row, does nothing", match.matchApply(linked, move("supply-left", 2, "l1"), L), null);
  check("the same pair again does nothing", match.matchApply(linked, move("supply", 1, "l0"), L), null);
  check("the menu links", match.matchApply(start, { type: "pair", row: 1, card: 0 }, L), { pairs: [-1, 0, -1] });
  check("and unlinks", match.matchApply(linked, { type: "pair", row: 0, card: -1 }, L), { pairs: [-1, -1, -1] });
  check("a row that is not there", match.matchApply(start, { type: "pair", row: 5, card: 0 }, L), null);

  check("a card shows beside its term only", [
    match.matchShown(linked, { zone: "l0", index: 1 }, L),
    match.matchShown(linked, { zone: "l1", index: 1 }, L),
  ], [true, false]);
  check("match describes the pairs", match.matchDescribe(linked, {
    none: "ingen", left: ["A", "B", "C"], right: ["x", "y", "z"],
  }), "A – y; B – ingen; C – ingen");
}

/* --- label ------------------------------------------------------------- */
{
  const L = { cards: 3 };
  const start = label.labelParse('{"slots":[-1,-1,-1]}', L);
  check("label parses its opening", start, { slots: [-1, -1, -1] });
  for (const bad of [...MALFORMED, '{"slots":[1,1,-1]}', '{"slots":[0,1]}', '{"slots":[0,1,3]}']) {
    check(`label refuses ${bad}`, label.labelParse(bad, L), null);
  }
  let s = label.labelApply(start, move("tray", 2, "s0"), L);
  check("a label from the tray onto a place", s, { slots: [2, -1, -1] });
  s = label.labelApply(s, move("tray", 1, "s0", 2), L);
  check("onto a place already labelled sends the old one back", s, { slots: [1, -1, -1] });
  check("the tray shows what is not placed", [0, 1, 2].map((j) => label.labelShown(s, { zone: "tray", index: j }, L)),
    [true, false, true]);
  s = label.labelApply(s, move("s0", 1, "s2"), L);
  check("from one place to another", s, { slots: [-1, -1, 1] });
  s = label.labelApply(s, move("s2", 1, "tray"), L);
  check("back to the tray", s, { slots: [-1, -1, -1] });
  check("a label that is not where it says", label.labelApply(start, move("s1", 0, "s2"), L), null);
  check("the menu places", label.labelApply(start, { type: "place", slot: 1, card: 0 }, L), { slots: [-1, 0, -1] });
  check("label describes by number", label.labelDescribe({ slots: [2, -1, 0] }, {
    none: "ingen", labels: ["nord", "øst", "sør"],
  }), "1: sør; 2: ingen; 3: nord");
}

/* --- highlight --------------------------------------------------------- */
{
  const L = { tokens: 6 };
  const start = highlight.highlightParse('{"marked":[]}', L);
  check("highlight parses its opening", start, { marked: [] });
  for (const bad of [...MALFORMED, '{"marked":[3,1]}', '{"marked":[1,1]}', '{"marked":[6]}',
    '{"marked":[-1]}']) {
    check(`highlight refuses ${bad}`, highlight.highlightParse(bad, L), null);
  }
  let s = highlight.highlightApply(start, { type: "toggle", index: 4 }, L);
  s = highlight.highlightApply(s, { type: "toggle", index: 1 }, L);
  check("tapping marks, kept in order", s, { marked: [1, 4] });
  check("tapping again unmarks", highlight.highlightApply(s, { type: "toggle", index: 4 }, L), { marked: [1] });
  check("a word that is not there", highlight.highlightApply(s, { type: "toggle", index: 6 }, L), null);
  check("anything but a toggle", highlight.highlightApply(s, { type: "move" }, L), null);
  check("the ring shows on a marked word only", [
    highlight.highlightShown(s, { zone: "mark", index: 1 }),
    highlight.highlightShown(s, { zone: "mark", index: 2 }),
  ], [true, false]);
  const say = { and: "og", nothing: "ingenting", tokens: ["Katten", "hopper", "opp", "og", "spiser", "fisken"] };
  check("highlight names the marked words", highlight.highlightDescribe(s, say), "«hopper» og «spiser»");
  check("and says when nothing is", highlight.highlightDescribe(start, say), "ingenting");
}

if (failures) {
  console.error(`${failures} failure(s)`);
  process.exit(1);
}
console.log("cards: all checks passed");
