/* The balloon game, played through a stub DOM.
 *
 * arkade-balloons.js is an IIFE that reads the page the moment it loads, so the
 * harness builds the few elements it reads, runs the shipped file against them,
 * and plays a round: a right pop, a balloon left to pop by itself, a wrong pop.
 * What the page posts at the end is what the server marks, so that is what is
 * checked.
 *
 * Run directly with `node tests/js/arkade_balloons.test.js`, or through pytest.
 */

const fs = require("fs");
const path = require("path");

const SOURCE = path.join(
  __dirname, "..", "..", "src", "pensum", "web", "static", "arkade-balloons.js"
);
const src = fs.readFileSync(SOURCE, "utf8");

let failures = 0;
function check(what, condition) {
  if (condition) return;
  failures++;
  console.error(`FAIL: ${what}`);
}

/* --- a stub DOM, only as much as the game touches ------------------------ */

function element(id) {
  const classes = new Set();
  const el = {
    id,
    dataset: {},
    hidden: false,
    disabled: false,
    style: {
      setProperty(name, value) {
        this[name] = value;
      },
    },
    children: [],
    listeners: {},
    innerHTML: "",
    _text: "",
    get textContent() {
      return this._text;
    },
    set textContent(value) {
      this._text = value;
      if (value === "") this.children = [];
    },
    get className() {
      return [...classes].join(" ");
    },
    set className(value) {
      classes.clear();
      value.split(" ").filter(Boolean).forEach((c) => classes.add(c));
    },
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
    },
    appendChild(child) {
      this.children.push(child);
      if (child._text) this._text += child._text;
      return child;
    },
    querySelectorAll(selector) {
      return selector === ".balloon" ? this.children : [];
    },
    addEventListener(type, fn) {
      this.listeners[type] = fn;
    },
    click() {
      if (!this.disabled && this.listeners.click) this.listeners.click();
    },
    focus() {},
  };
  return el;
}

function page(round, { calm = false, failFirst = false } = {}) {
  const ids = [
    "balloons", "balloons-round", "balloons-position", "balloons-rule", "balloons-hear",
    "balloons-say", "balloons-sky", "balloons-feedback", "balloons-next",
    "balloons-result", "balloons-rules", "balloons-no-voice",
  ];
  const els = Object.fromEntries(ids.map((id) => [id, element(id)]));
  Object.assign(els.balloons.dataset, {
    postUrl: "/nb/arkade/runde/r1",
    seconds: "60",
    labelRight: "Riktig!",
    labelWrong: "Ikke helt. Riktig er:",
    labelPopped: "Ballongen sprakk. Riktig er:",
    labelPosition: "Ballong {n} av {total}",
    labelFailed: "Vi fikk ikke lagret runden."
  });
  els["balloons-round"].textContent = JSON.stringify(round);
  els["balloons-rules"].content = {
    querySelector: (sel) => ({ textContent: sel.includes("false_statement") ? "Sprekk feil" : "Sprekk ordet" }),
  };

  const timers = [];
  const posted = [];
  const document = {
    getElementById: (id) => els[id] || null,
    createElement: () => element(""),
    documentElement: { hasAttribute: (name) => calm && name === "data-calm" },
  };
  const window = {
    setTimeout: (fn) => timers.push(fn) && timers.length,
    clearTimeout: (n) => {
      timers[n - 1] = null;
    },
    matchMedia: () => ({ matches: false }),
  };
  const fetch = (url, options) => {
    posted.push({ url, body: JSON.parse(options.body) });
    const ok = !(failFirst && posted.length === 1);
    return Promise.resolve({ ok, text: () => Promise.resolve("<p>resultat</p>") });
  };

  new Function("document", "window", "fetch", src)(document, window, fetch);
  return { els, timers, posted };
}

function balloon(els, i) {
  return els["balloons-sky"].children[i];
}

const item = (candidates, match, answer) => ({
  rule: "false_statement",
  candidates,
  matches: [match],
  answer,
  spoken: null,
  language: null,
});

