/* Regression cover for the simulations' page scripts: trials, step code and
 * explore_sim.
 *
 * The same approach as primitives.test.js: the pure functions are pulled out
 * of the shipped files and run here, so this tests what ships. Covered is what
 * each primitive decides -- how a state is parsed (anything malformed or out
 * of order refused), what each button does, how a state is said -- plus the
 * seeded draws, the program executor and the Python-like text.
 *
 * tests/test_simulation_primitives_js.py runs this, and checks the page
 * against the server for every committed item: the page parses every state
 * the server writes, shows exactly the pieces the server draws, says a state
 * in the same words, replays the same draws, runs programs to the same poses,
 * writes the same text, and a board built with the buttons is graded right.
 *
 * Run directly with `node tests/js/simulation_primitives.test.js`.
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

const core = grab("primitives/core.js", ["fill", "plural", "count", "actionOf"])({});
const window = { PensumActivity: { fill: core.fill, plural: core.plural, count: core.count } };

const trials = grab("primitives/trials.js", [
  "trialsNext", "trialsSimulate", "trialsParse", "trialsApply", "trialsLevel", "trialsShown",
  "trialsJoin", "trialsDescribe", "trialsSealed",
])(window);
const stepCode = grab(
  "primitives/step-code.js",
  [
    "stepCodeBody", "stepCodeCount", "stepCodeAllowed", "stepCodeListAt", "stepCodeValidCursor",
    "stepCodeParse", "stepCodePath", "stepCodeApply", "stepCodeBlocked", "stepCodeTrace",
    "stepCodePoseIndex", "stepCodeShown", "stepCodeHead", "stepCodeWords", "stepCodeDescribe",
    "stepCodeText", "stepCodeLines",
  ],
  ["DX", "DY", "SIMPLE"]
)(window);
const exploreSim = grab("primitives/explore-sim.js", [
  "exploreSimParse", "exploreSimWith", "exploreSimApply", "exploreSimShown", "exploreSimDescribe",
  "exploreSimSealed",
])(window);

module.exports = {
  core,
  trials: {
    parse: trials.trialsParse, apply: trials.trialsApply, shown: trials.trialsShown,
    describe: trials.trialsDescribe, simulate: trials.trialsSimulate, sealed: trials.trialsSealed,
  },
  step_code: {
    parse: stepCode.stepCodeParse, apply: stepCode.stepCodeApply, shown: stepCode.stepCodeShown,
    describe: stepCode.stepCodeDescribe, trace: stepCode.stepCodeTrace, text: stepCode.stepCodeText,
  },
  explore_sim: {
    parse: exploreSim.exploreSimParse, apply: exploreSim.exploreSimApply,
    shown: exploreSim.exploreSimShown, describe: exploreSim.exploreSimDescribe,
    sealed: exploreSim.exploreSimSealed,
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

/* --- trials -------------------------------------------------------------- */

