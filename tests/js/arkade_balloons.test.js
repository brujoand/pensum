/* The balloon game, played through a stub DOM.
 *
 * arkade-balloons.js is an IIFE that reads the page the moment it loads, so the
 * harness builds the elements it reads, runs the shipped file against them,
 * and plays: swipes, buttons, arrow keys, lives, and a balloon left to drift.
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
  return {
    id,
    dataset: {},
    hidden: false,
    disabled: false,
    children: [],
    listeners: {},
    innerHTML: "",
    textContent: "",
    style: {
      transform: "",
      setProperty(name, value) {
        this[name] = value;
      },
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
    attrs: {},
    setAttribute(name, value) {
      this.attrs[name] = value;
    },
    getAttribute(name) {
      return name in this.attrs ? this.attrs[name] : null;
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

function page(round, { calm = false, failFirst = false, animate = false } = {}) {
  const frames = [];
  const ids = [
    "balloons", "balloons-round", "balloons-position", "balloons-lives", "balloons-rule",
    "balloons-hear", "balloons-say", "balloons-balloon", "balloons-shown", "balloons-sky",
    "balloons-string", "balloons-burst", "balloons-fly", "balloons-pop", "balloons-feedback",
    "balloons-next", "balloons-result", "balloons-rules", "balloons-no-voice",
  ];
  const els = Object.fromEntries(ids.map((id) => [id, element(id)]));
  Object.assign(els.balloons.dataset, {
    postUrl: "/nb/arkade/runde/r1",
    seconds: "60",
    labelRight: "Riktig!",
    labelLostTrue: "Den var riktig! Du mistet et liv. Det riktige er:",
    labelLostFalse: "Feil! Du mistet et liv. Det riktige er:",
    labelDrifted: "Det riktige er:",
    labelPosition: "Ballong {n} av {total}",
    labelLives: "Liv: {n}",
    labelFailed: "Vi fikk ikke lagret runden.",
  });
  els["balloons-round"].textContent = JSON.stringify(round);
  els["balloons-fly"].attrs = { "aria-label": "Riktig: la den fly" };
  els["balloons-pop"].attrs = { "aria-label": "Feil: stikk hull" };
  els["balloons-next"].hidden = true;
  els["balloons-rules"].content = {
    querySelector: (sel) => ({ textContent: sel.includes("statement") ? "Stemmer det?" : "Hør" }),
  };

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
    ...(animate ? { requestAnimationFrame: (fn) => frames.push(fn) } : {}),
  };
  const fetch = (url, options) => {
    posted.push({ url, body: JSON.parse(options.body) });
    const ok = !(failFirst && posted.length === 1);
    return Promise.resolve({ ok, text: () => Promise.resolve("<p>resultat</p>") });
  };

  new Function("document", "window", "fetch", src)(document, window, fetch);

  const el = els["balloons-balloon"];
  /* Let the fly-away or needle animation finish: run the newest short timer. */
  const settle = () => {
    for (let i = timers.length - 1; i >= 0; i--) {
      if (timers[i] && timers[i].ms < 5000) {
        const t = timers[i];
        timers[i] = null;
        t.fn();
        return;
      }
    }
  };
  const swipe = (dx) => {
    el.fire("pointerdown", { clientX: 200, pointerId: 1 });
    el.fire("pointermove", { clientX: 200 + dx });
    el.fire("pointerup", { clientX: 200 + dx });
  };
  const press = (key) => document.keys && document.keys({ key, preventDefault() {} });
  const next = () => els["balloons-next"].click();
  const flush = () => new Promise((resolve) => setImmediate(resolve));
  const feedback = () => els["balloons-feedback"].textContent;
  /* Run `n` animation frames, 16 ms apart. */
  let clock = 0;
  const run = (n) => {
    for (let i = 0; i < n; i++) {
      clock += 16;
      const due = frames.splice(0);
      due.forEach((fn) => fn(clock));
    }
  };
  return { els, el, timers, posted, settle, swipe, press, next, flush, feedback, run };
}

