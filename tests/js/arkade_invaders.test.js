/* Invaders, played through a stub DOM.
 *
 * Builds the elements arkade-invaders.js reads, runs the shipped file, and
 * plays: taps, swipes, keys, the pass button, targets landing with the timer
 * on, and lives. What the page posts is what the server marks.
 *
 * Run directly with `node tests/js/arkade_invaders.test.js`, or through pytest.
 */

const fs = require("fs");
const path = require("path");

const SOURCE = path.join(__dirname, "..", "..", "src", "pensum", "web", "static", "arkade-invaders.js");
const src = fs.readFileSync(SOURCE, "utf8");

let failures = 0;
function check(what, condition) {
  if (condition) return;
  failures++;
  console.error(`FAIL: ${what}`);
}

function element(id) {
  const classes = new Set();
  return {
    id,
    tagName: "DIV",
    dataset: {},
    hidden: false,
    disabled: false,
    listeners: {},
    innerHTML: "",
    textContent: "",
    style: {},
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
    addEventListener(type, fn) {
      this.listeners[type] = fn;
    },
    fire(type, event = {}) {
      if (this.listeners[type]) this.listeners[type](event);
    },
    click() {
      if (!this.disabled && this.listeners.click) this.listeners.click();
    },
    focus() {},
  };
}

function page(round, { calm = false } = {}) {
  const ids = [
    "invaders", "invaders-round", "invaders-position", "invaders-lives", "invaders-rule",
    "invaders-space", "invaders-target", "invaders-token", "invaders-beam", "invaders-burst",
    "invaders-pass", "invaders-feedback", "invaders-next", "invaders-result",
  ];
  const els = Object.fromEntries(ids.map((id) => [id, element(id)]));
  Object.assign(els.invaders.dataset, {
    postUrl: "/nb/arkade/runde/r1",
    seconds: "8",
    labelRight: "Riktig!",
    labelWrong: "Feil! Du mistet et liv.",
    labelMissed: "Den skulle vært skutt.",
    labelPosition: "Mål {n} av {total}",
    labelLives: "Liv: {n}",
    labelFailed: "Vi fikk ikke lagret runden.",
  });
  els["invaders-round"].textContent = JSON.stringify(round);
  els["invaders-next"].hidden = true;
  els["invaders-target"].tagName = "BUTTON";

  const timers = [];
  const posted = [];
  const document = {
    getElementById: (id) => els[id] || null,
    documentElement: { hasAttribute: (name) => calm && name === "data-calm" },
    keys: null,
    addEventListener(type, fn) {
      if (type === "keydown") this.keys = fn;
    },
  };
  const window = {
    setTimeout: (fn, ms) => timers.push({ fn, ms }) && timers.length,
    clearTimeout: (n) => {
      timers[n - 1] = null;
    },
    matchMedia: () => ({ matches: false }),
  };
  const fetch = (url, options) => {
    posted.push({ url, body: JSON.parse(options.body) });
    return Promise.resolve({ ok: true, text: () => Promise.resolve("<p>resultat</p>") });
  };
  new Function("document", "window", "fetch", src)(document, window, fetch);

  const t = els["invaders-target"];
  const settle = () => {
    for (let i = timers.length - 1; i >= 0; i--) {
      if (timers[i] && timers[i].ms < 1000) {
        const due = timers[i];
        timers[i] = null;
        due.fn();
      }
    }
  };
  const land = () => {
    const due = timers.find((x) => x && x.ms === 8000);
    if (due) due.fn();
  };
  const tap = () => {
    t.fire("pointerdown", { clientY: 100, pointerId: 1 });
    t.fire("pointerup", { clientY: 102 });
    t.click();
  };
  const swipeDown = () => {
    t.fire("pointerdown", { clientY: 100, pointerId: 1 });
    t.fire("pointermove", { clientY: 190 });
    t.fire("pointerup", { clientY: 190 });
    t.click();
  };
  const press = (key, target = { tagName: "BODY" }) =>
    document.keys && document.keys({ key, target, preventDefault() {} });
  const next = () => els["invaders-next"].click();
  const flush = () => new Promise((resolve) => setImmediate(resolve));
  const feedback = () => els["invaders-feedback"].textContent;
  const lives = () => els["invaders-lives"].textContent;
  return { els, timers, posted, settle, land, tap, swipeDown, press, next, flush, feedback, lives };
}

