/* Regression cover for the language primitives' page scripts: sound boxes, the
 * sound slide, word and sentence frames, and dialogue.
 *
 * The same approach as primitives.test.js: the pure functions are pulled out
 * of the shipped files and run here, so this tests what ships. Covered is what
 * each primitive decides -- how a state is parsed (anything malformed refused),
 * what each button, tap, drop and double tap does, and how a state is said --
 * plus the shared tile moves and the voice choice that core.js adds for them.
 *
 * tests/test_language_primitives_js.py runs this, and checks the page against
 * the server for every committed item: the page parses every state the server
 * writes, shows exactly the pieces the server draws, says a state in the same
 * words, and a board built with the buttons is graded right.
 *
 * Run directly with `node tests/js/language_primitives.test.js`.
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
  const exported = names.concat(vars || []);
  return new Function("window", parts.join("\n") + "\nreturn {" + exported.join(",") + "};");
}

const core = grab(
  "primitives/core.js",
  ["fill", "plural", "count", "actionOf", "slotOf", "tilesParse", "tilesApply", "tilesShown", "speechPick"],
  ["EMPTY", "SPEECH_LANGS"]
)({});
const window = {
  PensumActivity: {
    fill: core.fill,
    plural: core.plural,
    count: core.count,
    tiles: {
      EMPTY: core.EMPTY,
      slotOf: core.slotOf,
      parse: core.tilesParse,
      apply: core.tilesApply,
      shown: core.tilesShown,
    },
  },
};

const soundBoxes = grab("primitives/sound-boxes.js", [
  "soundBoxesParse", "soundBoxesApply", "soundBoxesShown", "soundBoxesDescribe",
])(window);
const blend = grab("primitives/blend.js", ["blendParse", "blendApply", "blendShown", "blendDescribe"])(window);
const wordBuild = grab("primitives/word-build.js", [
  "wordBuildParse", "wordBuildApply", "wordBuildShown", "wordBuildWord", "wordBuildDescribe",
])(window);
const sentenceBuild = grab("primitives/sentence-build.js", [
  "sentenceBuildTurn", "sentenceBuildFlippable", "sentenceBuildParse", "sentenceBuildToggle",
  "sentenceBuildApply", "sentenceBuildShown", "sentenceBuildWords", "sentenceBuildText",
  "sentenceBuildDescribe",
])(window);
const dialogue = grab("primitives/dialogue.js", [
  "dialogueAt", "dialogueParse", "dialogueApply", "dialogueShown", "dialogueDescribe",
  "dialogueLines",
])(window);

module.exports = {
  core,
  sound_boxes: {
    parse: soundBoxes.soundBoxesParse, apply: soundBoxes.soundBoxesApply,
    shown: soundBoxes.soundBoxesShown, describe: soundBoxes.soundBoxesDescribe,
  },
  blend: {
    parse: blend.blendParse, apply: blend.blendApply,
    shown: blend.blendShown, describe: blend.blendDescribe,
  },
  word_build: {
    parse: wordBuild.wordBuildParse, apply: wordBuild.wordBuildApply,
    shown: wordBuild.wordBuildShown, describe: wordBuild.wordBuildDescribe,
  },
  sentence_build: {
    parse: sentenceBuild.sentenceBuildParse, apply: sentenceBuild.sentenceBuildApply,
    shown: sentenceBuild.sentenceBuildShown, describe: sentenceBuild.sentenceBuildDescribe,
  },
  dialogue: {
    parse: dialogue.dialogueParse, apply: dialogue.dialogueApply,
    shown: dialogue.dialogueShown, describe: dialogue.dialogueDescribe,
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

function button(data) {
  return core.actionOf({ dataset: data });
}

function press(apply, state, actions, limits) {
  for (const action of actions) {
    const next = apply(state, action, limits);
    if (next === null) return null;
    state = next;
  }
  return state;
}

/* --- the shared tile moves --------------------------------------------- */