{
  const L = { weights: [2, 1, 1], dice: 0, outcomes: 3, choices: ["sol", "sky", "regn", "equal"], max: 1000, levels: 20 };
  const P = trials.trialsParse;
  const A = trials.trialsApply;
  const blank = '{"prediction":null,"seed":7,"done":0,"tally":[0,0,0]}';
  check("parse the opening", P(blank, L), { prediction: null, seed: 7, done: 0, tally: [0, 0, 0] });
  check("a run needs a prediction", A(P(blank, L), button({ action: "run", by: "10" }), L), null);
  let s = A(P(blank, L), button({ action: "predict", zone: "sky" }), L);
  s = A(s, button({ action: "predict", zone: "sol" }), L);
  check("the prediction can change before any run", s.prediction, "sol");
  check("not sealed yet", trials.trialsSealed(s), false);
  s = A(s, button({ action: "run", by: "10" }), L);
  check("ten trials", [s.done, s.tally.reduce((a, b) => a + b, 0)], [10, 10]);
  check("sealed after the first run", trials.trialsSealed(s), true);
  check("locked", A(s, button({ action: "predict", zone: "sky" }), L), null);
  check("only 1, 10 or 100 at a time", A(s, { type: "run", by: 5 }, L), null);
  const again = trials.trialsSimulate(7, 10, L);
  check("the draws are the seed's", s.tally, again);
  check("the same seed draws the same", trials.trialsSimulate(7, 110, L), trials.trialsSimulate(7, 110, L));
  check("another seed draws differently", JSON.stringify(trials.trialsSimulate(8, 100, L)) !== JSON.stringify(trials.trialsSimulate(7, 100, L)), true);
  const tampered = JSON.stringify({ prediction: "sol", seed: 7, done: 10, tally: [10, 0, 0] });
  check("a tally the seed did not draw is refused", P(tampered, L), null);
  check("a run without a prediction is refused", P('{"prediction":null,"seed":7,"done":1,"tally":' + JSON.stringify(trials.trialsSimulate(7, 1, L)) + "}", L), null);
  check("a choice that is not offered", P('{"prediction":"storm","seed":7,"done":0,"tally":[0,0,0]}', L), null);
  check("a seed of 0", P('{"prediction":null,"seed":0,"done":0,"tally":[0,0,0]}', L), null);
  check("a string", P('"a"', L), null);
  check("past the most", P(JSON.stringify({ prediction: "sol", seed: 7, done: 1001, tally: trials.trialsSimulate(7, 1001, L) }), L), null);
  let big = s;
  for (let i = 0; i < 9; i++) big = A(big, { type: "run", by: 100 }, L);
  check("up to the most", big.done, 910);
  check("not past it", A(big, { type: "run", by: 100 }, L), null);
  check("the bar level rounds to twentieths", [trials.trialsLevel(1, 2, 20), trials.trialsLevel(0, 0, 20), trials.trialsLevel(1, 40, 20)], [10, 0, 1]);
  const D = { weights: [], dice: 2, outcomes: 11, choices: [], max: 1000, levels: 20 };
  const sums = trials.trialsSimulate(3, 1000, D);
  check("two dice give totals 2 to 12", sums.length, 11);
  check("and seven is the commonest", sums.indexOf(Math.max.apply(null, sums)), 5);
  const say = {
    none: "no prediction yet", made: "“{choice}”", count: "{label}: {count}", and: "and",
    after: "after {count} spins: {tally}", after_one: "after 1 spin: {tally}",
    labels: ["Sun", "Cloud", "Rain"], choices: { sol: "Sun", sky: "Cloud", regn: "Rain", equal: "Equal" },
  };
  check("describe nothing", trials.trialsDescribe({ prediction: null, done: 0, tally: [0, 0, 0] }, say), "no prediction yet");
  check("describe a run", trials.trialsDescribe({ prediction: "sol", done: 1, tally: [1, 0, 0] }, say), "“Sun”, after 1 spin: Sun: 1, Cloud: 0 and Rain: 0");
}

/* --- step code ------------------------------------------------------------- */

{
  const L = {
    width: 4, height: 3, start: [0, 2, 1], goal: [3, 0], walls: [[1, 1]],
    tiles: ["step", "left", "right", "repeat", "if_wall"], repeats: [2, 3], max: 30, depth: 3, limit: 400, text: true,
  };
  const P = stepCode.stepCodeParse;
  const A = stepCode.stepCodeApply;
  const T = stepCode.stepCodeTrace;
  let s = P('{"program":[],"cursor":[0]}', L);
  s = press(A, s, [
    button({ action: "add", zone: "step" }),
    button({ action: "add", zone: "step" }),
    button({ action: "add", zone: "step" }),
    button({ action: "add", zone: "left" }),
    button({ action: "add", zone: "repeat", by: "2" }),
    button({ action: "add", zone: "step" }),
  ], L);
  check("built with the buttons", s, { program: ["step", "step", "step", "left", { repeat: 2, do: ["step"] }], cursor: [4, 1] });
  check("to the goal", T(s.program, L).outcome, "goal");
  check("every pose", T(s.program, L).poses.length, 7);
  check("out of the block", A(s, button({ action: "out" }), L).cursor, [5]);
  check("not out of the top", A({ program: [], cursor: [0] }, button({ action: "out" }), L), null);
  check("remove before the marker", A(s, button({ action: "remove" }), L).program[4], { repeat: 2, do: [] });
  const empty = A(s, button({ action: "remove" }), L);
  check("remove an empty block from inside it", A(empty, button({ action: "remove" }), L), { program: ["step", "step", "step", "left"], cursor: [4] });
  check("a count the item does not offer", A(s, button({ action: "add", zone: "repeat", by: "5" }), L), null);
  check("a tile the item does not offer", A(s, button({ action: "add", zone: "jump" }), L), null);
  check("move the marker", A(s, button({ action: "cursor", zone: "1" }), L).cursor, [1]);
  check("not to nowhere", A(s, button({ action: "cursor", zone: "9" }), L), null);
  check("dropped after a line", A(s, { type: "add", zone: "right", at: "0" }, L).program.slice(0, 2), ["right", "step"]);
  const deep = P('{"program":[{"repeat":2,"do":[{"repeat":2,"do":[]}]}],"cursor":[0,0,0]}', L);
  check("two blocks deep is allowed", !!deep, true);
  check("three is not", A(deep, button({ action: "add", zone: "if_wall" }), L), null);
  check("parse refuses a third level", P('{"program":[{"repeat":2,"do":[{"repeat":2,"do":[{"if_wall":[]}]}]}]}', L), null);
  check("parse refuses a bad cursor", P('{"program":["step"],"cursor":[2]}', L), null);
  check("parse refuses an extra key", P('{"program":[{"repeat":2,"do":[],"x":1}]}', L), null);
  check("parse refuses a string count", P('{"program":[{"repeat":"2","do":[]}]}', L), null);
  check("a wall stops it", T(["step", "left", "step"], L).outcome, "wall");
  check("off the grid stops it", T(["left", "step", "step", "step"], L).outcome, "wall");
  check("stopping short", T(["step"], L).outcome, "short");
  check("if wall ahead turns", T([{ repeat: 3, do: ["step"] }, { if_wall: ["left"] }, "step", "step"], L).outcome, "goal");
  const L2 = Object.assign({}, L, { repeats: [9], limit: 50 });
  check("a loop that runs too long is stopped", T([{ repeat: 9, do: [{ repeat: 9, do: ["left"] }] }], L2).outcome, "limit");
  check("shown at the start only", [
    stepCode.stepCodeShown(s, { zone: "bot", index: (2 * 4 + 0) * 4 + 1 }, L),
    stepCode.stepCodeShown(s, { zone: "bot", index: 0 }, L),
    stepCode.stepCodeShown(s, { zone: "trail", index: 0 }, L),
  ], [true, false, false]);
  const say = {
    empty: "no tiles yet", made: "{count} tiles: {tiles}", made_one: "1 tile: {tiles}", step: "step",
    left: "left", right: "right", repeat: "repeat {n}", if_wall: "if wall", block: "{head} ({body})",
    end: "end", start_line: "Start", py_step: "step()", py_left: "turn_left()", py_right: "turn_right()",
    py_repeat: "for _ in range({n}):", py_if: "if wall_ahead():", py_pass: "pass",
  };
  check("describe", stepCode.stepCodeDescribe(s, say), "6 tiles: step, step, step, left, repeat 2 (step)");
  check("describe empty", stepCode.stepCodeDescribe({ program: [], cursor: [0] }, say), "no tiles yet");
  check("as text", stepCode.stepCodeText([{ repeat: 2, do: [] }, { if_wall: ["left"] }], say), "for _ in range(2):\n    pass\nif wall_ahead():\n    turn_left()");
  const lines = stepCode.stepCodeLines(s.program, say);
  check("every line puts the marker somewhere different", new Set(lines.map((l) => l.after.join("."))).size, lines.length);
  check("a block's line puts it inside", lines[5], { text: "repeat 2", depth: 0, after: [4, 0] });
}

