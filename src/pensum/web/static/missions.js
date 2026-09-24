/* Remembers which steps of a mission a pupil has ticked, in this browser.
 *
 * The page works without this file: the steps are plain checkboxes, and a
 * pupil can tick them either way. All this adds is that a tick is still there
 * tomorrow. The ticks live in localStorage under one key and are never sent
 * anywhere; there is no request in this file, which a test asserts.
 */
(function () {
  "use strict";

  var STORE_KEY = "pensum.missions.v1";

  function load() {
    try {
      return JSON.parse(localStorage.getItem(STORE_KEY) || "{}") || {};
    } catch (error) {
      return {};
    }
  }

  function save(state) {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(state));
    } catch (error) {
      /* Private window, or storage full. The ticks still work on the page. */
    }
  }

  var page = document.querySelector("[data-mission]");
  if (!page) {
    return;
  }
  var id = page.getAttribute("data-mission");
  var boxes = page.querySelectorAll(".mission-steps input[type=checkbox]");

  var ticked = load()[id] || [];
  Array.prototype.forEach.call(boxes, function (box) {
    box.checked = ticked.indexOf(box.value) !== -1;
    box.addEventListener("change", function () {
      var state = load();
      var now = [];
      Array.prototype.forEach.call(boxes, function (other) {
        if (other.checked) {
          now.push(other.value);
        }
      });
      if (now.length) {
        state[id] = now;
      } else {
        delete state[id];
      }
      save(state);
    });
  });
})();