const target = (shown, isTrue) => ({
  shown,
  true: isTrue,
  answer: `${shown} ${isTrue ? "kan" : "kan ikke"} deles på 3.`,
});

const ROUND = {
  round: "r1",
  timed: false,
  lives: 3,
  rule: "Skyt tallene som kan deles på 3.",
  items: [target("9", true), target("10", false), target("12", true), target("7", false), target("6", true)],
};

(async () => {
  /* --- untimed: taps, swipes, keys, the pass button ------------------------ */
  const g = page(ROUND);
  check("the rule is shown", g.els["invaders-rule"].textContent === "Skyt tallene som kan deles på 3.");
  check("the first target", g.els["invaders-token"].textContent === "9");
  check("three hearts", g.lives() === "Liv: 3 ♥♥♥");
  check("untimed, nothing falls", g.timers.length === 0);

  g.tap();
  check("a tap shoots: the beam flashes", g.els["invaders-beam"].hidden === false);
  check("and the target bursts", g.els["invaders-burst"].hidden === false && g.els["invaders-target"].classList.contains("invaders__target--gone"));
  g.settle();
  check("a match shot is right", g.feedback() === "Riktig!");

  g.next();
  g.els["invaders-pass"].click();
  g.settle();
  check("a non-match let past is right", g.feedback() === "Riktig!" && g.lives() === "Liv: 3 ♥♥♥");

  g.next();
  g.swipeDown();
  g.settle();
  check("a swipe down lets it pass, and the click after it is not a shot", g.posted.length === 0 && g.feedback().startsWith("Feil!"));
  check("letting a match pass costs a life and says what it was", g.lives() === "Liv: 2 ♥♥♡" && g.feedback() === "Feil! Du mistet et liv. 12 kan deles på 3.");

  g.next();
  g.press(" ", { tagName: "BUTTON" });
  check("space on a focused button is left to the button", g.feedback() === "");
  g.press("ArrowUp");
  g.settle();
  check("the up arrow shoots; shooting a non-match costs a life", g.lives() === "Liv: 1 ♥♡♡");

  g.next();
  g.press("ArrowDown");
  g.settle();
  check("the down arrow lets it pass", g.lives() === "Liv: 0 ♡♡♡");
  g.next();
  await g.flush();
  check(
    "shot, passed, passed, shot, passed",
    g.posted.length === 1 && JSON.stringify(g.posted[0].body.picks) === JSON.stringify([0, 1, 1, 0, 1])
  );

  /* --- timed: targets land --------------------------------------------------- */
  const timed = page({ ...ROUND, timed: true });
  check("timed, the target falls", timed.els["invaders-target"].classList.contains("invaders__target--falling"));
  timed.land();
  timed.settle();
  check("a match that lands is a miss, with no life lost", timed.feedback() === "Den skulle vært skutt. 9 kan deles på 3." && timed.lives() === "Liv: 3 ♥♥♥");
  timed.next();
  timed.land();
  timed.settle();
  check("a non-match that lands was rightly let past", timed.feedback() === "Riktig!");
  timed.next();
  timed.tap();
  timed.settle();
  check("a shot stops its target landing", timed.timers.filter((x) => x && x.ms === 8000).length === 0);

  const landed = page({ ...ROUND, timed: true, items: ROUND.items.slice(0, 2) });
  landed.land();
  landed.settle();
  landed.next();
  landed.land();
  landed.settle();
  landed.next();
  await landed.flush();
  check("a missed match posts null, a landed non-match posts a pass", JSON.stringify(landed.posted[0].body.picks) === JSON.stringify([null, 1]));

  /* --- calm ------------------------------------------------------------------ */
  const calm = page({ ...ROUND, timed: true }, { calm: true });
  check("calm mode cannot draw the fall, so nothing falls", calm.timers.length === 0);

  if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
  }
  console.log("ok");
})();