/* --- explore_sim ----------------------------------------------------------- */

{
  const L = { stops: 4, start: 1, predict: ["a", "b"], explain: ["x", "y", "z"] };
  const P = exploreSim.exploreSimParse;
  const A = exploreSim.exploreSimApply;
  let s = P('{"prediction":null,"locked":false,"stop":1,"explain":null}', L);
  check("the slider waits for a prediction", A(s, { type: "slide", by: 2 }, L), null);
  check("so does the explanation", A(s, button({ action: "explain", zone: "x" }), L), null);
  s = A(s, button({ action: "predict", zone: "a" }), L);
  check("not sealed by the prediction", exploreSim.exploreSimSealed(s), false);
  s = A(s, { type: "slide", by: 3 }, L);
  check("the first move locks", [s.locked, exploreSim.exploreSimSealed(s)], [true, true]);
  check("and the prediction stays", A(s, button({ action: "predict", zone: "b" }), L), null);
  check("back past the start", A(s, button({ action: "step", by: "-1" }), L).stop, 2);
  check("not off the end", A(s, button({ action: "step", by: "1" }), L), null);
  s = A(s, button({ action: "explain", zone: "y" }), L);
  check("explained", s, { prediction: "a", locked: true, stop: 3, explain: "y" });
  check("parse refuses a moved slider that is not locked", P('{"prediction":"a","locked":false,"stop":2,"explain":null}', L), null);
  check("parse refuses a lock with no prediction", P('{"prediction":null,"locked":true,"stop":1,"explain":null}', L), null);
  check("parse refuses an explanation before watching", P('{"prediction":"a","locked":false,"stop":1,"explain":"x"}', L), null);
  check("parse refuses a stop past the end", P('{"prediction":"a","locked":true,"stop":4,"explain":null}', L), null);
  const say = { none: "none", predicted: "predicted", observed: "observed", made: "“{choice}”", explain: { x: "X", y: "Y", z: "Z" } };
  check("describe", [
    exploreSim.exploreSimDescribe({ prediction: null, locked: false, explain: null }, say),
    exploreSim.exploreSimDescribe({ prediction: "a", locked: false, explain: null }, say),
    exploreSim.exploreSimDescribe({ prediction: "a", locked: true, explain: null }, say),
    exploreSim.exploreSimDescribe(s, say),
  ], ["none", "predicted", "observed", "“Y”"]);
  check("no pieces", exploreSim.exploreSimShown(), false);
}

if (failures) {
  console.error(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("simulation primitives: all checks passed");