{
  const E = core.EMPTY;
  const A = core.tilesApply;
  check("parse", core.tilesParse([0, E, 2], 3, 3), [0, E, 2]);
  check("parse refuses a tile twice", core.tilesParse([0, 0, E], 3, 3), null);
  check("parse refuses the wrong length", core.tilesParse([0, E], 3, 3), null);
  check("parse refuses a tile that is not there", core.tilesParse([5, E, E], 3, 3), null);
  check("parse refuses a fraction", core.tilesParse([0.5, E, E], 3, 3), null);
  check("parse refuses a string", core.tilesParse(["0", E, E], 3, 3), null);
  check("slot names", [core.slotOf("s3"), core.slotOf("tray"), core.slotOf("s")], [3, -1, -1]);

  const empty = [E, E, E];
  check("a tile's button fills the first free place", A([E, 1, E], button({ action: "place", zone: "2" }), 3, 3), [2, 1, E]);
  check("a placed tile's button does nothing", A([2, E, E], button({ action: "place", zone: "2" }), 3, 3), null);
  check("a full frame takes no more", A([0, 1, 2], button({ action: "place", zone: "0" }), 4, 3), null);
  check("take back the last one", A([0, E, 2], button({ action: "unplace" }), 3, 3), [0, E, E]);
  check("nothing to take back", A(empty, button({ action: "unplace" }), 3, 3), null);
  check("a double tap in the tray places", A(empty, { type: "act", zone: "tray", index: 1 }, 3, 3), [1, E, E]);
  check("dragged from the tray to a place", A(empty, { type: "move", from: "tray", fromIndex: 2, to: "s1", toIndex: 1 }, 3, 3), [E, 2, E]);
  check("dropped on a full place replaces it", A([E, 0, E], { type: "move", from: "tray", fromIndex: 2, to: "s1" }, 3, 3), [E, 2, E]);
  check("two places swap", A([0, E, 1], { type: "move", from: "s0", fromIndex: 0, to: "s2" }, 3, 3), [1, E, 0]);
  check("back to the tray", A([0, E, 1], { type: "move", from: "s2", fromIndex: 1, to: "tray" }, 3, 3), [0, E, E]);
  check("a place past `usable` is refused", A(empty, { type: "move", from: "tray", fromIndex: 0, to: "s2" }, 3, 2), null);
  check("a tap on an empty place alone does nothing", A(empty, { type: "add", zone: "s0", index: 0 }, 3, 3), null);
  check("shown in its place", core.tilesShown([E, 2, E], { zone: "s1", index: 2 }), true);
  check("not shown in another", core.tilesShown([E, 2, E], { zone: "s0", index: 2 }), false);
  check("gone from the tray", core.tilesShown([E, 2, E], { zone: "tray", index: 2 }), false);
  check("still in the tray", core.tilesShown([E, 2, E], { zone: "tray", index: 0 }), true);
}

/* --- the voice ------------------------------------------------------------ */

{
  const nbLocal = { lang: "nb-NO", localService: true, name: "a" };
  const nbRemote = { lang: "nb-NO", localService: false, name: "b" };
  const no = { lang: "no_NO", localService: true, name: "c" };
  const en = { lang: "en-GB", localService: true, name: "d" };
  check("a local voice beats a remote one", core.speechPick([nbRemote, nbLocal], "nb").name, "a");
  check("no-NO is a Norwegian voice", core.speechPick([en, no], "nb").name, "c");
  check("an English voice is not a Norwegian one", core.speechPick([en], "nb"), null);
  check("English", core.speechPick([nbLocal, en], "en").name, "d");
  check("no voices at all", core.speechPick([], "en"), null);
}

/* --- sound_boxes --------------------------------------------------------------- */

{
  const E = -1;
  const L = { capacity: 5, tiles: ["h", "m", "s", "u"], letters: true, language: "nb", word: "hus" };
  const P = soundBoxes.soundBoxesParse;
  const A = soundBoxes.soundBoxesApply;
  const start = { counters: 0, slots: [E, E, E, E, E] };
  check("parse", P(JSON.stringify(start), L), start);
  check("parse refuses a letter with no counter", P('{"counters":0,"slots":[0,-1,-1,-1,-1]}', L), null);
  check("parse refuses too many counters", P('{"counters":6,"slots":[-1,-1,-1,-1,-1]}', L), null);

  let s = press(A, start, Array(3).fill(button({ action: "move", from: "supply", to: "counters" })), L);
  check("three counters by the button", s.counters, 3);
  check("a tap on a box adds one", A(start, { type: "add", zone: "s4", index: 4 }, L).counters, 1);
  check("a letter goes on a counter", A(s, button({ action: "place", zone: "0" }), L).slots, [0, E, E, E, E]);
  check("not past the counters", A(s, { type: "move", from: "tray", fromIndex: 1, to: "s3" }, L), null);
  s = press(A, s, [0, 3, 2].map((t) => button({ action: "place", zone: String(t) })), L);
  check("h-u-s by the buttons", s.slots, [0, 3, 2, E, E]);
  check("taking the last counter sends its letter back", A(s, { type: "move", from: "counters", fromIndex: 2, to: "supply" }, L), {
    counters: 2, slots: [0, 3, E, E, E],
  });
  check("no letters on a board without them", A(start, button({ action: "place", zone: "0" }), { ...L, letters: false, tiles: [] }), null);
  check("the box is full", A({ counters: 5, slots: [E, E, E, E, E] }, button({ action: "move", from: "supply", to: "counters" }), L), null);
  check("shown: the third counter", soundBoxes.soundBoxesShown(s, { zone: "counters", index: 2 }), true);
  check("shown: no fourth", soundBoxes.soundBoxesShown(s, { zone: "counters", index: 3 }), false);
  const say = { made: "{count} lyder", made_one: "1 lyd" };
  check("describe", soundBoxes.soundBoxesDescribe(s, say, L), "3 lyder: h-u-s");
  check("describe a gap", soundBoxes.soundBoxesDescribe({ counters: 2, slots: [0, E, E, E, E] }, say, L), "2 lyder: h-_");
  check("describe one", soundBoxes.soundBoxesDescribe({ counters: 1, slots: [E, E, E, E, E] }, say, { ...L, letters: false }), "1 lyd");
}

