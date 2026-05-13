// Patch screenX/screenY on MouseEvent to add realistic offsets.
// CDP's Input.dispatchMouseEvent sets screenX==clientX, which Cloudflare
// Turnstile uses to detect automation. Real events have an offset from
// the window position and taskbar height.
(function () {
  var ox = Math.floor(Math.random() * 400) + 800;
  var oy = Math.floor(Math.random() * 200) + 400;

  Object.defineProperty(MouseEvent.prototype, "screenX", {
    get: function () {
      return this.clientX + ox;
    },
    configurable: true,
  });

  Object.defineProperty(MouseEvent.prototype, "screenY", {
    get: function () {
      return this.clientY + oy;
    },
    configurable: true,
  });
})();
