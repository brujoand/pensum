/* Arkade confetti, thrown through a stub DOM.
 *
 * Run directly with `node tests/js/arkade_confetti.test.js`, or through pytest.
 */

const fs = require("fs");
const path = require("path");

const SOURCE = path.join(__dirname, "..", "..", "src", "pensum", "web", "static", "arkade-confetti.js");
const src = fs.readFileSync(SOURCE, "utf8");

let failures = 0;
function check(what, condition) {
  if (condition) return;
  failures++;
  console.error(`FAIL: ${what}`);
}

function element() {
  const attrs = {};
  return {
    className: "",
    children: [],
    style: {
      setProperty(name, value) {
        this[name] = value;
      },
    },
    setAttribute: (name, value) => {
      attrs[name] = value;
    },
    getAttribute: (name) => (name in attrs ? attrs[name] : null),
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    removeChild(child) {
      this.children.splice(this.children.indexOf(child), 1);
      return child;
    },
  };
}

function page({ calm = false, reduced = false, screen = { innerWidth: 400, innerHeight: 800 } } = {}) {
  const timers = [];
  const body = element();
  const document = {
    body,
    createElement: () => element(),
    documentElement: { hasAttribute: (name) => calm && name === "data-calm" },
  };
  const window = {
    setTimeout: (fn, ms) => timers.push({ fn, ms }) && timers.length,
    matchMedia: () => ({ matches: reduced }),
    ...screen,
  };
  new Function("document", "window", src)(document, window);
  return { body, timers, throwConfetti: window.arkadeConfetti };
}

const px = (piece, name) => parseInt(piece.style[name], 10);

const game = page();
check("nothing is on the page until something is thrown", game.body.children.length === 0);
game.throwConfetti();
const layer = game.body.children[0];
check("one layer over the page, hidden from a screen reader", game.body.children.length === 1 && layer.className === "arkade-confetti" && layer.getAttribute("aria-hidden") === "true");
check("a big burst", layer.children.length === 48);
check("placed by the stylesheet, at the middle of the screen", layer.children.every((piece) => !("--x" in piece.style) && !("--y" in piece.style)));
check("flying upwards", layer.children.every((piece) => px(piece, "--dy") < 0));
check("across the screen and no further", layer.children.every((piece) => Math.abs(px(piece, "--dx")) <= 180));
check("wide: some pieces go well out to each side", layer.children.some((piece) => px(piece, "--dx") < -60) && layer.children.some((piece) => px(piece, "--dx") > 60));
check("then falling", layer.children.every((piece) => px(piece, "--fall") >= 160));
check("in more than one colour", layer.children[0].className.endsWith("--0") && layer.children[1].className.endsWith("--1"));
check("and more than one size", layer.children.every((piece) => Number(piece.style["--size"]) >= 0.7 && Number(piece.style["--size"]) <= 1.3));
game.throwConfetti();
check("a second throw uses the same layer", game.body.children.length === 1 && layer.children.length === 96);
check("a piece stays for its whole flight", game.timers[0].ms === 1800);
game.timers[0].fn();
check("a throw is cleared away once it has fallen", layer.children.length === 48);
game.timers[1].fn();
check("and so is the next", layer.children.length === 0);

const unsized = page({ screen: {} });
unsized.throwConfetti();
check("a window that does not say its size still gets a burst", unsized.body.children[0].children.length === 48);

const calm = page({ calm: true });
calm.throwConfetti();
check("calm mode throws none", calm.body.children.length === 0 && calm.timers.length === 0);
const reduced = page({ reduced: true });
reduced.throwConfetti();
check("nor does a device that asks for less motion", reduced.body.children.length === 0);

if (failures) {
  console.error(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("ok");
