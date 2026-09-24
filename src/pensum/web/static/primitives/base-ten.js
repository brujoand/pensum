/* Base-ten blocks on a place-value mat.
 *
 * State: `{hundreds: h, tens: t, ones: o}`, the same shape the server grades
 * (`pensum.items.primitives.base_ten`), within the same limits: at most
 * `limits.ones` units, `limits.tens` rods and `limits.hundreds` flats. A board
 * without flats has `limits.hundreds` of 0, which refuses every hundred.
 *
 * Zones are the three columns and a tray under each (`supply-ones` ...). A
 * block goes to its own column wherever it is dropped, so it cannot land in
 * the wrong place -- except that dropping a rod on the ones column breaks it
 * into ten ones there, and dropping ten ones' worth on the tens column bundles
 * them, because that is what moving a block to the next place means.
 */
(function () {
  "use strict";

  var PLACES = ["hundreds", "tens", "ones"];

  function baseTenParse(json, limits) {
    var raw;
    try {
      raw = JSON.parse(json);
    } catch (error) {
      return null;
    }
    if (!raw || typeof raw !== "object") {
      return null;
    }
    var state = {};
    for (var i = 0; i < PLACES.length; i++) {
      var place = PLACES[i];
      var value = raw[place] === undefined ? 0 : raw[place];
      state[place] = window.PensumActivity.count(value, limits[place]);
      if (state[place] === null) return null;
    }
    return state;
  }

  /* Which place a zone is about: "supply-tens" and "tens" are both tens. */
  function baseTenPlace(zone) {
    var place = String(zone || "").replace(/^supply-/, "");
    return PLACES.indexOf(place) >= 0 ? place : null;
  }

  function baseTenWith(state, changes, limits) {
    var next = { hundreds: state.hundreds, tens: state.tens, ones: state.ones };
    for (var place in changes) {
      next[place] += changes[place];
      if (next[place] < 0 || next[place] > limits[place]) return null;
    }
    return next;
  }

  /* Ten of one place for one of the next place up, and back. */
  function baseTenBundle(state, place, limits) {
    if (place === "ones") return baseTenWith(state, { ones: -10, tens: 1 }, limits);
    if (place === "tens") return baseTenWith(state, { tens: -10, hundreds: 1 }, limits);
    return null;
  }

  function baseTenBreak(state, place, limits) {
    if (place === "tens") return baseTenWith(state, { tens: -1, ones: 10 }, limits);
    if (place === "hundreds") return baseTenWith(state, { hundreds: -1, tens: 10 }, limits);
    return null;
  }

  function baseTenAdd(state, place, delta, limits) {
    var change = {};
    change[place] = delta;
    return baseTenWith(state, change, limits);
  }

  function baseTenApply(state, action, limits) {
    var place = baseTenPlace(action.zone);
    if (action.type === "add") {
      return place ? baseTenAdd(state, place, 1, limits) : null;
    }
    if (action.type === "bundle") {
      return place ? baseTenBundle(state, place, limits) : null;
    }
    if (action.type === "break") {
      return place ? baseTenBreak(state, place, limits) : null;
    }
    if (action.type === "act") {
      /* Tapping a picked-up block again. A tray block is added; a rod or flat
       * breaks; a unit bundles when there are ten to bundle. */
      if (!place) return null;
      if (String(action.zone).indexOf("supply-") === 0) return baseTenAdd(state, place, 1, limits);
      if (place === "ones") return baseTenBundle(state, "ones", limits);
      return baseTenBreak(state, place, limits);
    }
    if (action.type !== "move") {
      return null;
    }
    var kind = baseTenPlace(action.from);
    var target = baseTenPlace(action.to);
    if (!kind || !target) return null;
    var fromTray = String(action.from).indexOf("supply-") === 0;
    var toTray = String(action.to).indexOf("supply-") === 0;
    if (fromTray && toTray) return null;
    if (fromTray) return baseTenAdd(state, kind, 1, limits);
    if (toTray) return baseTenAdd(state, kind, -1, limits);
    if (kind === target) return null;
    var down = PLACES.indexOf(target) > PLACES.indexOf(kind);
    if (down && PLACES.indexOf(target) === PLACES.indexOf(kind) + 1) {
      return baseTenBreak(state, kind, limits);
    }
    if (!down && PLACES.indexOf(kind) === PLACES.indexOf(target) + 1) {
      return baseTenBundle(state, kind, limits);
    }
    return null;
  }

  function baseTenShown(state, piece) {
    var place = baseTenPlace(piece.zone);
    return place !== null && state[place] > piece.index;
  }

  function baseTenValue(state) {
    return 100 * state.hundreds + 10 * state.tens + state.ones;
  }

  function baseTenDescribe(state, say, limits) {
    var P = window.PensumActivity;
    var parts = [];
    if (limits.hundreds) parts.push(P.plural(say, "hundreds_count", state.hundreds));
    parts.push(P.plural(say, "tens_count", state.tens));
    parts.push(P.plural(say, "ones_count", state.ones));
    var joined = parts.slice(0, -1).join(", ") + " " + say.and + " " + parts[parts.length - 1];
    return P.fill(say.made, { value: baseTenValue(state), parts: joined });
  }

  if (window.PensumActivity) {
    window.PensumActivity.register("base_ten", {
      parse: baseTenParse,
      apply: baseTenApply,
      shown: baseTenShown,
      describe: baseTenDescribe,
    });
  }
})();