const item = (shown, isTrue, answer) => ({
  rule: "statement",
  shown,
  true: isTrue,
  answer,
  spoken: null,
  language: null,
});

const ROUND = {
  round: "r1",
  timed: true,
  lives: 3,
  items: [
    item("5 : 1 = 5", true, "5 : 1 = 5"),
    item("7 · 8 = 48", false, "7 · 8 = 56"),
    item("3 · 4 = 12", true, "3 · 4 = 12"),
    item("6 + 1 = 8", false, "6 + 1 = 7"),
    item("2 · 2 = 4", true, "2 · 2 = 4"),
  ],
};

(async () => {
  /* --- a round played by swiping ------------------------------------------ */
  const g = page(ROUND);
  check("the balloon shows the statement", g.els["balloons-shown"].textContent === "5 : 1 = 5");
  check("three hearts", g.els["balloons-lives"].textContent === "Liv: 3 ♥♥♥");
  check("each half is named for what it says about this balloon", g.els["balloons-fly"].attrs["aria-label"] === "Riktig: la den fly: 5 : 1 = 5" && g.els["balloons-pop"].attrs["aria-label"] === "Feil: stikk hull: 5 : 1 = 5");
  check("a timed balloon rises", g.el.classList.contains("balloon--rising"));

  g.el.fire("pointerdown", { clientX: 200, pointerId: 1 });
  g.el.fire("pointermove", { clientX: 290 });
  check("dragging towards the needle lights that half", g.els["balloons-sky"].classList.contains("balloons__sky--toward-pop"));
  check("and the balloon follows the finger", g.el.style.transform.startsWith("translate(90.0px"));
  g.el.fire("pointermove", { clientX: 210 });
  check("back near the middle, neither half is lit", !g.els["balloons-sky"].classList.contains("balloons__sky--toward-pop"));
  g.el.fire("pointerup", { clientX: 210 });
  check("a short swipe is not an answer", g.posted.length === 0 && g.feedback() === "");
  check("and the balloon goes back", g.el.style.transform.startsWith("translate(0.0px,0.0px)"));

  g.swipe(-120);
  check("a swipe left lets it fly", g.el.classList.contains("balloon--flown"));
  check("not to the needle", !g.el.classList.contains("balloon--popped"));
  g.settle();
  check("a right answer just says so", g.feedback() === "Riktig!");
  check("no life lost", g.els["balloons-lives"].textContent === "Liv: 3 ♥♥♥");
  g.swipe(120);
  check("a swipe after the answer does nothing", !g.el.classList.contains("balloon--popped"));

  g.next();
  check("the next balloon", g.els["balloons-shown"].textContent === "7 · 8 = 48");
  check("comes back whole", !g.el.classList.contains("balloon--gone") && !g.el.classList.contains("balloon--flown"));
  g.swipe(120);
  check("a swipe right sends it to the needle", g.el.classList.contains("balloon--popped"));
  check("not away", !g.el.classList.contains("balloon--flown"));
  g.settle();
  check("popping a false one is right, and says only that", g.feedback() === "Riktig!");

  g.next();
  g.els["balloons-pop"].click();
  g.settle();
  check("popping a true one costs a life", g.els["balloons-lives"].textContent === "Liv: 2 ♥♥♡");
  check("and shows the right form", g.feedback() === "Den var riktig! Du mistet et liv. Det riktige er: 3 · 4 = 12");

  g.next();
  g.press("ArrowLeft");
  g.settle();
  check("the left arrow flies; a false one flown costs a life", g.els["balloons-lives"].textContent === "Liv: 1 ♥♡♡");
  check("and a wrong answer shows the right form", g.feedback() === "Feil! Du mistet et liv. Det riktige er: 6 + 1 = 7");

  g.next();
  g.timers.find((t) => t && t.ms === 60000).fn();
  g.settle();
  check("a balloon left alone drifts away and shows the right form", g.feedback() === "Det riktige er: 2 · 2 = 4");
  check("and costs no life", g.els["balloons-lives"].textContent === "Liv: 1 ♥♡♡");

  g.next();
  await g.flush();
  check("the round is posted once", g.posted.length === 1);
  check(
    "flown, popped, popped, flown, drifted",
    JSON.stringify(g.posted[0].body.picks) === JSON.stringify([0, 1, 1, 0, null])
  );
  check("the server's result is shown", g.els["balloons-result"].innerHTML === "<p>resultat</p>");

  /* --- the last life ends the round --------------------------------------- */
  const lost = page({ ...ROUND, timed: false });
  lost.press("ArrowRight"); // true popped: 2 left
  lost.settle();
  lost.next();
  lost.press("ArrowLeft"); // false flown: 1 left
  lost.settle();
  lost.next();
  lost.press("ArrowRight"); // true popped: 0 left
  lost.settle();
  check("three wrong answers spend three lives", lost.els["balloons-lives"].textContent === "Liv: 0 ♡♡♡");
  lost.next();
  await lost.flush();
  check("and end the round there", lost.posted.length === 1 && JSON.stringify(lost.posted[0].body.picks) === JSON.stringify([1, 0, 1]));

  /* --- the motion, frame by frame ----------------------------------------- */
  const pos = (el) => {
    const found = /translate\((-?[\d.]+)px,(-?[\d.]+)px\)/.exec(el.style.transform);
    return found ? [Number(found[1]), Number(found[2])] : [NaN, NaN];
  };
  const bendOf = (p) => {
    const found = / (-?[\d.]+) 198$/.exec(p.els["balloons-string"].attrs.d || "");
    return found ? Number(found[1]) - 50 : NaN;
  };

  const anim = page({ ...ROUND, timed: false }, { animate: true });
  anim.run(5);
  anim.el.fire("pointerdown", { clientX: 200, pointerId: 1 });
  anim.el.fire("pointermove", { clientX: 250 });
  anim.run(2);
  check("the string trails behind a quick drag", bendOf(anim) < -5);
  anim.el.fire("pointerup", { clientX: 250 });
  let crossed = false;
  for (let i = 0; i < 60; i++) {
    anim.run(1);
    if (pos(anim.el)[0] < -2) crossed = true;
  }
  check("a short swipe springs back past the middle before it rests", crossed);
  anim.run(120);
  check("and then rests near the middle", Math.abs(pos(anim.el)[0]) < 6);

  anim.swipe(-120);
  anim.run(30);
  const [flyX, flyY] = pos(anim.el);
  check("swiped left, it flies up and to the left", flyX < -50 && flyY < -50);

  anim.settle();
  anim.next();
  anim.run(5);
  anim.swipe(120);
  anim.run(8);
  const [needleX, needleY] = pos(anim.el);
  check("swiped right, it goes up and to the right, to the needle", needleX > 30 && needleY < -30);
  anim.run(60);
  check("and bursts there", anim.el.classList.contains("balloon--gone") && anim.els["balloons-burst"].hidden === false);

  /* --- untimed, and calm ---------------------------------------------------- */
  const untimed = page({ ...ROUND, timed: false });
  check("with the timer off the balloon does not rise", !untimed.el.classList.contains("balloon--rising"));
  check("and there is no clock", untimed.timers.length === 0);
  const calm = page(ROUND, { calm: true });
  check("calm mode cannot draw the timer, so it does not run one", calm.timers.length === 0);

  /* --- a save that fails ---------------------------------------------------- */
  const failing = page({ ...ROUND, timed: false, items: ROUND.items.slice(0, 1) }, { failFirst: true });
  failing.press("ArrowLeft");
  failing.settle();
  failing.next();
  await failing.flush();
  check("a failed save says so", failing.feedback() === "Vi fikk ikke lagret runden.");
  failing.next();
  await failing.flush();
  check("Next sends the same picks again", failing.posted.length === 2 &&
    JSON.stringify(failing.posted[1].body) === JSON.stringify(failing.posted[0].body));

  if (failures) {
    console.error(`${failures} check(s) failed`);
    process.exit(1);
  }
  console.log("ok");
})();
