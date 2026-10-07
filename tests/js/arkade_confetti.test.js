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

function page({ calm = false, reduced = false } = {}) {
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
  };
  new Function("document", "window", src)(document, window);
  return { body, timers, throwFrom: window.arkadeConfetti };
}

const CARD = { getBoundingClientRect: () => ({ left: 100, top: 200, width: 80, height: 60 }) };

const game = page();
check("nothing is on the page until something is thrown", game.body.children.length === 0);
game.throwFrom(CARD);
const layer = game.body.children[0];
check("one layer over the page, hidden from a screen reader", game.body.children.length === 1 && layer.className === "arkade-confetti" && layer.getAttribute("aria-hidden") === "true");
check("a little confetti", layer.children.length === 10);
check("from the middle of what threw it", layer.children[0].style["--x"] === "140px" && layer.children[0].style["--y"] === "230px");
check("flying upwards", layer.children.every((piece) => parseInt(piece.style["--dy"], 10) < 0));
check("in more than one colour", layer.children[0].className.endsWith("--0") && layer.children[1].className.endsWith("--1"));
game.throwFrom(CARD);
check("a second throw uses the same layer", game.body.children.length === 1 && layer.children.length === 20);
game.timers[0].fn();
check("a throw is cleared away once it has fallen", layer.children.length === 10);
game.timers[1].fn();
check("and so is the next", layer.children.length === 0);
game.throwFrom(null);
check("nothing to throw from throws nothing", layer.children.length === 0);

const calm = page({ calm: true });
calm.throwFrom(CARD);
check("calm mode throws none", calm.body.children.length === 0 && calm.timers.length === 0);
const reduced = page({ reduced: true });
reduced.throwFrom(CARD);
check("nor does a device that asks for less motion", reduced.body.children.length === 0);

if (failures) {
  console.error(`${failures} check(s) failed`);
  process.exit(1);
}
console.log("ok");