/* --- blend ---------------------------------------------------------------------- */

{
  const L = { count: 3, choices: ["a", "b", "c"], language: "en", sounds: ["shh", "ih", "puh"], word: "ship" };
  const P = blend.blendParse;
  const A = blend.blendApply;
  check("parse", P('{"joined":0,"pick":""}', L), { joined: 0, pick: "" });
  check("parse refuses a pick before the slide is full", P('{"joined":2,"pick":"a"}', L), null);
  check("parse refuses an unknown pick", P('{"joined":3,"pick":"z"}', L), null);

  let s = { joined: 0, pick: "" };
  check("a pick waits for the slide", A(s, button({ action: "pick", zone: "a" }), L), null);
  check("the first tile first", A(s, { type: "move", from: "apart", fromIndex: 1, to: "joined" }, L), null);
  s = A(s, { type: "move", from: "apart", fromIndex: 0, to: "joined" }, L);
  check("dragged on", s, { joined: 1, pick: "" });
  s = A(s, { type: "act", zone: "apart", index: 1 }, L);
  check("a double tap on the next tile joins it", s.joined, 2);
  s = A(s, button({ action: "join" }), L);
  check("the button joins the last", s.joined, 3);
  check("nothing more to join", A(s, button({ action: "join" }), L), null);
  s = A(s, button({ action: "pick", zone: "b" }), L);
  check("picked", s.pick, "b");
  check("picking it again takes it back", A(s, button({ action: "pick", zone: "b" }), L).pick, "");
  check("sliding one out clears the pick", A(s, button({ action: "split" }), L), { joined: 2, pick: "" });
  check("shown: the picked card", blend.blendShown(s, { zone: "pick", index: 1 }, L), true);
  check("shown: tiles on the slide", blend.blendShown(s, { zone: "joined", index: 2 }, L), true);
  check("shown: none left apart", blend.blendShown(s, { zone: "apart", index: 2 }, L), false);
  const say = { made: "«{choice}»", none: "ingenting ennå", choice_b: "en sau" };
  check("describe", blend.blendDescribe(s, say), "«en sau»");
  check("describe none", blend.blendDescribe({ joined: 3, pick: "" }, say), "ingenting ennå");
}

/* --- word_build ------------------------------------------------------------------- */

{
  const E = -1;
  const L = { slots: 2, tiles: ["ball", "fot", "hånd"] };
  const A = wordBuild.wordBuildApply;
  let s = wordBuild.wordBuildParse('{"slots":[-1,-1]}', L);
  check("parse", s, { slots: [E, E] });
  check("parse refuses a long frame", wordBuild.wordBuildParse('{"slots":[-1,-1,-1]}', L), null);
  s = press(A, s, [button({ action: "place", zone: "1" }), button({ action: "place", zone: "0" })], L);
  check("fot + ball by the buttons", s.slots, [1, 0]);
  check("a double tap in the frame sends it back", A(s, { type: "act", zone: "s0", index: 1 }, L).slots, [E, 0]);
  const say = { made: "«{word}»", empty: "ingenting i rammen ennå" };
  check("describe", wordBuild.wordBuildDescribe(s, say, L), "«fotball»");
  check("describe a gap closed up", wordBuild.wordBuildDescribe({ slots: [E, 2] }, say, L), "«hånd»");
  check("describe empty", wordBuild.wordBuildDescribe({ slots: [E, E] }, say, L), "ingenting i rammen ennå");
}

/* --- sentence_build ---------------------------------------------------------------- */

