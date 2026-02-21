// main.js — Shared JS for SWD Store

// Mobile nav toggle
(function () {
  var toggle = document.getElementById('nav-toggle');
  var menu = document.getElementById('mobile-menu');
  if (toggle && menu) {
    toggle.addEventListener('click', function () {
      menu.classList.toggle('hidden');
    });
  }
})();

// Auto-dismiss flash messages after 5 seconds
(function () {
  var messages = document.querySelectorAll('.flash-message');
  messages.forEach(function (msg) {
    setTimeout(function () {
      msg.style.transition = 'opacity 0.4s';
      msg.style.opacity = '0';
      setTimeout(function () { msg.remove(); }, 400);
    }, 5000);
  });
})();