const ROUND = {
  round: "r1",
  timed: true,
  items: [
    item(["2 · 3 = 6", "5 : 1 = 1", "4 · 2 = 8"], 1, "5 : 1 = 5"),
    item(["7 · 8 = 48", "2 · 2 = 4", "3 · 3 = 9"], 0, "7 · 8 = 56"),
    item(["1 + 1 = 2", "9 : 3 = 3", "6 + 1 = 8"], 2, "6 + 1 = 7"),
  ],
};

/* --- a timed round ------------------------------------------------------- */

(async () => {
  const { els, timers, posted } = page(ROUND);

  check("the first item shows three balloons", els["balloons-sky"].children.length === 3);
  check("the position is shown", els["balloons-position"].textContent === "Ballong 1 av 3");
  check("a timed balloon grows", balloon(els, 0).classList.contains("balloon--growing"));
  check("the balloon grows for the full time", balloon(els, 0).style["--balloon-seconds"] === "60s");
  check("a timer is set for the item", timers.length === 1);

  balloon(els, 1).click();
  check("a right pop says so", els["balloons-feedback"].textContent === "Riktig! 5 : 1 = 5");
  check("the pop cancels the timer", timers[0] === null);
  check("every balloon is then disabled", els["balloons-sky"].children.every((b) => b.disabled));
  check("next appears", els["balloons-next"].hidden === false);

  els["balloons-next"].click();
  check("the second item replaces the first", els["balloons-position"].textContent === "Ballong 2 av 3");
  timers[1]();
  check(
    "a balloon left alone pops and shows the right form",
    els["balloons-feedback"].textContent === "Ballongen sprakk. Riktig er: 7 · 8 = 56"
  );
  balloon(els, 0).click();
  check("a popped item cannot be answered again", els["balloons-feedback"].textContent.startsWith("Ballongen sprakk"));

  els["balloons-next"].click();
  balloon(els, 0).click();
  check(
    "a wrong pop shows the right form",
    els["balloons-feedback"].textContent === "Ikke helt. Riktig er: 6 + 1 = 7"
  );
  check("the right balloon is marked", balloon(els, 2).classList.contains("balloon--answer"));

  els["balloons-next"].click();
  await new Promise((resolve) => setImmediate(resolve));
  check("the round is posted once", posted.length === 1);
  check("to the round's address", posted[0] && posted[0].url === "/nb/arkade/runde/r1");
  check(
    "with the right pop, a timeout as null, and the wrong pop",
    posted[0] && JSON.stringify(posted[0].body.picks) === JSON.stringify([1, null, 0])
  );
  check("the server's result is shown", els["balloons-result"].innerHTML === "<p>resultat</p>");

  /* --- untimed, by setting or by calm mode ------------------------------- */

  const untimed = page({ ...ROUND, timed: false });
  check("with the timer off nothing grows", !balloon(untimed.els, 0).classList.contains("balloon--growing"));
  check("with the timer off no timer is set", untimed.timers.length === 0);

  /* --- a save that fails -------------------------------------------------- */

  const failing = page({ ...ROUND, timed: false }, { failFirst: true });
  for (let i = 0; i < ROUND.items.length; i++) {
    balloon(failing.els, 0).click();
    failing.els["balloons-next"].click();
  }
  await new Promise((resolve) => setImmediate(resolve));
  check("a failed save says so", failing.els["balloons-feedback"].textContent === "Vi fikk ikke lagret runden.");
  check("and offers the button again", failing.els["balloons-next"].hidden === false);
  failing.els["balloons-next"].click();
  await new Promise((resolve) => setImmediate(resolve));
  check("pressing it sends the same picks again", failing.posted.length === 2 &&
    JSON.stringify(failing.posted[1].body) === JSON.stringify(failing.posted[0].body));
  check("and the result is then shown", failing.els["balloons-result"].innerHTML === "<p>resultat</p>");

  const calm = page(ROUND, { calm: true });
  check("calm mode cannot draw the timer, so it does not run one", calm.timers.length === 0);

  if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
  }
  console.log("ok");
})();