{
  const E = -1;
  const L = { slots: 4, tiles: [".", "?", "bor", "du", "hvor"], marks: [",", ".", ":", ";", "?", "!"] };
  const A = sentenceBuild.sentenceBuildApply;
  const P = sentenceBuild.sentenceBuildParse;
  check("parse", P('{"slots":[-1,-1,-1,-1],"flipped":[]}', L), { slots: [E, E, E, E], flipped: [] });
  check("parse refuses a flipped mark", P('{"slots":[0,-1,-1,-1],"flipped":[0]}', L), null);
  check("parse refuses a flip of a tile in the tray", P('{"slots":[2,-1,-1,-1],"flipped":[4]}', L), null);
  check("parse refuses an unsorted flip list", P('{"slots":[2,4,-1,-1],"flipped":[4,2]}', L), null);

  let s = { slots: [E, E, E, E], flipped: [] };
  s = press(A, s, [4, 2, 3, 1].map((t) => button({ action: "place", zone: String(t) })), L);
  check("hvor bor du ? by the buttons", s.slots, [4, 2, 3, 1]);
  const say = { made: "«{sentence}»", empty: "tom" };
  check("describe before the flip", sentenceBuild.sentenceBuildDescribe(s, say, L), "«hvor bor du?»");
  s = A(s, button({ action: "flip" }), L);
  check("the flip button turns the first word", s.flipped, [4]);
  check("even when it is not in the first place", A({ slots: [E, 4, 2, E], flipped: [] }, button({ action: "flip" }), L).flipped, [4]);
  check("an empty frame has nothing to flip", A({ slots: [E, E, E, E], flipped: [] }, button({ action: "flip" }), L), null);
  check("describe after", sentenceBuild.sentenceBuildDescribe(s, say, L), "«Hvor bor du?»");
  check("a double tap turns it back", A(s, { type: "act", zone: "s0", index: 4 }, L).flipped, []);
  check("a mark does not turn", A(s, { type: "act", zone: "s3", index: 1 }, L), null);
  check("back to the tray loses the turn", A(s, { type: "move", from: "s0", fromIndex: 4, to: "tray" }, L), {
    slots: [E, 2, 3, 1], flipped: [],
  });
  check("the turn goes with the tile", A(s, { type: "move", from: "s0", fromIndex: 4, to: "s2" }, L), {
    slots: [3, 2, 4, 1], flipped: [4],
  });
  check("shown: the turned tile", sentenceBuild.sentenceBuildShown(s, { zone: "s0", index: 4, row: 1 }), true);
  check("hidden: its plain twin", sentenceBuild.sentenceBuildShown(s, { zone: "s0", index: 4, row: 0 }), false);
  check("turn I", sentenceBuild.sentenceBuildTurn("I"), "i");
  check("a mark is not flippable", sentenceBuild.sentenceBuildFlippable("?"), false);
}

/* --- dialogue ---------------------------------------------------------------------- */

{
  const L = { start: "order", language: "en", max: 40, nodes: { order: ["pay", null], pay: ["bye", null, "bye"], bye: [] } };
  const A = dialogue.dialogueApply;
  const P = dialogue.dialogueParse;
  check("parse", P('{"picks":[1,0]}', L), { picks: [1, 0] });
  check("parse refuses a pick after the end", P('{"picks":[0,0,0]}', L), null);
  check("parse refuses a pick that is not offered", P('{"picks":[2]}', L), null);
  check("parse refuses a string", P('{"picks":["0"]}', L), null);

  let s = { picks: [] };
  check("a line from another node", A(s, button({ action: "pick", zone: "pay", by: "0" }), L), null);
  s = A(s, button({ action: "pick", zone: "order", by: "1" }), L);
  check("a wrong line is kept and the conversation stays", [s.picks, dialogue.dialogueAt(s.picks, L)], [[1], "order"]);
  s = press(A, s, [button({ action: "pick", zone: "order", by: "0" }), button({ action: "pick", zone: "pay", by: "2" })], L);
  check("to the end", dialogue.dialogueAt(s.picks, L), "bye");
  check("nothing after the end", A(s, button({ action: "pick", zone: "bye", by: "0" }), L), null);
  const say = { made: "{count} picks, finished", made_one: "1 pick, finished", open: "{count} picks, open", open_one: "1 pick, open" };
  check("describe finished", dialogue.dialogueDescribe(s, say, L), "3 picks, finished");
  check("describe open", dialogue.dialogueDescribe({ picks: [1] }, say, L), "1 pick, open");
  const script = {
    partner: "Waiter", you: "You",
    nodes: {
      order: { says: "Hi", options: ["Juice, please", "Juice."], replies: [null, "Nicely?"] },
      pay: { says: "Here", options: ["Thanks", "Hm", "Ta"], replies: [null, "?", null] },
      bye: { says: "Bye", options: [], replies: [] },
    },
  };
  check("the log", dialogue.dialogueLines({ picks: [1, 0] }, L, script), [
    ["Waiter", "Hi"], ["You", "Juice."], ["Waiter", "Nicely?"], ["You", "Juice, please"], ["Waiter", "Here"],
  ]);
  check("no pieces", dialogue.dialogueShown(), false);
}

if (failures) {
  console.error(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("language primitives: all checks passed");
